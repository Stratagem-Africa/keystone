"""The real `ModelStore` backend (ADR-005 §7) — talks to Postgres via Supabase's PostgREST
client, exactly the way `prototype/api/jobs.py` already does. Lazily imported by
`model_store.make_model_store()` only when `STORE_PROVIDER=supabase`, so importing
`keystone.model_store` (or the engine package generally) never pulls the `supabase` package.

Deliberately does NOT copy `jobs.py`'s write-to-memory-first / degrade-to-Postgres-best-effort
/ swallow-every-exception pattern. ADR-005 §6 requires `save_model` to be fail-closed: an
invalid model must never be stored as a runnable version, and a save that "looked like" it
worked but silently didn't would defeat the entire point of a versioned store. Every method
here lets exceptions propagate.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import datetime

from keystone.ingestion import validate_model
from keystone.model import (
    Assumption,
    Component,
    ComponentKind,
    Flow,
    FlowStep,
    PricingRates,
    SystemModel,
    Workload,
)
from keystone.model_store import (
    DeletionResult,
    ModelDiff,
    Project,
    VersionMeta,
    _diff_models,
    _validate_for_persistence,
)
from keystone.provenance import Citation, Grounding

logger = logging.getLogger(__name__)


class StorageNotConfiguredError(Exception):
    """Raised by `_purge_storage_objects` — see its docstring. Caught by `delete_project`,
    never allowed to abort the DB-row purge (ADR-005 §5: erasure of a user's DB data must
    not be held hostage by an unrelated Storage-plumbing gap)."""


def _serialize_groundings(groundings: dict[str, Grounding]) -> dict:
    # Explicit float() on value/confidence_low/confidence_high, not relying on however
    # Postgres's jsonb happens to format a number on the way in — this is what actually
    # makes the int-vs-float fidelity ADR-005 §6a requires hold, regardless of jsonb's
    # internal behaviour (unverifiable from this sandbox; this makes it a non-issue either way).
    return {
        metric: {
            "value": float(g.value),
            "unit": g.unit,
            "confidence_low": float(g.confidence_low),
            "confidence_high": float(g.confidence_high),
            "citations": [asdict(c) for c in g.citations],
            "provenance": g.provenance,
            "measured_context": g.measured_context,
        }
        for metric, g in groundings.items()
    }


def _deserialize_groundings(data: dict | None) -> dict[str, Grounding]:
    return {
        metric: Grounding(
            value=float(g["value"]),
            unit=g["unit"],
            confidence_low=float(g["confidence_low"]),
            confidence_high=float(g["confidence_high"]),
            citations=tuple(Citation(**c) for c in g.get("citations", [])),
            provenance=g.get("provenance", "GROUNDED"),
            measured_context=g.get("measured_context", ""),
        )
        for metric, g in (data or {}).items()
    }


def _serialize_component(c: Component) -> dict:
    return {
        "id": c.id,
        "kind": c.kind.value,
        "name": c.name,
        "per_instance_rps": c.per_instance_rps,
        "instances": c.instances,
        "base_latency_ms": c.base_latency_ms,
        "monthly_cost_per_instance": c.monthly_cost_per_instance,
        "egress_gb_per_month": c.egress_gb_per_month,
        "storage_gb": c.storage_gb,
        "requests_per_month": c.requests_per_month,
        "llm_input_tokens_per_month": c.llm_input_tokens_per_month,
        "llm_output_tokens_per_month": c.llm_output_tokens_per_month,
        "provenance": c.provenance,
        "groundings": _serialize_groundings(c.groundings),
        "match_context": c.match_context,
    }


def _component_from_row(row: dict) -> Component:
    return Component(
        id=row["id"],
        kind=ComponentKind(row["kind"]),
        name=row["name"],
        per_instance_rps=float(row["per_instance_rps"]),
        instances=int(row["instances"]),
        base_latency_ms=float(row["base_latency_ms"]),
        monthly_cost_per_instance=int(row["monthly_cost_per_instance"]),
        egress_gb_per_month=int(row["egress_gb_per_month"]),
        storage_gb=int(row["storage_gb"]),
        requests_per_month=int(row["requests_per_month"]),
        llm_input_tokens_per_month=int(row["llm_input_tokens_per_month"]),
        llm_output_tokens_per_month=int(row["llm_output_tokens_per_month"]),
        provenance=row["provenance"],
        groundings=_deserialize_groundings(row.get("groundings")),
        match_context=row.get("match_context") or {},
    )


def _group_and_sort_steps(step_rows: list[dict]) -> dict[str, list[dict]]:
    """Grouped and sorted in Python, not relying on a single SQL ORDER BY to interleave a
    two-level structure correctly: step_order resets to 0 for EACH flow, so a global ORDER
    BY step_order alone would not reproduce each flow's own path order. Shared by
    `SupabaseModelStore.get_model` and `db_test_model_store_roundtrip.py`'s raw-SQL
    reconstruction, which operates on the identical row shape."""
    steps_by_flow: dict[str, list[dict]] = {}
    for row in step_rows:
        steps_by_flow.setdefault(row["flow_id"], []).append(row)
    for rows in steps_by_flow.values():
        rows.sort(key=lambda r: r["step_order"])
    return steps_by_flow


def _build_save_payload(model: SystemModel, project: Project) -> dict:
    return {
        "p_project_id": project.id,
        "p_name": model.name,
        "p_domain_flags": model.domain_flags,
        "p_system_rps": model.workload.system_rps,
        "p_workload_description": model.workload.description,
        "p_egress_micro_usd_per_gb": model.pricing.egress_micro_usd_per_gb,
        "p_storage_micro_usd_per_gb_month": model.pricing.storage_micro_usd_per_gb_month,
        "p_request_micro_usd_per_thousand": model.pricing.request_micro_usd_per_thousand,
        "p_llm_input_micro_usd_per_1k_tokens": model.pricing.llm_input_micro_usd_per_1k_tokens,
        "p_llm_output_micro_usd_per_1k_tokens": model.pricing.llm_output_micro_usd_per_1k_tokens,
        "p_compute_pricing": model.pricing.compute_pricing,
        "p_pricing_groundings": _serialize_groundings(model.pricing.groundings),
        "p_components": [_serialize_component(c) for c in model.components.values()],
        "p_flows": [
            {
                "name": f.name,
                "share": f.share,
                "path": [
                    {"component_id": s.component_id, "visit_prob": s.visit_prob}
                    for s in f.path
                ],
            }
            for f in model.flows
        ],
        "p_assumptions": [
            {
                "subject": a.subject,
                "statement": a.statement,
                "confidence": a.confidence,
                "source": a.source,
                "provenance": a.provenance,
            }
            for a in model.assumptions
        ],
    }


class SupabaseModelStore:
    """Constructed PER REQUEST, never shared/cached — same rule `jobs.py:_client_for`
    documents: mutating a shared client's auth token would race between concurrent
    requests, risking one user's rows leaking to another mid-flight."""

    def __init__(self, access_token: str) -> None:
        # This client-bootstrap sequence duplicates jobs.py:_client_for's construction
        # steps (env lookup, lazy import, create_client, .postgrest.auth) rather than
        # sharing a helper — flagged by independent review as a reuse opportunity, not
        # done here: jobs.py's version is inseparably wrapped in its own try/except
        # (graceful-degrade-to-memory), which this class must NOT inherit (fail-closed is
        # the whole point, see the module docstring), so factoring out a shared helper
        # would mean touching api/jobs.py (working, already-merged code) to split
        # construction from error-handling — real but small scope for a fast-follow, not
        # bundled into this PR.
        from supabase import create_client   # lazy — keeps `db` extra out of the base install
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_ANON_KEY"]
        self._client = create_client(url, key)
        self._client.postgrest.auth(access_token)   # every call as THIS caller's own JWT — RLS stays in force

    def save_model(self, project: Project, model: SystemModel) -> int:
        validate_model(model)              # simulatable? -- fail closed BEFORE any network call
        _validate_for_persistence(model)   # saveable? (see that function's docstring)
        payload = _build_save_payload(model, project)
        result = self._client.rpc("keystone_save_system_model", payload).execute()
        data = result.data
        # PostgREST's exact wire shape for a scalar `returns int` function's response is
        # unverified from this sandbox (no live Supabase project reachable here) — handle
        # a bare int, a list/dict-wrapped one, AND an empty list (an unexpected-but-not-
        # impossible response shape a bare data[0] would crash on with a confusing
        # IndexError instead of a clear "the save failed" signal) defensively; confirm/
        # simplify against a real project before trusting this as final.
        if isinstance(data, list):
            if not data:
                raise RuntimeError(
                    "keystone_save_system_model returned no data — the save may not have "
                    "actually committed; check Postgres logs before retrying"
                )
            data = data[0]
        if isinstance(data, dict):
            data = data.get("keystone_save_system_model", data)
        return int(data)

    def get_model(self, project: Project, version: int | str = "head") -> SystemModel:
        # KNOWN v1 characteristic, not fixed here (flagged by independent review): this
        # makes up to 6 sequential PostgREST round-trips (project, system_model, component,
        # flow, flow_step, assumption) where the last 5 have no data dependency on each
        # other and could in principle run concurrently or be combined into a single read
        # RPC mirroring save_model's write RPC. Not built here — a read-side RPC is a
        # meaningfully bigger design addition than anything Milestone 4/5 actually asks
        # for, and no requirement in the issue text calls for it. Revisit if this becomes a
        # real bottleneck, same "smallest correct thing first" call ADR-005's own "Data
        # engineer" dissent made about snapshot duplication.
        if version == "head":
            head = (
                self._client.table("project")
                .select("head_model_version")
                .eq("id", project.id)
                .single()
                .execute()
            )
            version = head.data["head_model_version"]
            if version is None:
                # head_model_version is NULL until the first save_model() call (0001) —
                # without this check, the .eq("version", None) query below silently
                # matches nothing and PostgREST's .single() raises an opaque "0 rows"
                # error instead of a clean, actionable message.
                raise KeyError(f"no versions saved for project {project.id!r}")

        sm = (
            self._client.table("system_model")
            .select("*")
            .eq("project_id", project.id)
            .eq("version", version)
            .single()
            .execute()
        ).data

        components = (
            self._client.table("component")
            .select("*")
            .eq("project_id", project.id)
            .eq("model_version", version)
            .order("component_order")   # matches flow_order/assumption_order below — without
            # it a reload can reorder components, and the engine reports the bottleneck by
            # iterating this order (Bifola's PR #198 review, 2026-09-14).
            .execute()
        ).data

        flow_rows = (
            self._client.table("flow")
            .select("*")
            .eq("project_id", project.id)
            .eq("model_version", version)
            .order("flow_order")
            .execute()
        ).data

        step_rows = (
            self._client.table("flow_step")
            .select("*")
            .eq("project_id", project.id)
            .eq("model_version", version)
            .execute()
        ).data
        steps_by_flow = _group_and_sort_steps(step_rows)

        assumption_rows = (
            self._client.table("assumption")
            .select("*")
            .eq("project_id", project.id)
            .eq("model_version", version)
            .order("assumption_order")
            .execute()
        ).data

        return SystemModel(
            name=sm["name"],
            components={row["id"]: _component_from_row(row) for row in components},
            flows=[
                Flow(
                    name=row["name"],
                    share=float(row["share"]),
                    path=[
                        FlowStep(component_id=s["component_id"], visit_prob=float(s["visit_prob"]))
                        for s in steps_by_flow.get(row["id"], [])
                    ],
                )
                for row in flow_rows
            ],
            workload=Workload(
                system_rps=float(sm["system_rps"]), description=sm["workload_description"]
            ),
            assumptions=[
                Assumption(
                    subject=row["subject"],
                    statement=row["statement"],
                    confidence=row["confidence"],
                    source=row["source"],
                    provenance=row["provenance"],
                )
                for row in assumption_rows
            ],
            domain_flags=sm.get("domain_flags") or [],
            pricing=PricingRates(
                egress_micro_usd_per_gb=int(sm["egress_micro_usd_per_gb"]),
                storage_micro_usd_per_gb_month=int(sm["storage_micro_usd_per_gb_month"]),
                request_micro_usd_per_thousand=int(sm["request_micro_usd_per_thousand"]),
                llm_input_micro_usd_per_1k_tokens=int(sm["llm_input_micro_usd_per_1k_tokens"]),
                llm_output_micro_usd_per_1k_tokens=int(sm["llm_output_micro_usd_per_1k_tokens"]),
                compute_pricing=sm["compute_pricing"],
                groundings=_deserialize_groundings(sm.get("pricing_groundings")),
            ),
        )

    def list_versions(self, project: Project) -> list[VersionMeta]:
        rows = (
            self._client.table("system_model")
            .select("version, parent_version, name, created_at")
            .eq("project_id", project.id)
            .order("version")
            .execute()
        ).data
        return [
            VersionMeta(
                version=r["version"],
                parent_version=r["parent_version"],
                name=r["name"],
                # PostgREST returns timestamptz as an ISO string, not a datetime object —
                # parse it so this matches VersionMeta's declared type (and StubModelStore's
                # actual behaviour). .replace("Z", "+00:00"): Python 3.10 (this project's
                # floor, CLAUDE.md) doesn't accept a bare "Z" suffix in fromisoformat().
                created_at=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
            )
            for r in rows
        ]

    def diff(self, project: Project, v1: int, v2: int) -> ModelDiff:
        return _diff_models(v1, v2, self.get_model(project, v1), self.get_model(project, v2))

    def delete_project(self, project: Project) -> DeletionResult:
        # Collecting the Storage/R2 pointers and deleting the project row must happen in ONE
        # transaction, not two separate PostgREST calls: `source_document` cascades on
        # `project` delete (0001), so a plain `.table("source_document").select(...)` followed
        # by a separate `.table("project").delete(...)` leaves a real window where a
        # source_document inserted between the two calls gets cascade-deleted without ever
        # being read — silently orphaning whatever Storage/R2 object it pointed at, with no
        # record that it needed purging (found by independent review). `keystone_delete_project`
        # (0006) does both inside one function call = one implicit transaction, same reason
        # 0004 needed an RPC for save_model.
        result = self._client.rpc(
            "keystone_delete_project", {"p_project_id": project.id}
        ).execute()
        data = result.data
        # Same defensive unwrap as save_model's response handling (PostgREST's exact wire
        # shape for a scalar-returning RPC is unverified from this sandbox) — INCLUDING the
        # dict-keyed-by-function-name case save_model guards against (a second independent
        # review caught that the first version of this method only handled the list-wrapped
        # case), AND matching save_model's fail-CLOSED handling of an empty/malformed
        # response (a THIRD independent review caught that the first version of this method
        # silently coerced an empty/anomalous response into `project_deleted=False` —
        # indistinguishable from a legitimate "not your project" no-op, which the RPC always
        # returns as a well-formed object, never an empty one — masking a real failure as a
        # successful-looking erasure that may not have actually run).
        if isinstance(data, list):
            if not data:
                raise RuntimeError(
                    "keystone_delete_project returned no data — the deletion may not have "
                    "actually run; check Postgres logs before retrying"
                )
            data = data[0]
        if isinstance(data, dict):
            data = data.get("keystone_delete_project", data)
        if not isinstance(data, dict):
            raise RuntimeError(f"keystone_delete_project returned an unexpected shape: {data!r}")
        # The RPC ALWAYS returns both keys with these exact types (0006's jsonb_build_object),
        # so anything else is a malformed response, not a "nothing happened" no-op. Bifola's
        # PR #200 review showed the earlier `.get(..., False)` / `bool(...)` / `list(...)`
        # failed OPEN for dict-shaped junk: `{}` -> project_deleted=False (identical to a
        # legitimate "not your project"), `"false"` -> True (truthy string), and a string uri
        # -> a list of its characters.
        deleted = data.get("project_deleted")
        uris = data.get("source_document_uris")
        if (
            not isinstance(deleted, bool)
            or not isinstance(uris, list)
            or not all(isinstance(u, str) for u in uris)
        ):
            # The RPC has ALREADY run by the time we parse its reply, so the project may be
            # gone and its source_document rows cascade-deleted. The raw response is embedded
            # deliberately: if it carries uris, this message is the only place they survive.
            raise RuntimeError(
                "keystone_delete_project returned a malformed response — the deletion may "
                "ALREADY have committed, so do not blindly retry, and treat the raw response "
                f"below as the only record of any Storage uris: {data!r} — expected "
                "{'project_deleted': bool, 'source_document_uris': [str, ...]}"
            )

        storage_purged = 0
        storage_errors: list[str] = []
        unpurged_uris: list[str] = []
        if uris:
            # Broad except is deliberate, not lazy: this call must NEVER block the DB-row
            # erasure above (already committed by the time we get here) — a real Storage/R2
            # implementation can fail in ways this file can't enumerate (network timeout,
            # bucket permission error, vendor SDK exception), and every one of them must be
            # recorded as a gap, not allowed to look like the whole deletion failed when the
            # part that actually matters (the user's DB rows) already succeeded.
            try:
                storage_purged = self._purge_storage_objects(uris)
            except Exception as exc:
                storage_errors.append(str(exc))
                # The source_document rows are already gone (cascade), so these strings
                # exist nowhere else — keep ALL of them (an exception can't tell us which
                # were purged before it fired) and log them so they survive even if the
                # caller drops the result. Durable fix (a purge-queue table written in the
                # same transaction as the delete) belongs with Epic 5.3.
                unpurged_uris = list(uris)
                logger.warning(
                    "project %s deleted but %d Storage object(s) were NOT purged and no "
                    "source_document row remains to record them: %s",
                    project.id, len(unpurged_uris), unpurged_uris,
                )

        return DeletionResult(
            project_deleted=deleted,
            storage_objects_found=len(uris),
            storage_objects_purged=storage_purged,
            storage_purge_errors=storage_errors,
            unpurged_uris=unpurged_uris,
        )

    def _purge_storage_objects(self, uris: list[str]) -> int:
        """GAP (ADR-005 §5; issue #21, Epic 5.3 — docs/08-Work-Breakdown.md): no Storage/R2
        client exists anywhere in this repo, and it is not yet decided WHICH vendor a real
        upload would even land in — `.env.example` only scaffolds `R2_*` vars, but
        `source_document.uri`'s own schema comment (0001) hedges between "Storage/R2"
        without picking one, and nothing writes a `source_document` row today (`ingestion.py`
        never persists; `api/main.py`'s upload handler reads bytes in-memory only). Guessing
        at either vendor's API here would mean shipping a call that's never been run against
        anything real — worse than an honest gap, since it would look done without being
        verified. This is deliberately the seam a real implementation plugs into once that
        choice is made (posted to Bifola on #21) and Epic 5.3 actually writes an object
        somewhere: same shape as `save_model`'s `.rpc(...)` call, or an S3-compatible client
        for R2, calling out to whichever bucket `uris` point at."""
        raise StorageNotConfiguredError(
            f"{len(uris)} source_document object(s) were not purged from Storage: no "
            "Storage/R2 client is configured (see ADR-005 §5 / issue #21 Epic 5.3)."
        )
