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
  - **Honesty:** every observed value carries mandatory provenance (source + window);
    a metric the engine did not predict is flagged NO_PREDICTION, never dropped or
    faked; an observation in the wrong unit is UNIT_MISMATCH (no verdict asserted from
    incomparable numbers), never silently compared.
  - **Untrusted input (harm floor):** actuals arrive from an external file/export —
    treated as UNTRUSTED. Parsing is fail-closed (missing field / non-numeric / bool /
    non-finite / blank-provenance all rejected); string fields are sanitised + length-
    bounded so they cannot break or inject the markdown report or the calibration JSON.
  - **Read-only:** NO load is generated against the user's system (that is a v2
    concern). This module is pure + deterministic.

Real external-client actuals are commercially sensitive → gated on the model store's
tenant-isolation MUST (#21) before any multi-tenant upload; single-user/offline runs
(the demo) need none of that.
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field

from keystone.simulation import SimulationResult

# Numeric component fields on `ComponentResult` an observation can target (saturated is
# a bool, not a magnitude — excluded). System-level targets resolve against sim.metrics.
_COMPONENT_FIELDS = frozenset({"arrival_rps", "capacity_rps", "utilization", "mean_latency_ms"})

# The engine unit each metric is expressed in — so an observation supplied in the WRONG
# unit (e.g. utilisation as "72"% vs the engine's 0.72 ratio) is flagged UNIT_MISMATCH and
# NOT compared (auto-conversion or a raw comparison could assert a false MATCH/DIVERGE).
_ENGINE_UNIT = {
    "arrival_rps": "rps", "capacity_rps": "rps", "utilization": "ratio",
    "mean_latency_ms": "ms",
    "bottleneck_utilization": "ratio", "breakpoint_rps_safe": "rps",
    "breakpoint_rps_theoretical": "rps", "p50_ms": "ms", "p95_ms": "ms", "p99_ms": "ms",
    "monthly_cost": "usd_minor_per_month",
}

MATCH, DIVERGE, NO_PREDICTION, UNIT_MISMATCH = "MATCH", "DIVERGE", "NO_PREDICTION", "UNIT_MISMATCH"

_MAX_FIELD = 200   # untrusted string fields are length-bounded (report-flood guard)


def _sanitize_field(s: object, *, limit: int = _MAX_FIELD) -> str:
    """Make an untrusted export string safe + bounded before it is stored, rendered, or
    persisted: collapse CR/LF/tabs to spaces, drop other control chars, strip, and clip to
    `limit` — so a newline cannot forge a table row/heading and one field cannot flood the
    report. Unlike ingestion._clean_text we do NOT scrub numbers: a measurement window or
    value IS legitimate evidence here. Pipe-escaping for markdown happens at render (`_cell`)."""
    out = str(s).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    out = "".join(ch for ch in out if ch >= " ").strip()
    return out if len(out) <= limit else out[:limit - 1].rstrip() + "…"


def _cell(s: object) -> str:
    """Render an (untrusted) string into a markdown table cell, self-defending: sanitise
    (newline/control/bound) AND escape the pipe, so a forged column/row can't be drawn even
    if an Observation was built without going through the parser."""
    return _sanitize_field(s).replace("|", r"\|")


def _num(n: float | None) -> str:
    """Readable magnitude for the report — thousands-separated, no scientific notation, no
    trailing-zero noise (a `:g` on a large cost/rps would print e.g. 1.05e+05)."""
    if n is None:
        return "—"
    if not math.isfinite(n):
        return str(n)
    return f"{n:,.4f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Observation:
    """One number MEASURED from a real running system — evidence, never an engine output.

    Deliberately NOT named 'Metric': a `Metric` is an engine-authored output (only
    simulation.py may build one, ADR-007); an Observation is external evidence compared
    against one. Keeping the names distinct keeps the prime-directive boundary crisp.

    `component_id` names the component to compare against (`None` = a system-level metric
    such as p99_ms). `metric` is the field/key. Provenance is mandatory: a measurement
    with no source/window is not evidence (enforced by `observed_from_records`)."""
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
    gap_ratio: float | None     # (observed - predicted) / predicted, or None if not comparable
    verdict: str                # MATCH | DIVERGE | NO_PREDICTION | UNIT_MISMATCH
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

    @property
    def unit_mismatched(self) -> list[PredictionVsActual]:
        return [r for r in self.rows if r.verdict == UNIT_MISMATCH]

    def calibration_pairs(self) -> list[dict]:
        """(predicted, observed) pairs for the calibration store — the L0→L1 flywheel. ONLY
        comparable rows seed it: a real MATCH/DIVERGE with a finite prediction in matching
        units. NO_PREDICTION and UNIT_MISMATCH rows are fail-closed EXCLUDED so an
        incomparable measurement can never poison the store. Each pair carries the unit +
        provenance so a downstream calibration pass can re-verify. Pure data (caller persists)."""
        out = []
        for r in self.rows:
            if r.predicted is None or r.verdict not in (MATCH, DIVERGE):
                continue
            out.append({
                "component_id": r.observed.component_id, "metric": r.observed.metric,
                "unit": r.observed.unit, "predicted": r.predicted, "observed": r.observed.value,
                "gap_ratio": r.gap_ratio, "verdict": r.verdict,
                "source": r.observed.source, "window": r.observed.window,
                "context": r.observed.context,
            })
        return out


def observed_from_records(records: list) -> list[Observation]:
    """Parse a list of plain dicts (e.g. from a JSON export) into Observations, FAIL-CLOSED.

    Required keys: metric, value, unit, source, window. Optional: component_id, context.
    Rejected with ValueError (untrusted input — never silently coerced): a missing field, a
    non-numeric or bool or non-finite (NaN/inf) value, or blank provenance (source/window).
    String fields are sanitised + length-bounded so no consumer can be injected/flooded.
    Kept pure (no file IO) so the trust-critical parse is testable; the caller reads the file."""
    out: list[Observation] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ValueError(f"observed record {i} is not an object")
        try:
            value = rec["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"observed record {i}: 'value' must be a number, got {value!r}")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"observed record {i}: 'value' must be finite, got {value!r}")
            source = _sanitize_field(rec["source"])
            window = _sanitize_field(rec["window"])
            if not source or not window:
                raise ValueError(f"observed record {i}: 'source' and 'window' are mandatory "
                                 "provenance — a measurement with no traceable origin is not evidence")
            out.append(Observation(
                metric=_sanitize_field(rec["metric"]), value=value, unit=_sanitize_field(rec["unit"]),
                source=source, window=window,
                component_id=(_sanitize_field(rec["component_id"]) if rec.get("component_id") is not None else None),
                context=_sanitize_field(rec.get("context", "")),
            ))
        except KeyError as e:
            raise ValueError(f"observed record {i} missing required field {e}") from e
    return out


_CSV_REQUIRED = ("metric", "value", "unit", "source", "window")


def observed_from_csv(text: str) -> list[Observation]:
    """Parse a CSV telemetry export into Observations — CSV is the universal export (any
    tool, from Datadog/Grafana to a spreadsheet, can dump it). Required columns: metric,
    value, unit, source, window; optional: component_id, context; extra columns are ignored.
    A CSV cell is always a string, so 'value' is coerced to float FAIL-CLOSED here; every
    other field then flows through observed_from_records' fail-closed sanitisation (finite
    check, mandatory provenance, injection/length bounds). A header row is required."""
    reader = csv.DictReader(io.StringIO(text))
    cols = {(f or "").strip() for f in (reader.fieldnames or [])}
    if not cols:
        raise ValueError("CSV has no header row")
    missing = [c for c in _CSV_REQUIRED if c not in cols]
    if missing:
        raise ValueError(f"CSV missing required column(s): {', '.join(missing)}")

    records: list[dict] = []
    for i, row in enumerate(reader):
        raw = (row.get("value") or "").strip()
        try:
            value = float(raw)
        except ValueError as e:
            raise ValueError(f"CSV row {i}: 'value' is not a number: {raw!r}") from e
        cid = (row.get("component_id") or "").strip()
        records.append({
            "metric": row.get("metric", ""), "value": value, "unit": row.get("unit", ""),
            "source": row.get("source", ""), "window": row.get("window", ""),
            "component_id": cid or None,     # blank component_id column → a system-level metric
            "context": row.get("context", "") or "",
        })
    return observed_from_records(records)


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
    result is only READ (the prime-directive boundary). Precedence per observation:
      - the engine predicted nothing for it            → NO_PREDICTION
      - the engine's prediction is non-finite (saturated) → NO_PREDICTION (no comparable value)
      - the observation's unit ≠ the engine's unit      → UNIT_MISMATCH (no verdict asserted)
      - otherwise                                        → MATCH / DIVERGE (hard beyond hard_tol)
    Nothing is auto-resolved — divergences are evidence for the human."""
    rows: list[PredictionVsActual] = []
    for o in observed:
        predicted = _predicted_value(sim, o)

        if predicted is None:
            where = (f"component {o.component_id!r} / field {o.metric!r}" if o.component_id
                     else f"system metric {o.metric!r}")
            rows.append(PredictionVsActual(o, None, None, NO_PREDICTION, "",
                                           f"engine produced no prediction for {where}"))
            continue

        if not math.isfinite(predicted):
            rows.append(PredictionVsActual(
                o, None, None, NO_PREDICTION, "",
                f"engine prediction for {o.metric!r} is non-finite (component saturated); "
                "no comparable value"))
            continue

        expected_unit = _ENGINE_UNIT.get(o.metric)
        if expected_unit and o.unit != expected_unit:
            # Incomparable units — never assert a MATCH/DIVERGE from raw numbers (honesty).
            rows.append(PredictionVsActual(
                o, predicted, None, UNIT_MISMATCH, "",
                f"observed unit {o.unit!r} ≠ engine unit {expected_unit!r} — not comparable; "
                "supply the observation in engine units to get a verdict"))
            continue

        if predicted <= 0:
            # No stable ratio at/through zero — compare absolutely, and say so.
            verdict = MATCH if abs(o.value - predicted) < 1e-9 else DIVERGE
            sev = "soft" if verdict == DIVERGE else ""
            rows.append(PredictionVsActual(
                o, predicted, None, verdict, sev,
                f"predicted is {predicted:g} (≤0) — compared absolutely, not as a ratio"))
            continue

        gap = (o.value - predicted) / predicted
        if abs(gap) <= tol:
            rows.append(PredictionVsActual(o, predicted, gap, MATCH, "", "within tolerance"))
        else:
            sev = "hard" if abs(gap) > hard_tol else "soft"
            direction = "above" if gap > 0 else "below"
            rows.append(PredictionVsActual(
                o, predicted, gap, DIVERGE, sev,
                f"observed is {abs(gap) * 100:.0f}% {direction} the engine's prediction"))
    return ActualsReconciliation(rows)


def render_actuals_section(outcome: ActualsReconciliation) -> str:
    """Markdown 'Model vs observed reality' section — the audit finding. Predicted vs observed
    side by side, divergences emphasised, provenance shown. Never asserts the observed value is
    correct — it reports the gap for the reviewer to judge. Every untrusted string is escaped."""
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
                 f"{len(outcome.unit_mismatched)} unit-mismatch · {len(outcome.no_prediction)} "
                 "not predicted. Observed values are evidence, not corrections — the engine's "
                 "numbers are unchanged.")
    L.append("")
    L.append("| Target | Metric | Predicted | Observed | Gap | Verdict | Provenance |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rows:
        o = r.observed
        target = _cell(o.component_id or "(system)")
        gap = "—" if r.gap_ratio is None else f"{r.gap_ratio * 100:+.0f}%"
        verdict = r.verdict + (f" ({r.severity})" if r.severity else "")
        prov = _cell(f"{o.source}; {o.window}" + (f"; {o.context}" if o.context else ""))
        L.append(f"| {target} | {_cell(o.metric)} | {_num(r.predicted)} | "
                 f"{_num(o.value)} {_cell(o.unit)} | {gap} | {verdict} | {prov} |")
    L.append("")
    L.append("_Observed metrics are read-only evidence measured from the running system; "
             "they never change an engine-computed number (prime directive). Divergences are "
             "surfaced for review, never auto-resolved (ADR-004)._")
    return "\n".join(L)
