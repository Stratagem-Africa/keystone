"""Audit map — the interactive architecture map overlaid with model-vs-observed divergence.

The stress-test / audit deliverable as a *spatial* view: `build_audit_map(model, sim, outcome)` takes
the base architecture map (`keystone.arch_map`) and colours each node by how the OBSERVED reality
reconciles with the engine's PREDICTION — matched (green) / soft divergence (amber) / hard divergence
(red) / not-compared (grey). It answers "where does my running system diverge from the design?"
spatially, which a markdown table cannot.

The divergence overlay is plain data injected into the map dict, so `arch_map` itself never imports the
actuals layer (the structural prime-directive guard, `test_actuals.py::TestBoundaryGuard`) and stays a
pure engine view. This module is a deliverable — like `audit_report.py`, it may read the actuals layer.

Prime directive: observed values are read-only EVIDENCE; they never become an engine number and the
reconciliation is never auto-resolved (ADR-004). This reads `sim` + the already-computed
`ActualsReconciliation` and produces no number of its own. Deterministic + offline.
"""
from __future__ import annotations

from keystone.actuals import DIVERGE, MATCH, ActualsReconciliation
from keystone.arch_map import _json_safe, build_arch_map, render_html
from keystone.audit_report import _overall


def _node_status(rows: list) -> tuple[str, float | None]:
    """A node's overall divergence status (worst verdict wins) + a representative gap for its badge.
    hard > soft > matched > not_compared (unit-mismatch / not-predicted) > not_observed (no rows)."""
    hard = [r for r in rows if r.verdict == DIVERGE and r.severity == "hard"]
    soft = [r for r in rows if r.verdict == DIVERGE and r.severity != "hard"]
    matched = [r for r in rows if r.verdict == MATCH]
    if hard:
        return "hard", hard[0].gap_ratio
    if soft:
        return "soft", soft[0].gap_ratio
    if matched:
        return "matched", matched[0].gap_ratio
    if rows:                      # only UNIT_MISMATCH / NO_PREDICTION — supplied but not comparable
        return "not_compared", None
    return "not_observed", None   # no observation targeted this component


def _row_dict(r) -> dict:
    o = r.observed
    return {"metric": o.metric, "observed": o.value, "predicted": r.predicted,
            "gap_ratio": r.gap_ratio, "unit": o.unit, "verdict": r.verdict,
            "severity": r.severity, "source": o.source, "note": r.note}


def build_audit_map(model, sim, outcome: ActualsReconciliation) -> dict:
    """The base architecture map enriched with a model-vs-observed divergence overlay. Deterministic;
    observed data is evidence-only and never feeds a number back into the engine (prime directive)."""
    arch = build_arch_map(model, sim)
    node_ids = {n["id"] for n in arch["nodes"]}
    by_comp: dict[str, list] = {}
    unmatched: list[dict] = []
    for r in outcome.rows:
        cid = r.observed.component_id
        if cid is not None and cid in node_ids:
            by_comp.setdefault(cid, []).append(r)
        else:                     # system-level (component_id None) or a component not in the model
            unmatched.append({"component_id": cid, "metric": r.observed.metric,
                              "verdict": r.verdict, "note": r.note})
    for n in arch["nodes"]:
        rows = by_comp.get(n["id"], [])
        status, gap = _node_status(rows)
        n["divergence"] = {"status": status, "gap": gap, "rows": [_row_dict(r) for r in rows]}
    arch["audit_unmatched"] = unmatched
    arch["meta"]["audit"] = {
        "matched": len(outcome.matched),
        "diverged": len(outcome.diverged),
        "hard": len(outcome.hard_divergences),
        "unit_mismatch": len(outcome.unit_mismatched),
        "no_prediction": len(outcome.no_prediction),
        "observed_count": len(outcome.rows),
        "overall": _overall(outcome),
        # True only when the map reads as a pass (things matched, nothing diverged) — the renderer then
        # shows the "a match is NOT a guarantee of correctness" caveat exactly where the false-pass risk is.
        "reads_as_pass": len(outcome.diverged) == 0 and len(outcome.matched) > 0,
    }
    # Re-sanitise: the overlay fields were added after build_arch_map's own pass, so fold any non-finite
    # (e.g. a None-safe gap) to JSON-safe here too — render_html dumps with allow_nan=False (fail closed).
    return _json_safe(arch)


def render_audit_map_html(model, sim, outcome: ActualsReconciliation) -> str:
    """Render the audit map to a self-contained interactive HTML page (reuses arch_map's renderer)."""
    return render_html(build_audit_map(model, sim, outcome))
