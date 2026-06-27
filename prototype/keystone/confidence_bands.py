"""Output confidence bands — propagate CITED input uncertainty into honest output ranges.

The deterministic engine (`simulation.simulate`) is the sole producer of numbers and NEVER reads a
grounding value. This layer sits ON TOP of it: it reads the cited confidence band of each
GROUNDED-in-band input, builds two scenario models (pessimistic + optimistic) by setting each such
input to its band endpoint, runs the UNCHANGED engine on each, and reports every headline output's
[min, max] across {point, pessimistic, optimistic} as its band.

Honesty (CLAUDE.md — "never claim accuracy the eval hasn't proven"): a band means "given the CITED
input ranges, the output ranges thus" — NOT that the true value lies within it, and NOT a calibration
claim. Maturity stays **L0 (Directional)**. Only GROUNDED-in-band inputs vary; ASSUMPTION inputs (no
evidence) and RECONCILE inputs (modeler value outside the cited band — kept, never overwritten) are
held CONSTANT, so the band reflects cited input uncertainty alone. No groundings → no bands (the L0
point-estimate state is preserved unchanged).

Determinism: no sampling — just two extra engine runs on fixed endpoint models. Prime directive: this
module never constructs a Metric; it hands band values to `simulation.attach_confidence_bands`.
"""
from __future__ import annotations

import dataclasses
import math

from keystone.model import SystemModel
from keystone.simulation import SimulationResult, attach_confidence_bands, simulate

# Per groundable INPUT metric: which cited endpoint is the PESSIMISTIC ("worst") scenario.
#   per_instance_rps (capacity):     LOW  is worst  → higher utilisation/latency, lower breakpoint.
#   base_latency_ms:                 HIGH is worst  → higher latency.
#   monthly_cost_per_instance:       HIGH is worst  → higher cost.
# Every headline output is monotonic in each of these for the M/M/1 + linear-cost engine, and the
# "worst" direction is consistent across outputs — so one pessimistic + one optimistic model bracket
# ALL outputs (we still take min/max defensively). A new groundable metric, or a non-monotonic formula
# change, MUST extend this map and re-justify the monotonicity (guarded by tests).
_WORST_ENDPOINT = {
    "per_instance_rps": "low",
    "base_latency_ms": "high",
    "monthly_cost_per_instance": "high",
}


def _in_band(value: float, g) -> bool:
    """GROUNDED-in-band: a grounding exists and its cited band brackets the value actually used.
    (RECONCILE — value outside the cited band — returns False, so it is held constant.)"""
    return g is not None and g.confidence_low <= value <= g.confidence_high


def _endpoint(g, which: str) -> float:
    return g.confidence_low if which == "low" else g.confidence_high


def _variant(model: SystemModel, *, worst: bool) -> SystemModel:
    """A model copy with each GROUNDED-in-band input set to its pessimistic (worst) or optimistic
    (best) cited endpoint. ASSUMPTION / RECONCILE inputs are left untouched."""
    new_components = {}
    for cid, c in model.components.items():
        changes: dict[str, float] = {}
        for metric, worst_end in _WORST_ENDPOINT.items():
            g = c.groundings.get(metric)
            cur = getattr(c, metric)
            if not _in_band(cur, g):
                continue
            best_end = "high" if worst_end == "low" else "low"
            val = _endpoint(g, worst_end if worst else best_end)
            if metric == "monthly_cost_per_instance":
                val = int(val)   # money stays integer cents (harm floor); the cited band is whole cents (ADR-008)
            changes[metric] = val
        new_components[cid] = dataclasses.replace(c, **changes) if changes else c
    return dataclasses.replace(model, components=new_components)


def has_grounded_in_band(model: SystemModel) -> bool:
    return any(_in_band(getattr(c, m), c.groundings.get(m))
               for c in model.components.values() for m in _WORST_ENDPOINT)


def simulate_with_confidence(model: SystemModel) -> SimulationResult:
    """`simulate(model)`, but each headline Metric also carries a [low, high] band derived from the
    cited uncertainty of GROUNDED-in-band inputs. Output VALUES are IDENTICAL to `simulate(model)`;
    only the bands are added. No grounded-in-band inputs → plain `simulate(model)` (no bands)."""
    point = simulate(model)
    if not has_grounded_in_band(model):
        return point
    worst = simulate(_variant(model, worst=True))
    best = simulate(_variant(model, worst=False))
    bands: dict[str, tuple[float, float]] = {}
    for key, m in point.metrics.items():
        vals = (m.value, worst.metrics[key].value, best.metrics[key].value)
        if any(not math.isfinite(v) for v in vals):
            continue                     # don't band a degenerate (saturated/inf) metric — false precision
        lo, hi = min(vals), max(vals)
        if lo < hi:                      # only when there is real spread (skip [x, x])
            bands[key] = (lo, hi)
    return attach_confidence_bands(point, bands)
