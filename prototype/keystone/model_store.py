"""Keystone canonical model store (ADR-005 §6-§7, Doc 05).

The persistence seam for `SystemModel`: `save_model`/`get_model`/`list_versions`/`diff`,
behind a `Protocol` — mirrors `council.py` (ADR-001) and `ingestion.py` (ADR-002) exactly,
per ADR-005 §7's own words ("Mirrors ADR-001/002"): a deterministic, in-memory `StubModelStore`
default (keeps the offline loop $0/stdlib, no DB required) and a real `SupabaseModelStore`
(`supabase_model_store.py`) behind the same interface, imported lazily so this module — and
the engine it sits next to — never pulls a DB driver just by being imported.

Every version is immutable once saved (ADR-005 §2): `save_model` always creates a new
version, never edits one in place. `StubModelStore` enforces this the same way the real
schema does — by never handing back a reference the caller could mutate to retroactively
change history (`copy.deepcopy` on both write and read).
"""
from __future__ import annotations

import copy
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from keystone.ingestion import IngestError, validate_model
from keystone.model import SystemModel

_VALID_PROVENANCE = frozenset({"GROUNDED", "GAP", "ASSUMPTION"})
_VALID_ASSUMPTION_SOURCE = frozenset({"llm_inferred", "benchmark", "user"})
_VALID_ASSUMPTION_CONFIDENCE = frozenset({"low", "med", "high"})


def _validate_for_persistence(model: SystemModel) -> None:
    """A SECOND validation pass, on top of `validate_model()` (ingestion.py, Bifola's
    lane — not touched here) — closes a real gap independent review found: that function
    checks a model is SIMULATABLE, not that it's SAVEABLE. The real schema (0001) enforces
    several enum/bound constraints via CHECK that `validate_model()` never checks (not its
    job), and `Assumption`/`Flow`/`Workload` have no `__post_init__` of their own either —
    so without this, `StubModelStore` silently accepts models `SupabaseModelStore`'s RPC
    then rejects with a raw, unhandled Postgres check_violation instead of a clean
    `IngestError`. Concretely: the DEFAULT `INGEST_PROVIDER=stub` path
    (`DeterministicStubIngestor`) constructs components with the stale lowercase
    `provenance="assumption"` default (model.py:59) — this is not a hypothetical edge
    case, it is what the $0 dev default actually produces. Applied identically by both
    store implementations so "saveable" means the same thing regardless of backend —
    that consistency, not just the individual checks, is the point."""
    for c in model.components.values():
        if c.provenance not in _VALID_PROVENANCE:
            raise IngestError(
                f"component {c.id!r} has provenance {c.provenance!r}, "
                f"must be one of {sorted(_VALID_PROVENANCE)}"
            )
    for f in model.flows:
        if not (0 < f.share <= 1):
            raise IngestError(f"flow {f.name!r} has share {f.share!r}, must be in (0, 1]")
        for s in f.path:
            if not (0 <= s.visit_prob <= 1):
                raise IngestError(
                    f"flow {f.name!r} step {s.component_id!r} has visit_prob {s.visit_prob!r}, "
                    "must be in [0, 1]"
                )
    for a in model.assumptions:
        if a.confidence not in _VALID_ASSUMPTION_CONFIDENCE:
            raise IngestError(
                f"assumption {a.subject!r} has confidence {a.confidence!r}, "
                f"must be one of {sorted(_VALID_ASSUMPTION_CONFIDENCE)}"
            )
        if a.source not in _VALID_ASSUMPTION_SOURCE:
            raise IngestError(
                f"assumption {a.subject!r} has source {a.source!r}, "
                f"must be one of {sorted(_VALID_ASSUMPTION_SOURCE)}"
            )
        if a.provenance not in _VALID_PROVENANCE:
            raise IngestError(
                f"assumption {a.subject!r} has provenance {a.provenance!r}, "
                f"must be one of {sorted(_VALID_PROVENANCE)}"
            )
    # DB CHECK is strict system_rps > 0; validate_model() only rejects < 0, so exactly 0
    # (a real value ClaudeIngestor's max(0.0, ...) fallback can produce) passes it but
    # would fail the schema's CHECK.
    if model.workload.system_rps <= 0:
        raise IngestError(f"workload.system_rps must be > 0, got {model.workload.system_rps!r}")


@dataclass(frozen=True)
class Project:
    """The minimal handle save_model/get_model need to address a project's rows.

    Deliberately carries no tenant_id: neither method ever sends a tenant value to
    Postgres — scoping is entirely server-side (RLS + the caller's own JWT, ADR-005 §1's
    whole point being "not application-layer filtering we could forget to apply"). Adding
    tenant_id here would be decorative at best, and at worst could read as if the client
    enforces something only the server actually does.
    """
    id: str


@dataclass(frozen=True)
class VersionMeta:
    """One row of `list_versions`' output — metadata about a saved version, without the
    full snapshot (fetch that via `get_model` if needed)."""
    version: int
    parent_version: int | None
    name: str
    created_at: datetime


@dataclass(frozen=True)
class ModelDiff:
    """What changed between two versions of the same project — deliberately SHALLOW (which
    components/flows differ, not which fields within a changed one). The milestone's only
    named "done" gate is the round-trip test; diff() has no test requirement in the issue
    text. Per CLAUDE.md's YAGNI lane ("ship the smallest correct thing"), a field-level diff
    is a GAP for later (needed once a UI wants to render "per_instance_rps: 500 -> 600"),
    not something to build speculatively now."""
    v1: int
    v2: int
    components_added: list[str]
    components_removed: list[str]
    components_changed: list[str]   # id present in both, but Component(v1) != Component(v2)
    flows_added: list[str]          # by Flow.name -- flows have no separate id in model.py
    flows_removed: list[str]
    flows_changed: list[str]
    workload_changed: bool
    pricing_changed: bool


class ModelStore(Protocol):
    def save_model(self, project: Project, model: SystemModel) -> int: ...
    def get_model(self, project: Project, version: int | Literal["head"] = "head") -> SystemModel: ...
    def list_versions(self, project: Project) -> list[VersionMeta]: ...
    def diff(self, project: Project, v1: int, v2: int) -> ModelDiff: ...


def _diff_models(v1: int, v2: int, a: SystemModel, b: SystemModel) -> ModelDiff:
    """Shared by both implementations (Stub and Supabase call this the same way, once each
    has its own two `SystemModel`s in hand) so the shallow-diff shape only lives in one
    place."""
    a_ids, b_ids = set(a.components), set(b.components)
    a_flow_names = {f.name for f in a.flows}
    b_flow_names = {f.name for f in b.flows}
    return ModelDiff(
        v1=v1, v2=v2,
        components_added=sorted(b_ids - a_ids),
        components_removed=sorted(a_ids - b_ids),
        components_changed=sorted(
            cid for cid in (a_ids & b_ids) if a.components[cid] != b.components[cid]
        ),
        flows_added=sorted(b_flow_names - a_flow_names),
        flows_removed=sorted(a_flow_names - b_flow_names),
        flows_changed=sorted(
            f.name for f in b.flows
            if f.name in a_flow_names
            and next(x for x in a.flows if x.name == f.name) != f
        ),
        workload_changed=a.workload != b.workload,
        pricing_changed=a.pricing != b.pricing,
    )


class StubModelStore:
    """In-memory ModelStore — the default, so the offline loop runs at $0 with no DB.

    Race-safety here means "safe for a single-process dev loop," not a distributed
    guarantee (that's what the real schema's version trigger + PK are for) — a plain
    `threading.Lock` around the dict is enough, since nothing in this codebase's engine
    path is async."""

    def __init__(self) -> None:
        self._versions: dict[str, list[SystemModel]] = {}
        self._lock = threading.Lock()

    def save_model(self, project: Project, model: SystemModel) -> int:
        validate_model(model)              # simulatable?
        _validate_for_persistence(model)   # saveable? (see that function's docstring)
        snapshot = copy.deepcopy(model)   # immutability: caller mutating their own `model` later can't rewrite history
        with self._lock:
            versions = self._versions.setdefault(project.id, [])
            versions.append(snapshot)
            return len(versions)   # 1-indexed version number

    def get_model(self, project: Project, version: int | Literal["head"] = "head") -> SystemModel:
        with self._lock:
            versions = self._versions.get(project.id, [])
            if not versions:
                raise KeyError(f"no versions saved for project {project.id!r}")
            idx = (len(versions) if version == "head" else version) - 1
            if not 0 <= idx < len(versions):
                raise KeyError(f"project {project.id!r} has no version {version!r}")
            return copy.deepcopy(versions[idx])   # caller mutating the RETURNED model can't corrupt the store either

    def list_versions(self, project: Project) -> list[VersionMeta]:
        with self._lock:
            versions = self._versions.get(project.id, [])
            now = datetime.now(timezone.utc)   # Stub has no real created_at; stamp "now" for every entry
            return [
                VersionMeta(version=i + 1, parent_version=(i or None), name=m.name, created_at=now)
                for i, m in enumerate(versions)
            ]

    def diff(self, project: Project, v1: int, v2: int) -> ModelDiff:
        return _diff_models(v1, v2, self.get_model(project, v1), self.get_model(project, v2))


def make_model_store(provider: str | None = None, *, access_token: str | None = None) -> ModelStore:
    """Build the configured model store. Defaults to the deterministic in-memory stub so
    the offline loop runs with no DB and at $0 (CLAUDE.md cost rule) — mirrors
    `make_council`'s shape exactly. Reads STORE_PROVIDER from the environment when
    `provider` isn't passed explicitly. `access_token` is required (and lazily imports
    `supabase_model_store`, keeping the `db` extra out of the base install) only when the
    provider is `supabase` — every real call then runs as THAT caller's own JWT, so RLS
    stays in force."""
    provider = (provider or os.getenv("STORE_PROVIDER", "stub")).strip().lower()
    if provider == "stub":
        return StubModelStore()
    if provider == "supabase":
        if not access_token:
            raise ValueError("STORE_PROVIDER=supabase needs an access_token (the caller's own JWT)")
        from keystone.supabase_model_store import SupabaseModelStore   # lazy: optional dep
        return SupabaseModelStore(access_token)
    raise ValueError(f"Unknown STORE_PROVIDER={provider!r}. Use one of: stub | supabase.")
