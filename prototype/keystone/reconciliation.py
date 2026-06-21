"""Cross-document reconciliation (ADR-004; Doc 04 F2): merge N partial models → one.

The differentiator most tools skip. Takes the partial `SystemModel`s ingested from a
document corpus and merges them into one canonical model, emitting a Reconciliation
Report of **conflicts**, **gaps**, and **duplications**. The hard rule (Doc 04 F2 MUST):

  - HALT at unresolved HARD conflicts — never design on a contradiction.
  - NEVER auto-resolve — conflicts are shown side-by-side for the user to choose.

v1 is DETERMINISTIC over the typed models (prose-level semantic conflicts are a v2 LLM
lever — ADR-004). It produces a model + a report, never an engine number. Fail-closed:
any hard conflict, an empty corpus, or a merged model that fails validation returns
`halted=True` with no model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from keystone.ingestion import IngestError, IngestResult, orphan_components, validate_model
from keystone.model import Assumption, SystemModel, Workload


@dataclass
class Conflict:
    subject: str
    kind: str                 # component-kind | component-params | workload | flow-merge | invalid
    a_ref: str
    a_value: str
    b_ref: str
    b_value: str
    severity: str             # hard | soft


@dataclass
class Gap:
    subject: str
    statement: str


@dataclass
class Duplication:
    a_id: str
    b_id: str
    kind: str
    note: str


@dataclass
class ReconciliationReport:
    conflicts: list[Conflict] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    duplications: list[Duplication] = field(default_factory=list)

    @property
    def hard_conflicts(self) -> list[Conflict]:
        return [c for c in self.conflicts if c.severity == "hard"]


@dataclass
class ReconciliationOutcome:
    model: SystemModel | None     # the merged canonical model, or None when halted
    report: ReconciliationReport
    halted: bool


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) >= 3}


def _similar(a: str, b: str) -> bool:
    """Best-effort name similarity: share a significant (>=3 char) token."""
    return bool(_tokens(a) & _tokens(b))


def _detect_gaps(model: SystemModel) -> list[Gap]:
    gaps: list[Gap] = []
    if model.workload.system_rps <= 0:
        gaps.append(Gap("workload", "no peak request rate (system_rps) was specified"))
    if not model.flows:
        gaps.append(Gap("flows", "no request flows were defined"))
    ids = set(model.components)
    for f in model.flows:
        for s in f.path:
            if s.component_id not in ids:
                gaps.append(Gap("flow", f"flow {f.name!r} references undefined component {s.component_id!r}"))
    return gaps


def reconcile(results: list[IngestResult]) -> ReconciliationOutcome:
    """Merge the partial models in `results` into one canonical model + report.
    Halts (model=None) on a hard conflict, an empty corpus, or an invalid merge."""
    models = [r.model for r in results]
    if not models:
        return ReconciliationOutcome(
            None, ReconciliationReport(gaps=[Gap("corpus", "no sources to reconcile")]), halted=True)

    # Single source: nothing to reconcile; pass it through (still fail-closed validated).
    if len(models) == 1:
        m = models[0]
        try:
            validate_model(m)
        except IngestError as e:
            return ReconciliationOutcome(
                None, ReconciliationReport(conflicts=[Conflict("merged-model", "invalid", "validation",
                str(e), "-", "-", "hard")]), halted=True)
        return ReconciliationOutcome(m, ReconciliationReport(gaps=_detect_gaps(m)), halted=False)

    conflicts: list[Conflict] = []
    duplications: list[Duplication] = []
    merged_components: dict = {}
    hard = False

    # --- component reconciliation: union by id; detect kind (hard) + param (soft) conflicts
    by_id: dict[str, list[tuple[int, object]]] = {}
    for i, m in enumerate(models):
        for cid, c in m.components.items():
            by_id.setdefault(cid, []).append((i, c))

    for cid, occ in by_id.items():
        first = occ[0][1]
        kinds = {c.kind for _, c in occ}
        if len(kinds) > 1:
            other = next(o for o in occ if o[1].kind != first.kind)
            conflicts.append(Conflict(
                subject=cid, kind="component-kind", a_ref=f"source {occ[0][0]+1}",
                a_value=first.kind.value, b_ref=f"source {other[0]+1}", b_value=other[1].kind.value,
                severity="hard"))
            hard = True
        else:
            for idx, c in occ[1:]:
                sig_a = (first.per_instance_rps, first.instances, first.base_latency_ms, first.monthly_cost_per_instance)
                sig_b = (c.per_instance_rps, c.instances, c.base_latency_ms, c.monthly_cost_per_instance)
                if sig_a != sig_b:
                    conflicts.append(Conflict(
                        subject=cid, kind="component-params", a_ref=f"source {occ[0][0]+1}",
                        a_value=f"{first.per_instance_rps:g} rps/inst x{first.instances}",
                        b_ref=f"source {idx+1}", b_value=f"{c.per_instance_rps:g} rps/inst x{c.instances}",
                        severity="soft"))
                    break
        merged_components[cid] = first   # keep the first; any divergence is FLAGGED, never silently merged

    # --- duplication detection: same kind, different id, similar name, ACROSS sources
    flat = [(i, cid, c) for i, m in enumerate(models) for cid, c in m.components.items()]
    seen_pairs: set[tuple[str, str]] = set()
    for a in range(len(flat)):
        for b in range(a + 1, len(flat)):
            (ia, ida, ca), (ib, idb, cb) = flat[a], flat[b]
            pair = tuple(sorted((ida, idb)))
            if ia != ib and ida != idb and ca.kind == cb.kind and _similar(ca.name, cb.name) and pair not in seen_pairs:
                seen_pairs.add(pair)
                duplications.append(Duplication(a_id=ida, b_id=idb, kind=ca.kind.value,
                                                note=f"{ca.name!r} (source {ia+1}) ~ {cb.name!r} (source {ib+1})"))

    # HARD conflict -> halt; never design on a contradiction (Doc 04 F2 MUST).
    if hard:
        return ReconciliationOutcome(
            None, ReconciliationReport(conflicts, [], duplications), halted=True)

    # --- merge (no hard conflict) ---
    # workload: take the MAX stated rate (conservative), flag any divergence — never average away.
    rps_set = {round(m.workload.system_rps) for m in models}
    if len(rps_set) > 1:
        conflicts.append(Conflict(
            subject="workload.system_rps", kind="workload", a_ref="lowest", a_value=f"{min(rps_set):,}",
            b_ref="highest", b_value=f"{max(rps_set):,}", severity="soft"))
    merged_rps = max(m.workload.system_rps for m in models)

    # flows: use the richest model's flows (most components) as primary; flag if others also
    # define flows (deterministic flow-merging across prose is a v2 lever, ADR-004).
    primary = max(models, key=lambda m: len(m.components))
    others_with_flows = sum(1 for m in models if m is not primary and m.flows)
    if others_with_flows:
        conflicts.append(Conflict(
            subject="flows", kind="flow-merge", a_ref="primary", a_value=f"{len(primary.flows)} flow(s)",
            b_ref="other sources", b_value=f"{others_with_flows} source(s) also define flows", severity="soft"))

    domain_flags = sorted({f for m in models for f in m.domain_flags})
    assumptions: list[Assumption] = [a for m in models for a in m.assumptions]
    assumptions.append(Assumption(
        subject="reconciliation", source="user", confidence="med", provenance="ASSUMPTION",
        statement=f"Merged from {len(models)} sources; any soft conflicts are kept side-by-side for "
                  f"the user to resolve (never auto-resolved)."))

    merged = SystemModel(
        name=primary.name, components=merged_components, flows=primary.flows,
        workload=Workload(system_rps=merged_rps, description=f"reconciled from {len(models)} sources"),
        assumptions=assumptions, domain_flags=domain_flags)

    gaps = _detect_gaps(merged)

    # A component contributed by a source whose flows were NOT merged is left unwired
    # (flow-merge across prose is a v2 lever, ADR-004). The engine would silently report it
    # at 0% utilisation, so surface each orphan as a SOFT conflict — visible to the user,
    # never auto-dropped — rather than hard-halting the otherwise-valid merge.
    for cid in orphan_components(merged):
        conflicts.append(Conflict(
            subject=cid, kind="unwired-component", a_ref="merged model",
            a_value="on no flow (engine would show a misleading 0% utilisation)",
            b_ref="resolve", b_value="wire it into a flow or drop it; flow-merge is a v2 lever (ADR-004)",
            severity="soft"))

    try:
        # Orphans are flagged above as soft conflicts, so don't let them hard-halt the merge.
        validate_model(merged, require_connected=False)   # fail closed on every OTHER structural fault
    except IngestError as e:
        conflicts.append(Conflict("merged-model", "invalid", "validation", str(e), "-", "-", "hard"))
        return ReconciliationOutcome(None, ReconciliationReport(conflicts, gaps, duplications), halted=True)

    return ReconciliationOutcome(merged, ReconciliationReport(conflicts, gaps, duplications), halted=False)


def render_reconciliation_report(outcome: ReconciliationOutcome) -> str:
    r = outcome.report
    L: list[str] = ["# Reconciliation Report", ""]
    if outcome.halted:
        L.append("> ⛔ **HALTED — unresolved hard conflict(s).** Keystone does not design on a "
                 "contradiction; resolve the conflicts below, then re-run. No merged model was produced.")
    else:
        L.append("> ✅ Merged into one canonical model. Soft conflicts are listed below and kept "
                 "side-by-side — **review them; nothing was auto-resolved.**")
    L.append("")
    L.append(f"## Conflicts ({len(r.conflicts)})")
    if r.conflicts:
        L.append("")
        L.append("| Severity | Subject | A | B |")
        L.append("|---|---|---|---|")
        for c in r.conflicts:
            L.append(f"| {c.severity.upper()} | {c.subject} ({c.kind}) | {c.a_ref}: {c.a_value} | {c.b_ref}: {c.b_value} |")
    else:
        L.append("\n_none_")
    L.append("")
    L.append(f"## Gaps ({len(r.gaps)})")
    L.append("")
    L.extend(f"- {g.subject}: {g.statement}" for g in r.gaps) if r.gaps else L.append("_none_")
    L.append("")
    L.append(f"## Possible duplications ({len(r.duplications)})")
    L.append("")
    L.extend(f"- {d.a_id} ↔ {d.b_id} ({d.kind}): {d.note}" for d in r.duplications) if r.duplications else L.append("_none_")
    L.append("")
    return "\n".join(L)
