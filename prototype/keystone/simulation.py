"""Deterministic analytical simulation engine (Doc 02 §4, Doc 03).

This module is the ONLY producer of numbers in Keystone. The LLM/council never
emits a metric; it parameterises this model and explains the output.

Model: an open queueing network (Jackson-style approximation).
  - Per component: arrival rate = Sum over flows of system_rps * share * visit_prob.
  - Utilization rho = arrival / capacity.
  - Bottleneck = component with the highest rho.
  - Breakpoint scales linearly with offered load (open network), so the max
    sustainable system rps is today's rps * (ceiling / rho_max).
  - Per-component mean sojourn time via M/M/1: W = service / (1 - rho).
  - Path latency = sum of mean sojourn times along the dominant flow; percentiles
    via an exponential-tail approximation (acknowledged in caveats).

Accuracy level: L0 (Directional) per the Accuracy Charter. Honest by construction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from keystone.model import SystemModel

SAFE_UTILIZATION = 0.85   # conventional "run hot" ceiling
_RHO_CEIL = 0.999         # guard against divide-by-zero as rho -> 1


@dataclass
class ComponentResult:
    id: str
    name: str
    arrival_rps: float
    capacity_rps: float
    utilization: float
    mean_latency_ms: float
    saturated: bool


@dataclass
class SimulationResult:
    system_rps: float
    bottleneck_id: str
    bottleneck_name: str
    bottleneck_utilization: float
    breakpoint_rps_safe: float
    breakpoint_rps_theoretical: float
    mean_latency_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    monthly_cost: float
    components: dict[str, ComponentResult]
    spofs: list[str]
    confidence: str
    caveats: list[str] = field(default_factory=list)


def _arrivals(model: SystemModel) -> dict[str, float]:
    arr = {cid: 0.0 for cid in model.components}
    for flow in model.flows:
        flow_rps = model.workload.system_rps * flow.share
        for step in flow.path:
            arr[step.component_id] += flow_rps * step.visit_prob
    return arr


def _mm1_sojourn_ms(service_ms: float, rho: float) -> float:
    rho = min(rho, _RHO_CEIL)
    return service_ms / (1.0 - rho)


def _confidence(rho_max: float) -> str:
    # Queueing estimates get unreliable as utilization approaches 1.
    if rho_max >= 1.0:
        return "low (a component is saturated; beyond the model's stable range)"
    if rho_max >= 0.85:
        return "low-to-medium (running hot; latency is highly sensitive near saturation)"
    if rho_max >= 0.6:
        return "medium (directional; within the model's reliable band)"
    return "medium-high (lightly loaded; estimates most reliable here)"


def simulate(model: SystemModel) -> SimulationResult:
    arrivals = _arrivals(model)

    comp_results: dict[str, ComponentResult] = {}
    rho_max = 0.0
    bottleneck = None
    spofs: list[str] = []

    for cid, comp in model.components.items():
        a = arrivals[cid]
        cap = comp.capacity_rps
        rho = (a / cap) if cap > 0 else float("inf")
        latency = _mm1_sojourn_ms(comp.base_latency_ms, rho)
        comp_results[cid] = ComponentResult(
            id=cid, name=comp.name, arrival_rps=a, capacity_rps=cap,
            utilization=rho, mean_latency_ms=latency, saturated=(rho >= 1.0),
        )
        if rho > rho_max:
            rho_max, bottleneck = rho, cid
        if comp.is_spof:
            spofs.append(comp.name)

    if rho_max > 0:
        bp_safe = model.workload.system_rps * (SAFE_UTILIZATION / rho_max)
        bp_theo = model.workload.system_rps * (1.0 / rho_max)
    else:
        bp_safe = bp_theo = float("inf")

    # Latency along the dominant (largest-share) flow.
    dom = max(model.flows, key=lambda f: f.share)
    mean = sum(comp_results[s.component_id].mean_latency_ms * s.visit_prob for s in dom.path)

    # Exponential-tail percentile approximation (conservative on the tail).
    p50 = mean * math.log(2)          # ~0.69 * mean
    p95 = mean * math.log(20)         # ~3.00 * mean
    p99 = mean * math.log(100)        # ~4.61 * mean

    monthly_cost = sum(c.monthly_cost for c in model.components.values())

    caveats = [
        "Analytical queueing approximation (M/M/1 per component), not a discrete-event "
        "simulation. Async/streaming/multi-region topologies are out of v1 scope.",
        "Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to "
        "your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).",
        "Percentiles use an exponential-tail approximation and tend to OVER-state the tail; "
        "treat p95/p99 as upper-bound directional figures.",
        "Cost is compute/instance only; data-transfer/egress and managed-service pricing "
        "nuances are not yet modelled.",
        "Bottleneck identification and the relative ordering of components are far more "
        "reliable than absolute latency/cost numbers.",
    ]

    return SimulationResult(
        system_rps=model.workload.system_rps,
        bottleneck_id=bottleneck,
        bottleneck_name=comp_results[bottleneck].name if bottleneck else "n/a",
        bottleneck_utilization=rho_max,
        breakpoint_rps_safe=bp_safe,
        breakpoint_rps_theoretical=bp_theo,
        mean_latency_ms=mean,
        p50_ms=p50, p95_ms=p95, p99_ms=p99,
        monthly_cost=monthly_cost,
        components=comp_results,
        spofs=spofs,
        confidence=_confidence(rho_max),
        caveats=caveats,
    )
