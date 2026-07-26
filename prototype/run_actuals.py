"""Demo: reconcile a real system's OBSERVED metrics against the engine's PREDICTIONS.

The audit-service + calibration-flywheel loop, offline and $0 (no LLM):
    build model -> simulate (engine predicts) -> load observed actuals ->
    reconcile (predicted vs observed) -> report "where reality diverges" + capture
    (predicted, observed) calibration pairs.

Observed actuals are read-only EVIDENCE — they never change an engine number
(prime directive); divergences are surfaced, never auto-resolved (ADR-004).

Run from prototype/:  python3 run_actuals.py
"""
from __future__ import annotations

import json
import os

from keystone.actuals import (observed_from_records, reconcile_observed,
                              render_actuals_section)
from keystone.audit_map import render_audit_map_html
from keystone.audit_report import render_audit_report
from keystone.blueprints import url_shortener
from keystone.simulation import simulate

HERE = os.path.dirname(__file__)
OBSERVED = os.path.join(HERE, "observed", "url_shortener_actuals.json")
REPORT = os.path.join(HERE, "outputs", "actuals_url_shortener_report.md")
AUDIT = os.path.join(HERE, "outputs", "audit_url_shortener_report.md")
AUDIT_MAP = os.path.join(HERE, "outputs", "audit_url_shortener_map.html")
CALIBRATION = os.path.join(HERE, "outputs", "calibration.jsonl")


def main() -> None:
    # 1. The model + the engine's prediction (the engine owns every number).
    model = url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)
    sim = simulate(model)

    # 2. Load the real system's observed metrics (a read-only export — no load generated).
    #    Reject NaN/Infinity JSON literals up front (untrusted input; they are not real
    #    measurements and would emit invalid strict-JSON into the calibration store).
    def _no_nonfinite(tok):
        raise ValueError(f"non-finite JSON literal {tok!r} in observed export")
    with open(OBSERVED) as f:
        observed = observed_from_records(json.load(f, parse_constant=_no_nonfinite))

    # 3. Reconcile: predicted vs observed, deterministically. Never auto-resolved.
    outcome = reconcile_observed(sim, observed)
    section = render_actuals_section(outcome)

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        f.write(section + "\n")

    # 3b. The full audit deliverable (exec summary + severity findings + non-guarantee disclaimer).
    with open(AUDIT, "w") as f:
        f.write(render_audit_report(model, sim, outcome) + "\n")

    # 3c. The SAME audit as an interactive map — nodes coloured by model-vs-observed divergence.
    with open(AUDIT_MAP, "w", encoding="utf-8") as f:
        f.write(render_audit_map_html(model, sim, outcome) + "\n")

    # 4. Capture (predicted, observed) pairs — the L0→L1 calibration flywheel seed.
    #    The demo TRUNCATES (idempotent re-runs — no double-counting a window); a real
    #    calibration store is the caller's responsibility (append with a run-id + dedup).
    pairs = outcome.calibration_pairs()
    with open(CALIBRATION, "w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")

    print("=" * 74)
    print(f"KEYSTONE — Model vs observed reality  ({model.name})")
    print("=" * 74)
    print(f"Observed metrics : {len(observed)} (source: read-only export, no load generated)")
    print(f"  matched        : {len(outcome.matched)}")
    print(f"  diverged       : {len(outcome.diverged)}  (hard: {len(outcome.hard_divergences)})")
    print(f"  not predicted  : {len(outcome.no_prediction)}")
    print("-" * 74)
    for r in outcome.diverged:
        arrow = "⛔ HARD" if r.severity == "hard" else "⚠ soft"
        gap = f"{r.gap_ratio * 100:+.0f}%" if r.gap_ratio is not None else "gap n/a"
        print(f"  {arrow}  {r.observed.component_id or '(system)'} / {r.observed.metric}: "
              f"predicted {r.predicted:g}, observed {r.observed.value:g} ({gap})")
    print("-" * 74)
    print(f"Calibration pairs captured: {len(pairs)} -> outputs/{os.path.basename(CALIBRATION)} "
          "(the L0→L1 flywheel seed)")
    print(f"Full section -> outputs/{os.path.basename(REPORT)}")
    print(f"Audit report  -> outputs/{os.path.basename(AUDIT)}  (the client deliverable)")
    print(f"Audit map     -> outputs/{os.path.basename(AUDIT_MAP)}  (interactive — open in a browser)")
    print("\nNOTE: observed values are evidence only — no engine number was changed "
          "(prime directive); divergences are surfaced for review, never auto-resolved.")


if __name__ == "__main__":
    main()
