"""Observed-actuals reconciliation (the audit-service + L0→L1 calibration seam).

Lets a real system's **observed** metrics (measured RPS, p99, utilisation, …) enter
Keystone as EVIDENCE and be compared, deterministically, against what the engine
PREDICTED for the same model. It answers "where does your running reality diverge
from your design model?" — the core finding of an expert stress-test/audit — and it
captures each (predicted, observed) pair as calibration data (the L0→L1 flywheel, the
moat in docs/07).

Invariants (this is trust-critical):
  - **Prime directive:** an observed number is an INPUT/evidence, never an engine
    output. This module only READS an already-computed `SimulationResult`; it never
    constructs or mutates a `Metric`, and never feeds a number back into the engine.
    The engine stays the sole producer of the predicted numbers.
  - **Never auto-resolve (ADR-004 ethos):** a divergence is SURFACED side-by-side
    (predicted vs observed + the gap), never silently reconciled or used to "correct"
    the model. A hard divergence is flagged prominently for the human reviewer.
  - **Honesty:** every observed value carries its provenance (source + measurement
    window + context); a metric the engine did not predict is flagged NO_PREDICTION,
    never dropped or faked.
  - **Read-only:** actuals arrive from a file/export — NO load is generated against
    the user's system (that is a v2 concern). This module is pure + deterministic.

Real external-client actuals are commercially sensitive → gated on the model store's
tenant-isolation MUST (#21) before any multi-tenant upload; single-user/offline runs
(the demo) need none of that.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from keystone.simulation import SimulationResult

# Numeric component fields on `ComponentResult` an observation can target (saturated is
# a bool, not a magnitude — excluded). System-level targets resolve against sim.metrics.
_COMPONENT_FIELDS = frozenset({"arrival_rps", "capacity_rps", "utilization", "mean_latency_ms"})

# The engine unit each metric is expressed in — so an observation supplied in the WRONG
# unit (e.g. utilisation as "72"% vs the engine's 0.72 ratio) is FLAGGED, never silently
# compared or auto-converted (auto-conversion could hide a real error — honesty).
_ENGINE_UNIT = {
    "arrival_rps": "rps", "capacity_rps": "rps", "utilization": "ratio",
    "mean_latency_ms": "ms",
    "bottleneck_utilization": "ratio", "breakpoint_rps_safe": "rps",
    "breakpoint_rps_theoretical": "rps", "p50_ms": "ms", "p95_ms": "ms", "p99_ms": "ms",
    "monthly_cost": "usd_minor_per_month",
}

MATCH, DIVERGE, NO_PREDICTION = "MATCH", "DIVERGE", "NO_PREDICTION"


@dataclass(frozen=True)
class Observation:
    """One number MEASURED from a real running system — evidence, never an engine output.

    Deliberately NOT named 'Metric': a `Metric` is an engine-authored output (only
    simulation.py may build one, ADR-007); an Observation is external evidence compared
    against one. Keeping the names distinct keeps the prime-directive boundary crisp.

    `component_id` names the component to compare against (`None` = a system-level metric
    such as p99_ms). `metric` is the field/key. Provenance is mandatory: a measurement
    with no source/window is not evidence."""
    metric: str
    value: float
    unit: str
    source: str                 # where it came from, e.g. "Datadog export"
    window: str                 # measurement window, e.g. "2026-07-01..14, peak hour"
    component_id: str | None = None
    context: str = ""           # optional: hardware/workload the measurement ran on


@dataclass(frozen=True)
class PredictionVsActual:
    """One observed metric set beside the engine's prediction for the same thing."""
    observed: Observation
    predicted: float | None     # the engine's predicted value (None = engine did not predict it)
    gap_ratio: float | None     # (observed - predicted) / predicted, or None if not computable
    verdict: str                # MATCH | DIVERGE | NO_PREDICTION
    severity: str               # "hard" | "soft" | ""  (only set for DIVERGE)
    note: str


@dataclass
class ActualsReconciliation:
    """The deterministic comparison outcome — evidence for the reader, never a new number."""
    rows: list[PredictionVsActual] = field(default_factory=list)

    @property
    def diverged(self) -> list[PredictionVsActual]:
        return [r for r in self.rows if r.verdict == DIVERGE]

    @property
    def hard_divergences(self) -> list[PredictionVsActual]:
        return [r for r in self.rows if r.verdict == DIVERGE and r.severity == "hard"]

    @property
    def matched(self) -> list[PredictionVsActual]:
        return [r for r in self.rows if r.verdict == MATCH]

    @property
    def no_prediction(self) -> list[PredictionVsActual]:
        return [r for r in self.rows if r.verdict == NO_PREDICTION]

    def calibration_pairs(self) -> list[dict]:
        """(predicted, observed) pairs for the calibration store — the L0→L1 flywheel.
        Only rows the engine actually predicted; each keeps its provenance so a future
        calibration pass knows the measurement's context. Pure data (the caller persists)."""
        out = []
        for r in self.rows:
            if r.predicted is None:
                continue
            out.append({
                "component_id": r.observed.component_id, "metric": r.observed.metric,
                "predicted": r.predicted, "observed": r.observed.value,
                "gap_ratio": r.gap_ratio, "verdict": r.verdict,
                "source": r.observed.source, "window": r.observed.window,
                "context": r.observed.context,
            })
        return out


def observed_from_records(records: list) -> list[Observation]:
    """Parse a list of plain dicts (e.g. from a JSON export) into Observations, fail-closed.

    Required keys: metric, value, unit, source, window. Optional: component_id, context.
    A missing required field or a non-numeric value raises ValueError (untrusted input —
    never silently coerced). Kept pure (no file IO) so the trust-critical parse is testable;
    the demo/run script does the file read."""
    out: list[Observation] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ValueError(f"observed record {i} is not an object")
        try:
            value = rec["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"observed record {i}: 'value' must be a number, got {value!r}")
            out.append(Observation(
                metric=str(rec["metric"]), value=float(value), unit=str(rec["unit"]),
                source=str(rec["source"]), window=str(rec["window"]),
                component_id=(str(rec["component_id"]) if rec.get("component_id") is not None else None),
                context=str(rec.get("context", "")),
            ))
        except KeyError as e:
            raise ValueError(f"observed record {i} missing required field {e}") from e
    return out


def _predicted_value(sim: SimulationResult, o: Observation) -> float | None:
    """The engine's predicted value for an observation's target, or None if it predicted none.
    READ-ONLY — pulls from an already-computed result; never builds or mutates a number."""
    if o.component_id is not None:
        comp = sim.components.get(o.component_id)
        if comp is None or o.metric not in _COMPONENT_FIELDS:
            return None
        return float(getattr(comp, o.metric))
    m = sim.metrics.get(o.metric)
    return float(m.value) if m is not None else None


def reconcile_observed(sim: SimulationResult, observed: list[Observation], *,
                       tol: float = 0.15, hard_tol: float = 0.5) -> ActualsReconciliation:
    """Compare each observed metric to the engine's prediction. Deterministic; the engine
    result is only READ (the prime-directive boundary). A metric within `tol` (relative) is
    MATCH; beyond it DIVERGE (hard beyond `hard_tol`); one the engine did not predict is
    NO_PREDICTION. Nothing is auto-resolved — divergences are evidence for the human."""
    rows: list[PredictionVsActual] = []
    for o in observed:
        predicted = _predicted_value(sim, o)
        expected_unit = _ENGINE_UNIT.get(o.metric)
        unit_note = ""
        if expected_unit and o.unit != expected_unit:
            # Surface a probable unit mismatch (don't convert — that could hide a real error).
            unit_note = (f" [unit '{o.unit}' ≠ engine unit '{expected_unit}' — confirm the "
                         f"observation is in engine units before trusting the gap]")

        if predicted is None:
            where = (f"component {o.component_id!r} / field {o.metric!r}" if o.component_id
                     else f"system metric {o.metric!r}")
            rows.append(PredictionVsActual(
                o, None, None, NO_PREDICTION, "",
                f"engine produced no prediction for {where}"))
            continue

        if predicted <= 0:
            # No stable ratio at/through zero — compare absolutely, and say so.
            verdict = MATCH if abs(o.value - predicted) < 1e-9 else DIVERGE
            sev = ("soft" if verdict == DIVERGE else "")
            rows.append(PredictionVsActual(
                o, predicted, None, verdict, sev,
                "predicted is 0 — compared absolutely, not as a ratio" + unit_note))
            continue

        gap = (o.value - predicted) / predicted
        if abs(gap) <= tol:
            rows.append(PredictionVsActual(o, predicted, gap, MATCH, "",
                                           "within tolerance" + unit_note))
        else:
            sev = "hard" if abs(gap) > hard_tol else "soft"
            direction = "above" if gap > 0 else "below"
            rows.append(PredictionVsActual(
                o, predicted, gap, DIVERGE, sev,
                f"observed is {abs(gap) * 100:.0f}% {direction} the engine's prediction" + unit_note))
    return ActualsReconciliation(rows)


def render_actuals_section(outcome: ActualsReconciliation) -> str:
    """Markdown 'Model vs observed reality' section — the audit finding. Predicted vs observed
    side by side, divergences emphasised, provenance shown. Never asserts the observed value is
    correct — it reports the gap for the reviewer to judge."""
    rows = outcome.rows
    L: list[str] = ["## Model vs observed reality", ""]
    if not rows:
        L.append("_No observed metrics supplied._")
        return "\n".join(L)

    hard = outcome.hard_divergences
    if hard:
        L.append(f"> ⛔ **{len(hard)} HARD divergence(s)** — the running system is far from the "
                 "model here. Treat the design's numbers for these with suspicion until reconciled; "
                 "nothing was auto-corrected.")
    else:
        L.append(f"> {len(outcome.matched)} matched · {len(outcome.diverged)} diverged · "
                 f"{len(outcome.no_prediction)} not predicted. Observed values are evidence, "
                 "not corrections — the engine's numbers are unchanged.")
    L.append("")
    L.append("| Target | Metric | Predicted | Observed | Gap | Verdict | Provenance |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rows:
        o = r.observed
        target = o.component_id or "(system)"
        pred = "—" if r.predicted is None else f"{r.predicted:g}"
        gap = "—" if r.gap_ratio is None else f"{r.gap_ratio * 100:+.0f}%"
        verdict = r.verdict + (f" ({r.severity})" if r.severity else "")
        prov = f"{o.source}; {o.window}" + (f"; {o.context}" if o.context else "")
        L.append(f"| {target} | {o.metric} | {pred} | {o.value:g} {o.unit} | {gap} | {verdict} | {prov} |")
    L.append("")
    L.append("_Observed metrics are read-only evidence measured from the running system; "
             "they never change an engine-computed number (prime directive). Divergences are "
             "surfaced for review, never auto-resolved (ADR-004)._")
    return "\n".join(L)
