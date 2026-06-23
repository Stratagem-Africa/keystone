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

from keystone.model import Flow, SystemModel

SAFE_UTILIZATION = 0.85   # conventional "run hot" ceiling
_RHO_CEIL = 0.999         # guard against divide-by-zero as rho -> 1
# Exponential-tail percentile multipliers. Defined once and used by BOTH the engine and its
# derivation trace, so the "show your work" line can never drift from the math actually applied.
_P50_K = math.log(2)      # ~0.69
_P95_K = math.log(20)     # ~3.00
_P99_K = math.log(100)    # ~4.61
_MICRO_PER_CENT = 10_000  # 1 cent = 10_000 micro-USD (ADR-009 usage-rate fixed point)
_BP_FULL = 10_000         # basis-point denominator (per-10_000) for the compute discount lever
_BP_HALF = _BP_FULL // 2  # round-half-up offset, so the discount stays pure-integer money (no float)


def _discount_compute(list_cents: int, retained_bp: int) -> int:
    """Apply the compute pricing model (ADR-009 Tier 2): the cents actually paid = list × retained_bp,
    with round-half-up done in PURE INTEGER arithmetic (harm floor — money never touches a float).
    on_demand (retained_bp = 10_000) returns `list_cents` unchanged, so existing numbers are identical."""
    return (list_cents * retained_bp + _BP_HALF) // _BP_FULL


def _cost_breakdown(model: SystemModel) -> dict[str, int]:
    """Monthly cost split into compute + usage lines, all integer CENTS (ADR-008/ADR-009 Tiers 1–2).
    Compute = per-instance compute × the pricing-model discount (Tier 2). Usage = each component's
    egress/storage/request volumes × the model's per-unit rates (micro-USD), rounded to cents per line
    so the shown lines sum to the total. Zero volumes + on_demand pricing → existing models unchanged.
    The engine is the sole producer of these numbers (prime directive)."""
    r = model.pricing
    egress_micro = storage_micro = request_acc = 0
    for c in model.components.values():
        egress_micro += c.egress_gb_per_month * r.egress_micro_usd_per_gb
        storage_micro += c.storage_gb * r.storage_micro_usd_per_gb_month
        # accumulate the numerator (requests × rate-per-1000) and divide ONCE, so no per-component
        # truncation bias — the request line is exact to the cent (review nit).
        request_acc += c.requests_per_month * r.request_micro_usd_per_thousand
    list_compute = sum(c.monthly_cost for c in model.components.values())   # on-demand list, integer cents
    return {
        "compute": _discount_compute(list_compute, r.compute_retained_bp),   # Tier 2 discount applied
        "egress": round(egress_micro / _MICRO_PER_CENT),
        "storage": round(storage_micro / _MICRO_PER_CENT),
        "requests": round(request_acc / (1000 * _MICRO_PER_CENT)),
    }


@dataclass(frozen=True)
class Metric:
    """A self-describing engine output: a number never travels without the MODEL that produced it
    and a confidence qualifier (Doc 03 pillar 2 "no bare numbers"; ADR-007; prior art: gem5's
    typed stats, docs/13).

    Prime-directive invariant: a `Metric` is constructed ONLY by this module. The council / report
    / UI may READ one, never build or mutate it (enforced by `tests/test_metric_envelope.py`).
    At L0 the numeric band (`low`/`high`) stays `None` — the engine does not compute a per-metric
    interval yet, and fabricating one would be false precision (Doc 03). A band is set only when
    EARNED (L1 grounding / L2 calibration / v2 DES replications) and must bracket `value`."""
    value: float
    unit: str               # "rps" | "ms" | "usd_minor_per_month" | "ratio"
    model: str              # the formula that produced it, e.g. "M/M/1 sojourn W=S/(1-rho)"
    confidence: str         # the engine-stability qualifier (NOT an input-provenance tag)
    low: float | None = None
    high: float | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if math.isnan(self.value):
            raise ValueError("Metric.value must not be NaN")
        if not self.model.strip():
            raise ValueError("Metric.model (the formula that produced it) is required")
        if (self.low is None) != (self.high is None):
            raise ValueError("Metric band needs both low and high, or neither")
        if self.low is not None and not (self.low <= self.value <= self.high):
            raise ValueError("Metric band must bracket value (no fabricated precision)")


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
    # Generated "show your work" trace: the deterministic steps that produced the numbers
    # above (arrivals -> rho -> bottleneck -> breakpoint -> latency -> percentiles). Derived
    # purely from this engine's own computation (NEVER an LLM) so the report can render
    # provenance instead of trusting prose. Complements `caveats` (how-computed vs where-wrong).
    derivation: list[str] = field(default_factory=list)
    # Self-describing envelope for the headline numbers (ADR-007): each carries its model +
    # confidence qualifier so the report ships no bare number. Built only by `simulate()`.
    metrics: dict[str, Metric] = field(default_factory=dict)
    # Monthly cost split into compute + usage lines, integer cents (ADR-009 Tier 1). Sums to monthly_cost.
    cost_breakdown: dict[str, int] = field(default_factory=dict)
    # On-demand (list) compute before the Tier-2 pricing discount, integer cents. Equals
    # cost_breakdown["compute"] under on_demand; lets the report show "list → charged (−X%)" honestly.
    compute_list_cents: int = 0
    compute_pricing: str = "on_demand"   # which pricing model produced the compute line (ADR-009 Tier 2)


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


def _fmt_rps(x: float) -> str:
    return "unbounded" if x == float("inf") else f"{x:,.0f}"


def _derivation(
    model: SystemModel,
    comps: dict[str, ComponentResult],
    dom: Flow,
    rho_max: float,
    bottleneck_id: str | None,
    bp_safe: float,
    bp_theo: float,
    mean: float,
    cost_breakdown: dict[str, int],
    compute_list_cents: int,
) -> list[str]:
    """The deterministic derivation of every headline number (a generated audit trail).

    Each line restates a step the engine actually executed above, using the values it
    computed. This is provenance, not a metric source: it never introduces a number the
    engine did not already produce, and no language model is involved (prime directive)."""
    sys_rps = model.workload.system_rps
    flow_split = ", ".join(f"{f.name} {f.share:.0%}" for f in model.flows) or "no flows"
    lines = [
        f"Offered load: {_fmt_rps(sys_rps)} req/s split across {len(model.flows)} flow(s) "
        f"by share ({flow_split}).",
        "Arrival per component = sum over flows of system_rps * flow.share * visit_prob along "
        "its path (open Jackson network).",
        "Utilisation rho = arrival / capacity, where capacity = per_instance_rps * instances.",
    ]
    bn = comps.get(bottleneck_id) if bottleneck_id else None
    if bn:
        lines.append(
            f"Bottleneck = highest rho -> {bn.name} at rho={rho_max:.2f} "
            f"({_fmt_rps(bn.arrival_rps)} / {_fmt_rps(bn.capacity_rps)} rps)."
        )
    lines.append(
        f"Max sustainable load = system_rps * (ceiling / rho_max): "
        f"safe@{SAFE_UTILIZATION:.0%} ~ {_fmt_rps(bp_safe)} req/s, "
        f"theoretical@100% ~ {_fmt_rps(bp_theo)} req/s."
    )
    lines.append(
        f"Latency = sum of M/M/1 sojourn (service / (1 - rho)) * visit_prob along the dominant "
        f"flow ('{dom.name}', {dom.share:.0%} share) -> mean {mean:.0f} ms."
    )
    lines.append(
        "Percentiles via an exponential-tail approximation: p50/p95/p99 = mean x "
        f"{_P50_K:.2f}/{_P95_K:.2f}/{_P99_K:.2f} (over-states the tail; treat as a directional upper bound)."
    )
    # Cost derivation: list compute -> pricing discount -> + usage lines (all integer cents).
    charged = cost_breakdown.get("compute", 0)
    pricing = model.pricing.compute_pricing
    usage_bits = ", ".join(
        f"{k} ${cost_breakdown[k] / 100:,.2f}" for k in ("egress", "storage", "requests")
        if cost_breakdown.get(k)
    )
    if pricing != "on_demand" and compute_list_cents != charged:
        off = 1 - (charged / compute_list_cents) if compute_list_cents else 0.0
        lines.append(
            f"Compute pricing '{pricing}': list ${compute_list_cents / 100:,.2f} -> "
            f"charged ${charged / 100:,.2f} ({off:.0%} off, ASSUMPTION discount ratio)."
        )
    lines.append(
        f"Monthly cost = compute ${charged / 100:,.2f}"
        + (f" + usage ({usage_bits})" if usage_bits else "")
        + f" = ${sum(cost_breakdown.values()) / 100:,.2f} (integer cents; usage rates ASSUMPTION)."
    )
    return lines


def _metrics(
    rho_max: float, bp_safe: float, bp_theo: float, mean: float,
    p50: float, p95: float, p99: float, monthly_cost: float, confidence: str,
) -> dict[str, Metric]:
    """The headline outputs as self-describing `Metric`s (ADR-007). Each restates a value the
    engine already computed, tagged with the model that produced it + the engine-stability
    confidence qualifier. No numeric band at L0 (not fabricated). Built only here."""
    tail = ("over-states the tail; directional upper bound",)
    safe_pct = f"{SAFE_UTILIZATION:.0%}"
    return {
        "bottleneck_utilization": Metric(rho_max, "ratio", "max rho = arrival / capacity", confidence),
        "breakpoint_rps_safe": Metric(bp_safe, "rps", f"system_rps * ({safe_pct} ceiling / rho_max)", confidence),
        "breakpoint_rps_theoretical": Metric(bp_theo, "rps", "system_rps * (1.0 / rho_max)", confidence),
        "mean_latency_ms": Metric(mean, "ms", "sum of M/M/1 sojourn W=S/(1-rho) along the dominant flow", confidence),
        "p50_ms": Metric(p50, "ms", "exponential-tail: mean * ln(2)", confidence, caveats=tail),
        "p95_ms": Metric(p95, "ms", "exponential-tail: mean * ln(20)", confidence, caveats=tail),
        "p99_ms": Metric(p99, "ms", "exponential-tail: mean * ln(100)", confidence, caveats=tail),
        "monthly_cost": Metric(monthly_cost, "usd_minor_per_month",
                               "compute (× pricing model) + usage (egress/storage/requests) at ASSUMPTION rates",
                               confidence, caveats=("usage + discount ratios are uncited seeds; no SaaS/AI cost yet",)),
    }


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
    p50 = mean * _P50_K
    p95 = mean * _P95_K
    p99 = mean * _P99_K

    cost_breakdown = _cost_breakdown(model)
    monthly_cost = sum(cost_breakdown.values())   # compute + usage, integer cents (ADR-009 Tiers 1–2)
    compute_list_cents = sum(c.monthly_cost for c in model.components.values())  # on-demand list (pre-discount)

    caveats = [
        "Analytical queueing approximation (M/M/1 per component), not a discrete-event "
        "simulation. Async/streaming/multi-region topologies are out of v1 scope.",
        "Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to "
        "your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).",
        "Percentiles use an exponential-tail approximation and tend to OVER-state the tail; "
        "treat p95/p99 as upper-bound directional figures.",
        "Cost = per-instance compute × the chosen pricing-model discount + declared usage "
        "(egress/storage/requests) at ASSUMPTION rates (ADR-009 Tiers 1–2). Compute defaults to "
        "on_demand list price; reserved/spot apply published-range discount ratios that are uncited "
        "ASSUMPTION seeds. Usage is 0 unless a component declares it. AI/LLM and SaaS costs are not yet modelled.",
        "Bottleneck identification and the relative ordering of components are far more "
        "reliable than absolute latency/cost numbers.",
    ]

    conf = _confidence(rho_max)  # engine-stability qualifier, shared by the run + every Metric
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
        confidence=conf,
        caveats=caveats,
        derivation=_derivation(model, comp_results, dom, rho_max, bottleneck, bp_safe, bp_theo, mean,
                               cost_breakdown, compute_list_cents),
        metrics=_metrics(rho_max, bp_safe, bp_theo, mean, p50, p95, p99, monthly_cost, conf),
        cost_breakdown=cost_breakdown,
        compute_list_cents=compute_list_cents,
        compute_pricing=model.pricing.compute_pricing,
    )
