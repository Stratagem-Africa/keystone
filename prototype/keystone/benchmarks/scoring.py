"""Engine scoring harness (Doc 03 §4; board Task #5; methodology in docs/11).

Scores the deterministic engine + a hand-built reference model against the SysSimulator
ground-truth corpus (component count + monthly cost band). Per Doc 03 §3, L0 accuracy is
ORDER-OF-MAGNITUDE cost + RELIABLE bottleneck/structure — NOT exact cost — so the
scorecard reports, per reference model:

  - cost band verdict: in-band / near (≤3× outside) / oom (≤10×) / off (>10×), with the
    factor outside the nearest band edge. Cost is compute/instance-only and the band's
    reference scale is undocumented, so this is a calibration signal, not a pass/fail.
  - bottleneck: the engine names a real, saturatable component (no ground-truth bottleneck
    in the corpus — this is a plausibility check).
  - breakpoint: stable — the max sustainable load is a model property, so it must be
    invariant to the current offered load (open network).
  - determinism: identical result on a re-run.
  - component count: model vs documented (informational — reference models capture the
    simulated HOT PATH, a subset of the full architecture).

Honest by construction: the scorecard ships a "where this is wrong" section and states how
many of the in-scope blueprints actually have a reference model (and that field-calibration is a GAP).
"""
from __future__ import annotations

from dataclasses import dataclass

from keystone.benchmarks import syssimulator_blueprints as corpus
from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.simulation import simulate

_TRUTH = {b[0]: b for b in corpus.BLUEPRINTS}  # key -> (key,name,cat,comps,lo,hi,v1)


@dataclass
class ScoreCard:
    key: str
    name: str
    category: str
    ref_rps: float
    comps_model: int
    comps_truth: int
    cost_engine: float
    cost_low: float
    cost_high: float
    cost_verdict: str            # in-band | near | oom | off
    cost_factor: float           # 1.0 if in band, else × outside the nearest edge
    bottleneck: str
    bottleneck_util: float
    bottleneck_ok: bool
    breakpoint_safe: float
    breakpoint_stable: bool
    deterministic: bool


def _cost_verdict(cost: float, lo: float, hi: float) -> tuple[str, float]:
    if lo <= cost <= hi:
        return "in-band", 1.0
    factor = (cost / hi) if cost > hi else (lo / cost if cost > 0 else float("inf"))
    if factor <= 3:
        return "near", factor
    if factor <= 10:
        return "oom", factor
    return "off", factor


def score_blueprint(key: str, build_fn, ref_rps: float) -> ScoreCard:
    truth = _TRUTH[key]
    _, name, category, comps_truth, lo, hi, _ = truth

    model = build_fn()
    sim = simulate(model)

    # Engine cost is integer minor units (cents, ADR-008); the corpus cost bands are in dollars,
    # so compare in dollars and report the scorecard cost in dollars.
    cost_dollars = sim.monthly_cost / 100
    verdict, factor = _cost_verdict(cost_dollars, lo, hi)

    # bottleneck plausibility: a named component carrying real load.
    bottleneck_ok = bool(sim.bottleneck_id) and sim.bottleneck_utilization > 0

    # breakpoint stability: the max sustainable load is a property of the model's
    # capacities, so in a linear open network it must be INVARIANT to the current offered
    # load. Re-simulate at 2× and confirm the safe breakpoint is unchanged (ratio ≈ 1).
    sim2 = simulate(model.scaled(model.workload.system_rps * 2))
    if sim.breakpoint_rps_safe and sim2.breakpoint_rps_safe not in (0, float("inf")):
        ratio = sim2.breakpoint_rps_safe / sim.breakpoint_rps_safe
        breakpoint_stable = abs(ratio - 1.0) < 0.02
    else:
        breakpoint_stable = False

    # determinism: identical result object on a re-run.
    deterministic = simulate(model) == sim

    return ScoreCard(
        key=key, name=name, category=category, ref_rps=ref_rps,
        comps_model=len(model.components), comps_truth=comps_truth,
        cost_engine=cost_dollars, cost_low=lo, cost_high=hi,
        cost_verdict=verdict, cost_factor=factor,
        bottleneck=sim.bottleneck_name, bottleneck_util=sim.bottleneck_utilization,
        bottleneck_ok=bottleneck_ok,
        breakpoint_safe=sim.breakpoint_rps_safe, breakpoint_stable=breakpoint_stable,
        deterministic=deterministic,
    )


def score_all() -> list[ScoreCard]:
    return [score_blueprint(k, fn, rps) for k, fn, rps in REFERENCE_MODELS]


def render_scorecard(cards: list[ScoreCard]) -> str:
    n_in_scope = len(corpus.in_scope())
    modeled = len(cards)
    in_band = sum(c.cost_verdict == "in-band" for c in cards)
    within_oom = sum(c.cost_verdict in ("in-band", "near", "oom") for c in cards)
    bottleneck_ok = sum(c.bottleneck_ok for c in cards)
    linear = sum(c.breakpoint_stable for c in cards)
    det = sum(c.deterministic for c in cards)

    L: list[str] = []
    L.append("# Keystone Engine Scorecard — vs SysSimulator ground truth")
    L.append("")
    L.append("> Accuracy level **L0 (Directional)**. This scores the **(reference-model + "
             "engine)** pipeline against documented component counts + monthly cost bands. "
             "The engine's math is exact given a model (see engine unit tests); a cost miss "
             "is usually **model calibration**, not engine error. Capacities/costs are SEED "
             "`ASSUMPTION`s (Doc 03) — not yet field-calibrated.")
    L.append("")
    L.append("## Coverage")
    if modeled >= n_in_scope:
        L.append(f"- **Reference models scored: {modeled} / {n_in_scope} in-scope blueprints — "
                 f"full in-scope coverage.** The remaining work is field-calibration, not coverage "
                 f"(see 'where this is wrong'); out-of-scope blueprints await the v2 engine.")
    else:
        L.append(f"- **Reference models scored: {modeled} / {n_in_scope} in-scope blueprints** "
                 f"({n_in_scope - modeled} still need a model built — a tracked GAP).")
    L.append("")
    L.append("## Summary")
    L.append(f"- **Cost band:** {in_band}/{modeled} in-band · {within_oom}/{modeled} within an order of magnitude.")
    L.append(f"- **Bottleneck identified (plausibility):** {bottleneck_ok}/{modeled}.")
    L.append(f"- **Breakpoint stable (load-invariant):** {linear}/{modeled}.")
    L.append(f"- **Deterministic:** {det}/{modeled}.")
    L.append("")
    L.append("## Per-model")
    L.append("")
    L.append("| Blueprint | Cat | @rps | Cost (engine) | Band | Verdict | Bottleneck (util) | Safe bp (rps) | Stable | Det | Comp m/t |")
    L.append("|---|---|--:|--:|--|--|--|--:|:--:|:--:|:--:|")
    for c in sorted(cards, key=lambda x: x.cost_verdict):
        v = c.cost_verdict if c.cost_verdict == "in-band" else f"{c.cost_verdict} {c.cost_factor:.1f}×"
        L.append(
            f"| {c.name} | {c.category} | {c.ref_rps:,.0f} | ${c.cost_engine:,.0f} | "
            f"${c.cost_low:,.0f}–${c.cost_high:,.0f} | {v} | {c.bottleneck} ({c.bottleneck_util*100:.0f}%) | "
            f"{c.breakpoint_safe:,.0f} | {'✓' if c.breakpoint_stable else '—'} | "
            f"{'✓' if c.deterministic else '—'} | {c.comps_model}/{c.comps_truth} |")
    L.append("")
    L.append("## Where this is wrong (read before trusting a score)")
    L.append("")
    L.append("- **Cost bands are scale-dependent and their reference scale is undocumented.** "
             "A model run at a heavier load than the band assumes will read 'over' even with a "
             "correct engine (e.g. a 12-instance high-traffic deployment vs a small-deployment band). "
             "This is calibration, not engine error.")
    L.append("- **Cost is compute/instance-only** — no egress/data-transfer or managed-service "
             "pricing — so it should land at or BELOW an all-in band; landing far above signals an "
             "over-provisioned reference model.")
    L.append("- **No ground-truth bottleneck/breakpoint in the corpus** — those columns are "
             "plausibility/sanity checks, not scored-vs-truth.")
    L.append("- **Component count is the simulated hot path**, a subset of the full architecture's "
             "documented count; it is informational, not a pass/fail.")
    L.append("- **Capacities/costs are SEED `ASSUMPTION`s, not field-calibrated** — even at full "
             "in-scope coverage, calibrating them to real benchmarks is the remaining L0→L1 **GAP** "
             "(Doc 03 §3); out-of-scope blueprints still await the v2 engine.")
    L.append("")
    return "\n".join(L)
