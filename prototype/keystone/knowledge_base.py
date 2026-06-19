"""Knowledge Base / grounding layer (ADR-006) — capacities → evidence.

The L0→L1 lever: a place that can attach **resolvable evidence** to an input value
(a component's service rate, a cost) so it can move ASSUMPTION → GROUNDED. Today
nothing is GROUNDED — this scaffolds the seam + the trust contract so that, when real
benchmark data is curated, it can only ever be tagged GROUNDED *with a citation*.

Prime directive (ADR-002 boundary): the KB grounds **inputs** and never produces a
derived metric (utilisation/bottleneck/breakpoint/latency/cost estimate) — the engine
remains the sole producer of those. Honesty contract (Doc 03): a `Grounding` cannot be
constructed without ≥1 resolvable `Citation` and a confidence band; no evidence → the KB
returns None and the caller keeps the value as ASSUMPTION. Stub-default ($0, offline):
the default `EmptyKnowledgeBase` grounds nothing — the honest L0 state.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from keystone.model import ComponentKind

# The KB grounds INPUT capacities/costs only — never a DERIVED metric (utilisation,
# bottleneck, breakpoint, latency percentiles, cost ESTIMATE), which the engine alone
# produces (prime directive; ADR-002 boundary). These three are the per-unit facts a
# benchmark can establish; `instances` is a sizing choice, not a grounded fact.
GROUNDABLE_METRICS = frozenset({"per_instance_rps", "base_latency_ms", "monthly_cost_per_instance"})

_MAX_TEXT = 500


def _require_groundable_metric(metric: str) -> None:
    if metric not in GROUNDABLE_METRICS:
        raise ValueError(
            f"the KB may only ground INPUT metrics {sorted(GROUNDABLE_METRICS)}; {metric!r} is not "
            "groundable — a derived metric is the engine's to compute (prime directive)")


def _single_line(name: str, val: str, *, maxlen: int = _MAX_TEXT) -> None:
    """Evidence text is rendered in reports; keep it single-line + bounded so a citation
    can't smuggle markdown/control chars (same posture as ingestion's text cleaning)."""
    if not isinstance(val, str):
        raise TypeError(f"{name} must be a string")
    if "\n" in val or "\r" in val:
        raise ValueError(f"{name} must be a single line (no newlines)")
    if len(val) > maxlen:
        raise ValueError(f"{name} exceeds {maxlen} chars")


@dataclass(frozen=True)
class Citation:
    """A resolvable piece of evidence. `reference` must point at something real
    (a URL, a vendor spec, a load-test id, a paper) — an unresolvable citation is
    an invented one (Doc 03), so both fields are required and non-empty."""
    source: str          # who/what (e.g. "AWS r7g.large pgbench", "Redis benchmarks")
    reference: str        # where it resolves (URL / doc id / load-test run id)
    note: str = ""

    def __post_init__(self) -> None:
        _single_line("Citation.source", self.source)
        _single_line("Citation.reference", self.reference)
        _single_line("Citation.note", self.note)
        if not self.source.strip():
            raise ValueError("Citation requires a non-empty source")
        if not self.reference.strip():
            raise ValueError("Citation requires a non-empty reference")


@dataclass(frozen=True)
class Grounding:
    """An input value backed by evidence. Constructing one REQUIRES ≥1 citation and a
    finite confidence band — so a GROUNDED value without resolvable evidence is
    structurally impossible (Doc 03 'evidence is a required field')."""
    value: float
    unit: str                       # e.g. "rps", "usd_minor_per_month", "ms"
    confidence_low: float
    confidence_high: float
    citations: tuple[Citation, ...] = ()
    provenance: str = "GROUNDED"

    def __post_init__(self) -> None:
        # Store citations immutably: a frozen dataclass still allows mutating a list
        # attribute (g.citations.clear()), which would void the evidence contract.
        object.__setattr__(self, "citations", tuple(self.citations))
        if self.provenance != "GROUNDED":
            raise ValueError("a Grounding is GROUNDED by definition; "
                             "use None (→ caller keeps ASSUMPTION) when there is no evidence")
        if not self.citations:
            raise ValueError("GROUNDED requires >=1 resolvable Citation (no evidence → return None)")
        for v in (self.value, self.confidence_low, self.confidence_high):
            if not math.isfinite(v):
                raise ValueError("Grounding values must be finite (no NaN/inf)")
        if self.value < 0 or self.confidence_low < 0:
            raise ValueError("grounded capacities/costs are physical quantities; they cannot be negative")
        if not (self.confidence_low <= self.value <= self.confidence_high):
            raise ValueError("confidence band must bracket the value: low <= value <= high")


@runtime_checkable
class KnowledgeBase(Protocol):
    """Grounds an INPUT value for a component kind + metric, or returns None if there is
    no evidence. Never returns a derived metric (prime directive)."""
    def ground(self, kind: ComponentKind, metric: str, *,
               context: dict | None = None) -> Grounding | None: ...


class EmptyKnowledgeBase:
    """Default stub: no curated data yet, so it grounds NOTHING — every value honestly
    stays ASSUMPTION. Deterministic, $0, offline (CLAUDE.md cost rule)."""
    def ground(self, kind: ComponentKind, metric: str, *,
               context: dict | None = None) -> Grounding | None:
        _require_groundable_metric(metric)   # reject derived-metric requests at the seam (prime directive)
        return None


_KNOWN_PROVIDERS = ("stub", "curated", "rag")


def make_knowledge_base(provider: str | None = None) -> KnowledgeBase:
    """Env-driven factory (`KB_PROVIDER`), default 'stub'. `curated`/`rag` are gated
    until built (ADR-006) — real grounding activation is a manual Bifola trigger."""
    provider = (provider or os.getenv("KB_PROVIDER", "stub")).lower()
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(f"unknown KB provider {provider!r} (expected one of {_KNOWN_PROVIDERS})")
    if provider == "stub":
        return EmptyKnowledgeBase()
    raise NotImplementedError(
        f"KB provider {provider!r} is not built yet (ADR-006: curated/rag are gated). "
        "The stub grounds nothing; real grounding awaits curated, cited benchmark data.")
