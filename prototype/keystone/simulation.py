"""Deterministic analytical simulation engine (Doc 02 §4, Doc 03).

This module is the ONLY producer of numbers in Keystone. The LLM/council never
emits a metric; it parameterises this model and explains the output.

Model: an open queueing network (Jackson-style approximation).
  - Per component: arrival rate = Sum over flows of system_rps * share * visit_prob.
  - Utilization rho = arrival / capacity.
  - Bottleneck = component with the highest rho.
  - Breakpoint scales linearly with offered load (open network), so the max
    sustainable system rps is today's rps * (ceiling / rho_max).
  - Per-component mean sojourn time via M/M/c (Erlang-C): W = S + Wq, over the tier's
    instance count. Reduces to M/M/1 exactly at c=1. Unstable (infinite) at rho >= 1.
  - Path latency = sum of mean sojourn times along the dominant flow (exact — expectation is
    linear). Percentiles are a fixed-shape exponential approximation applied to that mean, so
    p99/p50 is a constant regardless of design or load. Exact for a single M/M/1 hop; approximate
    for M/M/c and for multi-hop paths. Disclosed in the caveats, never presented as a measurement.

Accuracy level: L0 (Directional) per the Accuracy Charter. Honest by construction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

# ComponentKind is imported for ONE purpose: a prose caveat (see the queue note in `simulate`).
# The engine's maths remains entirely kind-agnostic — there is no branch on kind anywhere in the
# numeric path, and a component's behaviour comes from its capacity and service time alone.
from keystone.model import ComponentKind, Flow, SystemModel

SAFE_UTILIZATION = 0.85   # conventional "run hot" ceiling
_RHO_CEIL = 0.999         # retained ONLY for the breakpoint search; latency no longer clamps (see
                          # _mmc_sojourn_ms — above rho=1 the wait is infinite and is reported so)
_ERLANG_C_MAX_SERVERS = 10_000   # beyond this the Erlang-C wait is numerically nil; see _mmc_sojourn_ms
# Exponential-tail percentile multipliers. Defined once and used by BOTH the engine and its
# derivation trace, so the "show your work" line can never drift from the math actually applied.
_P50_K = math.log(2)      # ~0.69
_P95_K = math.log(20)     # ~3.00
_P99_K = math.log(100)    # ~4.61
_MICRO_PER_CENT = 10_000  # 1 cent = 10_000 micro-USD (ADR-009 usage-rate fixed point)
_MICRO_PER_CENT_HALF = _MICRO_PER_CENT // 2          # round-half-up offset for per-unit micro-rates
_MICRO_PER_K_CENT = 1000 * _MICRO_PER_CENT           # divisor for per-1000-unit micro-rates → cents
_MICRO_PER_K_CENT_HALF = _MICRO_PER_K_CENT // 2
_BP_FULL = 10_000         # basis-point denominator (per-10_000) for the compute discount lever
_BP_HALF = _BP_FULL // 2  # round-half-up offset, so the discount stays pure-integer money (no float)


def _discount_compute(list_cents: int, retained_bp: int) -> int:
    """Apply the compute pricing model (ADR-009 Tier 2): the cents actually paid = list × retained_bp,
    with round-half-up done in PURE INTEGER arithmetic (harm floor — money never touches a float).
    on_demand (retained_bp = 10_000) returns `list_cents` unchanged, so existing numbers are identical."""
    return (list_cents * retained_bp + _BP_HALF) // _BP_FULL


def _cost_breakdown(model: SystemModel) -> dict[str, int]:
    """Monthly cost split into compute + usage + AI lines, all integer CENTS (ADR-008/ADR-009 Tiers 1–2).
    Compute = per-instance compute × the pricing-model discount (Tier 2 part 1). Usage = each component's
    egress/storage/request volumes × the model's per-unit rates. AI = LLM input/output token volumes ×
    per-1K-token rates (Tier 2 part 2). All rates are micro-USD; each line accumulates its numerator and
    divides ONCE, rounded to cents, so the shown lines sum to the total with no per-component truncation
    bias. Zero volumes + on_demand pricing → existing models unchanged. The engine is the sole producer
    of these numbers (prime directive)."""
    r = model.pricing
    egress_micro = storage_micro = request_acc = token_acc = 0
    for c in model.components.values():
        egress_micro += c.egress_gb_per_month * r.egress_micro_usd_per_gb
        storage_micro += c.storage_gb * r.storage_micro_usd_per_gb_month
        # accumulate each per-1000-unit numerator and divide ONCE (below), so no per-component
        # truncation bias — the request/AI lines are exact to the cent (review nit).
        request_acc += c.requests_per_month * r.request_micro_usd_per_thousand
        token_acc += (c.llm_input_tokens_per_month * r.llm_input_micro_usd_per_1k_tokens
                      + c.llm_output_tokens_per_month * r.llm_output_micro_usd_per_1k_tokens)
    list_compute = sum(c.monthly_cost for c in model.components.values())   # on-demand list, integer cents
    return {
        "compute": _discount_compute(list_compute, r.compute_retained_bp),   # Tier 2 discount applied
        # Pure-integer round-half-up (no float) — money never touches a float (harm floor, ADR-008).
        # Matches _discount_compute; for realistic volumes this equals the prior round(); it differs only
        # for sums beyond float's exact-integer range or an exact-half-cent (banker's→half-up), where the
        # integer form is the correct, exact one.
        "egress": (egress_micro + _MICRO_PER_CENT_HALF) // _MICRO_PER_CENT,
        "storage": (storage_micro + _MICRO_PER_CENT_HALF) // _MICRO_PER_CENT,
        "requests": (request_acc + _MICRO_PER_K_CENT_HALF) // _MICRO_PER_K_CENT,
        "ai": (token_acc + _MICRO_PER_K_CENT_HALF) // _MICRO_PER_K_CENT,   # LLM tokens (per-1K rate) → cents
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
    model: str              # the formula that produced it, e.g. "M/M/c sojourn W=S+Wq (Erlang-C)"
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
class FlowLatency:
    """One flow's own latency (ms): the same M/M/c-sojourn + exponential-tail model as the headline,
    applied to THIS flow's path — so a minority flow on a different (often worse) path is not hidden
    behind the dominant flow's figure (engine-audit fix). Built only by `simulate()`."""
    name: str
    share: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


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
    monthly_cost: int               # integer minor units (USD cents) — harm floor (ADR-008), never float
    components: dict[str, ComponentResult]
    spofs: list[str]
    confidence: str
    # Per-flow latency (each flow's own path); the headline mean/p50/p95/p99 above is the dominant flow.
    flow_latencies: list[FlowLatency] = field(default_factory=list)
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


def _flow_latency_ms(flow: Flow, comp_results: dict[str, "ComponentResult"]) -> tuple[float, float, float, float]:
    """Mean + exponential-tail percentiles (ms) along ONE flow's path — the sole latency math, shared by
    the headline (dominant flow) and the per-flow breakdown so they can never diverge."""
    mean = sum(comp_results[s.component_id].mean_latency_ms * s.visit_prob for s in flow.path)
    return mean, mean * _P50_K, mean * _P95_K, mean * _P99_K


def _erlang_c(servers: int, rho: float) -> float:
    """Probability an arrival must WAIT (Erlang-C), computed via the numerically-stable Erlang-B
    recursion. The textbook closed form needs a^c / c!, which overflows well before the 320-instance
    transcode fleet in the library; the recursion never forms either term.

        B(0) = 1 ;  B(k) = a*B(k-1) / (k + a*B(k-1)) ;  C = B(c) / (1 - rho*(1 - B(c)))
    """
    a = servers * rho                       # offered load in erlangs
    b = 1.0
    for k in range(1, servers + 1):
        b = (a * b) / (k + a * b)
    return b / (1.0 - rho * (1.0 - b))


def _mmc_sojourn_ms(service_ms: float, servers: int, rho: float) -> float:
    """Mean time in system for an M/M/c queue: W = S + Wq, with Wq = C(c,rho) / (c*mu*(1 - rho)).

    THIS WAS M/M/1 UNTIL 2026-09-07, and that was a real error, not a simplification. `docs/02` has
    always advertised "M/M/c utilization"; the code applied the SINGLE-server waiting formula
    S/(1-rho) to a whole fleet's AGGREGATE utilisation. A 12-instance tier at rho=0.694 does not
    queue like one server at 69.4% — it queues far better, because an arrival has twelve chances to
    find a free server. Measured against Erlang-C on the flagship url_shortener that overstated the
    app tier by 3.12x (26.18ms vs 8.38ms) and the whole path by 2.10x; `blueprints/library/
    ci_cd.json:282` self-documents ~12x. Every multi-instance tier in all 56 blueprints carried it,
    so every latency, and every remediation ranked by latency, leaned pessimistic.

    c = 1 reduces to S/(1-rho) EXACTLY (algebraically, not approximately) — `test_simulation`
    asserts that identity, so the old single-server behaviour is preserved where it was correct.

    Above rho = 1 the queue is UNSTABLE: arrivals outrun the servers and the backlog grows without
    limit, so the mean is genuinely infinite. It returns `inf` and says so, rather than clamping to
    a finite figure. The clamp this replaces returned 46,051.7 ms at 100x, 1,000x, 10,000x AND
    1,000,000x load — a constant that looked like a prediction and was an artifact of `_RHO_CEIL`.
    """
    if rho >= 1.0:
        return math.inf
    if servers <= 1:
        return service_ms / (1.0 - rho)
    if servers > _ERLANG_C_MAX_SERVERS:
        # C(c,rho) decays exponentially in c at fixed rho<1, so beyond this the wait is numerically
        # nil and the O(c) recursion is pure cost. Returning the service time is the correct limit.
        return service_ms
    c_wait = _erlang_c(servers, rho)
    wq_ms = c_wait * service_ms / (servers * (1.0 - rho))
    return service_ms + wq_ms


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
    rates_grounded: bool = False,
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
        f"Latency = sum of M/M/c sojourn (Erlang-C, over each tier's instances) * visit_prob along the dominant "
        f"flow ('{dom.name}', {dom.share:.0%} share) -> mean {mean:.0f} ms."
    )
    lines.append(
        "Percentiles are a FIXED-SHAPE approximation, not a second measurement: p50/p95/p99 = mean x "
        f"{_P50_K:.2f}/{_P95_K:.2f}/{_P99_K:.2f}. Two consequences worth knowing. (1) The ratio "
        f"p99/p50 is the constant {_P99_K / _P50_K:.2f} for EVERY design at EVERY load, so the "
        "percentiles carry no information the mean does not already carry — read them as a shape "
        "applied to the mean, never as an independently derived tail. (2) The multipliers assume an "
        "exponentially distributed sojourn, which is EXACT for a single M/M/1 hop and only "
        "approximate here, because the engine now models each tier as M/M/c (whose sojourn is a "
        "mixture, not an exponential) and sums several hops along a path. It over-states the tail in "
        "the common case; treat it as a directional upper bound. A real tail model needs the M/M/c "
        "sojourn distribution convolved along the path, and is not in v1."
    )
    # Cost derivation: list compute -> pricing discount -> + usage lines (all integer cents).
    charged = cost_breakdown.get("compute", 0)
    pricing = model.pricing.compute_pricing
    usage_bits = ", ".join(
        f"{k} ${cost_breakdown[k] / 100:,.2f}" for k in ("egress", "storage", "requests", "ai")
        if cost_breakdown.get(k)
    )
    # Provenance label agrees with the rate evidence (stub → "ASSUMPTION", exact prior text).
    prov = "GROUNDED (cited)" if rates_grounded else "ASSUMPTION"
    if pricing != "on_demand" and compute_list_cents != charged:
        off = 1 - (charged / compute_list_cents) if compute_list_cents else 0.0
        lines.append(
            f"Compute pricing '{pricing}': list ${compute_list_cents / 100:,.2f} -> "
            f"charged ${charged / 100:,.2f} ({off:.0%} off, {prov} discount ratio)."
        )
    # Name AI rates explicitly when an AI line is present — AI token prices are a placeholder model
    # class (real prices vary ~100×), a stronger caveat than the generic usage rates (honesty review).
    rate_note = f"usage/AI rates {prov}" if cost_breakdown.get("ai") else f"usage rates {prov}"
    lines.append(
        f"Monthly cost = compute ${charged / 100:,.2f}"
        + (f" + usage ({usage_bits})" if usage_bits else "")
        + f" = ${sum(cost_breakdown.values()) / 100:,.2f} (integer cents; {rate_note})."
    )
    return lines


def _metrics(
    rho_max: float, bp_safe: float, bp_theo: float, mean: float,
    p50: float, p95: float, p99: float, monthly_cost: float, confidence: str,
    rates_grounded: bool = False,
) -> dict[str, Metric]:
    """The headline outputs as self-describing `Metric`s (ADR-007). Each restates a value the
    engine already computed, tagged with the model that produced it + the engine-stability
    confidence qualifier. No numeric band at L0 (not fabricated). Built only here."""
    tail = ("fixed shape applied to the mean (p99/p50 is a constant); over-states the "
            "tail; directional upper bound, not a second measurement",)
    safe_pct = f"{SAFE_UTILIZATION:.0%}"
    # Rate provenance label agrees with the report's rate tag (stub → "ASSUMPTION", exact prior text).
    rate_model = ("compute (× pricing model) + usage (egress/storage/requests) + AI tokens at "
                  + ("GROUNDED (cited) rates" if rates_grounded else "ASSUMPTION rates"))
    rate_caveat = ("usage/AI/discount ratios GROUNDED to cited benchmarks; no third-party SaaS cost yet"
                   if rates_grounded else
                   "usage/AI/discount ratios are uncited seeds; no third-party SaaS cost yet")
    return {
        "bottleneck_utilization": Metric(rho_max, "ratio", "max rho = arrival / capacity", confidence),
        "breakpoint_rps_safe": Metric(bp_safe, "rps", f"system_rps * ({safe_pct} ceiling / rho_max)", confidence),
        "breakpoint_rps_theoretical": Metric(bp_theo, "rps", "system_rps * (1.0 / rho_max)", confidence),
        "mean_latency_ms": Metric(mean, "ms", "sum of M/M/c sojourn W=S+Wq (Erlang-C) along the dominant flow", confidence),
        "p50_ms": Metric(p50, "ms", "exponential-tail: mean * ln(2)", confidence, caveats=tail),
        "p95_ms": Metric(p95, "ms", "exponential-tail: mean * ln(20)", confidence, caveats=tail),
        "p99_ms": Metric(p99, "ms", "exponential-tail: mean * ln(100)", confidence, caveats=tail),
        "monthly_cost": Metric(monthly_cost, "usd_minor_per_month", rate_model,
                               confidence, caveats=(rate_caveat,)),
    }


def attach_confidence_bands(result: SimulationResult,
                            bands: dict[str, tuple[float, float]] | None) -> SimulationResult:
    """Return a copy of `result` whose headline Metrics carry a [low, high] band.

    Prime-directive invariant: a Metric is only ever constructed in THIS module. So the confidence-band
    layer (keystone/confidence_bands.py) computes the band VALUES by re-running the UNTOUCHED engine on
    cited-endpoint scenario models, then hands them here to be attached. Metric VALUES are unchanged —
    the engine output is byte-identical with or without bands; only low/high are added. The Metric guard
    enforces low <= value <= high, so the band must bracket the point value (it does: the band layer
    takes min/max over {point, pessimistic, optimistic}). An honest band = "given the cited INPUT ranges,
    the output ranges thus" — NOT a validated-accuracy claim; maturity stays L0 (Directional)."""
    if not bands:
        return result
    new_metrics = {
        key: (Metric(m.value, m.unit, m.model, m.confidence,
                     low=bands[key][0], high=bands[key][1], caveats=m.caveats)
              if key in bands else m)
        for key, m in result.metrics.items()
    }
    return replace(result, metrics=new_metrics)


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
        latency = _mmc_sojourn_ms(comp.base_latency_ms, comp.instances, rho)
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

    # Latency: the headline tracks the dominant (largest-share) flow; the per-flow breakdown gives EACH
    # flow its own figure so a minority flow on a worse path isn't hidden (engine-audit fix).
    dom = max(model.flows, key=lambda f: f.share)
    mean, p50, p95, p99 = _flow_latency_ms(dom, comp_results)
    flow_latencies = [FlowLatency(f.name, f.share, *_flow_latency_ms(f, comp_results)) for f in model.flows]

    cost_breakdown = _cost_breakdown(model)
    monthly_cost = sum(cost_breakdown.values())   # compute + usage, integer cents (ADR-009 Tiers 1–2)
    compute_list_cents = sum(c.monthly_cost for c in model.components.values())  # on-demand list (pre-discount)

    # Provenance LABEL only: have the engine's cost caveats/derivation/Metric strings agree with the
    # report's rate tag when the rates carry cited evidence. Reads `pricing.groundings` PRESENCE — never a
    # grounding value, never the math (the rate VALUES are the PricingRates fields, identical either way),
    # so it does not violate "grounding never changes a computed number" (the cost is byte-identical;
    # locked by test_rate_grounding_does_not_change_engine_cost). Stub → False → the exact ASSUMPTION text.
    # BILLED-LINE-AWARE: claim GROUNDED only if EVERY rate this model actually bills is grounded — a custom
    # rate (omitted by ground_pricing's fail-closed match) must NOT be swept under a blanket GROUNDED tag.
    _grounded_rates = model.pricing.groundings
    _billed_rates: set[str] = set()
    if cost_breakdown.get("egress"):   _billed_rates.add("egress")
    if cost_breakdown.get("storage"):  _billed_rates.add("storage")
    if cost_breakdown.get("requests"): _billed_rates.add("requests")
    if cost_breakdown.get("ai"):       _billed_rates.update(("llm_input", "llm_output"))
    if model.pricing.compute_pricing != "on_demand":
        _billed_rates.add(model.pricing.compute_pricing)
    rates_grounded = bool(_grounded_rates) and all(r in _grounded_rates for r in _billed_rates)
    # PRESENCE only (never a grounding value): do any component inputs carry grounding? Used to keep the
    # caveats provenance-ACCURATE without touching the math (same posture as rates_grounded).
    any_comp_grounded = any(c.groundings for c in model.components.values())
    cost_caveat = (
        "Cost = per-instance compute × the chosen pricing-model discount + declared usage "
        "(egress/storage/requests) + AI/LLM tokens (input/output) at GROUNDED (cited) rates (ADR-009 Tiers 1–2). "
        "Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. "
        "AI token rates span a wide model-class band (real prices vary ~100× by model). These per-unit rates "
        "are GROUNDED to cited benchmarks (see *Cost rate evidence*). Volumes are 0 unless a component declares "
        "them. Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope."
    ) if rates_grounded else (
        "Cost = per-instance compute × the chosen pricing-model discount + declared usage "
        "(egress/storage/requests) + AI/LLM tokens (input/output) at ASSUMPTION rates (ADR-009 Tiers 1–2). "
        "Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. "
        "AI token rates are a placeholder model class (real prices vary ~100× by model). All these rates "
        "are uncited ASSUMPTION seeds until grounded. Volumes are 0 unless a component declares them. "
        "Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope."
    )
    if any_comp_grounded:
        # Honesty: the "rates" provenance above is for per-UNIT rates only; the per-component COMPUTE
        # prices that usually dominate the cost carry their OWN provenance (incl. RECONCILE) — so the
        # "GROUNDED rates" label must NOT be read as "this cost is grounded".
        cost_caveat += (" NOTE: that 'rates' provenance is for the per-unit usage/AI/discount rates only — "
                        "the per-component COMPUTE prices that drive most of this figure carry their own "
                        "provenance (GROUNDED / RECONCILE / ASSUMPTION), shown per component in the Grounding "
                        "& reconciliation section; some may be RECONCILE (your value kept despite the cited band).")
    cap_caveat = (
        "Component capacities & prices have MIXED provenance — each is GROUNDED (matches a cited benchmark "
        "band), RECONCILE (your value kept despite falling outside the cited band), or ASSUMPTION (uncited), "
        "as marked in the Grounding & reconciliation section. None are calibrated to your stack. Accuracy is "
        "L0 (Directional) until field-calibrated (Doc 03)."
    ) if any_comp_grounded else (
        "Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to "
        "your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03)."
    )
    caveats = [
        "Analytical queueing approximation (M/M/c per component, via Erlang-C over each tier's "
        "instance count), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.",
        cap_caveat,
        "Percentiles are a FIXED SHAPE applied to the mean, not a second measurement. The ratio "
        f"p99/p50 is the constant {_P99_K / _P50_K:.2f} for every design at every load, so they "
        "carry no information the mean does not already carry — do not read p99 as an independently "
        "derived tail. The exponential shape is EXACT for a single M/M/c tier with one server and "
        "only approximate here, because each tier is M/M/c (whose sojourn is a mixture, not an "
        "exponential) and a path sums several of them. It tends to OVER-state the tail; treat "
        "p95/p99 as upper-bound directional figures. A real tail model needs the M/M/c sojourn "
        "distribution convolved along the path, and is not in v1.",
        cost_caveat,
        "Bottleneck identification and the relative ordering of components are far more "
        "reliable than absolute latency/cost numbers.",
    ]
    # A design whose components carry no price is not a free design — it is an unpriced one, and
    # "$0.00 / month" beside a 20-component architecture is a confidently wrong headline. The LLM
    # design path deliberately does not ask the model for cost (ingestion.py sets it to 0, because
    # the council must never author a number), so this is exactly the case that needs saying rather
    # than showing. Triggered on the total, so it also covers a canvas topology drawn without prices.
    if cost_breakdown.get("compute", 0) == 0 and model.components:
        caveats.append(
            "COST IS NOT MODELLED for this design: no component carries a price, so the monthly "
            "total reads as zero. That is missing input, not a free architecture — most likely the "
            "design came from the LLM path, which is deliberately never asked to produce a number. "
            "Set per-instance costs on the canvas, or start from a reference blueprint, before "
            "treating any cost figure here as meaningful."
        )

    # Honesty gap closed (2026-09-06): `_flow_latency_ms` sums EVERY component's sojourn along the
    # path, including a queue's. That is right for a synchronous hop and wrong for the usual reason a
    # queue exists — the producer enqueues and returns, and the consumer drains on its own time. The
    # engine has no async notion (it never branches on ComponentKind), so rather than quietly report a
    # background wait as user-facing latency, say so wherever a queue is actually on a modelled path.
    queued = sorted({
        comp_results[step.component_id].name
        for flow in model.flows for step in flow.path
        if model.components[step.component_id].kind is ComponentKind.QUEUE
    })
    if queued:
        caveats.append(
            f"Latency here treats {', '.join(queued)} as a SYNCHRONOUS hop — the queue's own wait is "
            f"added to the request's latency as if the caller blocks on it. If the consumer is "
            f"asynchronous (the usual reason to add a queue), real user-facing latency is lower than "
            f"shown, and the backlog and drain time that actually matter are not modelled at all. "
            f"The v1 engine has no async path; treat any flow through a queue as an upper bound."
        )

    if len(model.flows) > 1:
        # Honesty (engine audit): latency is computed for the DOMINANT (largest-share) flow only, so a
        # lower-share flow on a different (often more congested) path is NOT reflected in these figures.
        caveats.append(
            f"Headline latency (mean/p50/p95/p99) is for the DOMINANT flow — '{dom.name}' ({dom.share:.0%} "
            f"of traffic). Each flow's own latency is in the Per-flow latency table; a minority flow on a "
            f"different (often worse) path can differ sharply."
        )

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
        flow_latencies=flow_latencies,
        caveats=caveats,
        derivation=_derivation(model, comp_results, dom, rho_max, bottleneck, bp_safe, bp_theo, mean,
                               cost_breakdown, compute_list_cents, rates_grounded),
        metrics=_metrics(rho_max, bp_safe, bp_theo, mean, p50, p95, p99, monthly_cost, conf, rates_grounded),
        cost_breakdown=cost_breakdown,
        compute_list_cents=compute_list_cents,
        compute_pricing=model.pricing.compute_pricing,
    )
