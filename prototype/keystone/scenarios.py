"""Chaos & event scenarios — declarative perturbations of the canonical model.

**The prime directive holds by construction.** A scenario never produces a number and never
touches a `SimulationResult`. It returns a *modified `SystemModel`*, and `simulate()` is re-run
on it. Every figure a `ScenarioResult` carries is an engine output from one of two real runs
(baseline, perturbed); the few derived fields are plain arithmetic over those two engine outputs
(a ratio, a difference, a comparison), never an independent estimate. This is the same move
`arch_map.build_load_sweep` already makes for the load axis — a scenario is that idea generalised
from "more traffic" to "something went wrong".

Why this is not a port of SysSimulator's chaos panel: SysSimulator mutates a *running* simulation
and lets you watch. Keystone re-runs the *counterfactual* and shows you the two designs side by
side. That is deterministic, reproducible, and it inherits the whole honesty apparatus for free —
each side carries its own confidence, caveats and derivation.

Scope honesty (docs/03). This module deliberately ships only the perturbations the v1 analytical
model can express *truthfully*. See `UNMODELLED` for the ones it cannot, and why — they are not
omissions to be quietly filled in, they need either a v2 engine or a model change behind an ADR.
"""
from __future__ import annotations

import math

import dataclasses
from dataclasses import dataclass, field
from typing import Callable

from .model import ComponentKind, SystemModel
from .simulation import SAFE_UTILIZATION, SimulationResult, simulate

__all__ = [
    "Scenario", "ScenarioResult", "ScenarioSpec", "CATALOGUE", "UNMODELLED",
    "available", "apply_scenario", "run_scenario", "run_compound", "get", "catalogue_for",
]


# --------------------------------------------------------------------------------------
# What this module refuses to fake. Each entry names the honest blocker, not a TODO.
# --------------------------------------------------------------------------------------
UNMODELLED: dict[str, str] = {
    "hard_node_failure": (
        "A component with zero capacity. `Component` validation requires instances >= 1 and a "
        "finite positive per_instance_rps, so a dead component is not expressible. Faking it with "
        "a near-zero capacity would report a queueing collapse the model did not actually derive. "
        "Needs an explicit availability field on the canonical model, behind an ADR."
    ),
    "network_partition": (
        "There is no network model — flows carry visit probabilities, not links with loss or "
        "bandwidth. A partition is a topology change, not a parameter change."
    ),
    "burst_and_recovery": (
        "Thundering herd, retry storms and cache stampede *transients* need a time axis. The v1 "
        "engine is steady-state analytical (a closed form, not a trace), so it can answer 'what if "
        "this load were sustained' but never 'what happens in the ninety seconds after'. That is "
        "the v2 discrete-event upgrade (docs/02 GAP, docs/13 reference design)."
    ),
    "partial_degradation_over_time": (
        "Memory leaks and gradual degradation are trajectories. Same blocker as above: no time axis."
    ),
    "orchestration_and_provisioning_failures": (
        "A container that will not start, a pod stuck pending, a Terraform apply that fails — these "
        "are failures of the control plane, and the canonical model has no control plane. It models "
        "serving capacity, not how that capacity came to exist. Expressing them needs component "
        "kinds for the orchestrator and the provisioning pipeline, plus a notion of desired-vs-actual "
        "replicas, which is a model change behind an ADR. Their *effect* on serving capacity is "
        "already reachable today as lost instances or degraded capacity."
    ),
}


# --------------------------------------------------------------------------------------
# Perturbations. Each is a pure SystemModel -> SystemModel.
# --------------------------------------------------------------------------------------
def _replace_component(model: SystemModel, cid: str, **changes) -> SystemModel:
    comps = dict(model.components)
    comps[cid] = dataclasses.replace(comps[cid], **changes)
    return dataclasses.replace(model, components=comps)


def _scale_load(model: SystemModel, factor: float) -> SystemModel:
    wl = model.workload
    return dataclasses.replace(
        model, workload=dataclasses.replace(wl, system_rps=wl.system_rps * factor))


def _traffic_surge(model: SystemModel, target: str | None, magnitude: float) -> SystemModel:
    """Offered load multiplied. `magnitude` is the multiple (2x … 100x)."""
    return _scale_load(model, magnitude)


def _capacity_degraded(model: SystemModel, target: str, magnitude: float) -> SystemModel:
    """Each instance serves a `magnitude` FRACTION of its rated throughput (0.5 = half rate) — the
    steady-state shadow of a CPU spike, a noisy neighbour or a degraded node. Service *rate* falls;
    the queue discipline is unchanged."""
    return _replace_component(
        model, target, per_instance_rps=model.components[target].per_instance_rps * magnitude)


def _instance_loss(model: SystemModel, target: str, magnitude: float) -> SystemModel:
    """Lose `magnitude` instances from a horizontally-scaled tier. At least one must remain —
    losing the last is `hard_node_failure`, which this model cannot express (see UNMODELLED)."""
    return _replace_component(
        model, target, instances=model.components[target].instances - int(magnitude))


def _slow_dependency(model: SystemModel, target: str, magnitude: float) -> SystemModel:
    """Service time inflates `magnitude`x with capacity unchanged — a dependency that got slow but
    stayed up. Adds latency without moving utilisation, so it isolates the latency axis."""
    return _replace_component(
        model, target, base_latency_ms=model.components[target].base_latency_ms * magnitude)


def _cache_cold(model: SystemModel, target: str, magnitude: float) -> SystemModel:
    """Every read misses. In each flow that visits `target` (a cache), any *later* step whose
    visit probability was below 1.0 is the miss path — it now takes every request. Models a cold
    start, a flushed cache or an eviction storm as a sustained state, not as the transient spike
    (see UNMODELLED['burst_and_recovery'])."""
    flows = []
    for flow in model.flows:
        ids = [step.component_id for step in flow.path]
        if target not in ids:
            flows.append(flow)
            continue
        after = ids.index(target)
        path = [
            dataclasses.replace(step, visit_prob=1.0)
            if i > after and step.visit_prob < 1.0 else step
            for i, step in enumerate(flow.path)
        ]
        flows.append(dataclasses.replace(flow, path=path))
    return dataclasses.replace(model, flows=flows)


# --------------------------------------------------------------------------------------
# The catalogue
# --------------------------------------------------------------------------------------
def _has_replicas(model: SystemModel, target: str, magnitude: float = 1.0) -> tuple[bool, str]:
    n = model.components[target].instances
    lose = max(1, int(magnitude))
    return (n > lose,
            f"tier runs {n} instance(s); losing {lose} would leave {n - lose}. At least one must "
            f"remain — a fully dead tier is a hard failure this model cannot express "
            f"(see UNMODELLED['hard_node_failure'])")


def _has_miss_path(model: SystemModel, target: str, magnitude: float = 1.0) -> tuple[bool, str]:
    """`cache_cold` only means something where a miss path exists — a step *after* the cache whose
    visit probability is below certainty. Canvas-drawn topologies wire every step at 1.0 (see
    `topology.build_model_from_topology`), so there the cache absorbs nothing and going cold would
    change nothing. Rather than render a button that silently does nothing, we do not offer it."""
    for flow in model.flows:
        ids = [s.component_id for s in flow.path]
        if target not in ids:
            continue
        after = ids.index(target)
        if any(s.visit_prob < 1.0 for s in flow.path[after + 1:]):
            return True, ""
    return False, ("no miss path behind this cache — every downstream step is already visited on "
                   "every request, so a cold cache would change nothing")


@dataclass(frozen=True)
class Scenario:
    """A named, declarative perturbation. `apply` is pure and never reads a SimulationResult."""
    id: str
    name: str
    category: str          # traffic | capacity | data | dependency
    question: str          # the plain-English question this answers
    caveat: str            # what this perturbation does NOT model
    apply: Callable[[SystemModel, str | None, float], SystemModel] = field(compare=False, repr=False)
    targets: tuple[ComponentKind, ...] = ()   # () = whole-system, no target needed
    # Selectable severities. The first is the default. () = the scenario is binary (it either
    # happens or it does not) and `magnitude` is ignored.
    magnitudes: tuple[float, ...] = ()
    magnitude_unit: str = ""                  # how to render one, e.g. "x" or "% of rated rate"
    # Guard that decides whether this scenario is *meaningful* on a given target. Returning False
    # keeps it out of `available()` and makes `apply_scenario` fail closed — so the panel never
    # renders a card that would be a no-op dressed up as a survived scenario.
    precondition: Callable[[SystemModel, str, float], tuple[bool, str]] | None = field(
        default=None, compare=False, repr=False)

    @property
    def default_magnitude(self) -> float:
        return self.magnitudes[0] if self.magnitudes else 1.0

    def to_dict(self) -> dict:
        """Serialisable form for the API/UI catalogue (drops the callables)."""
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "question": self.question, "caveat": self.caveat,
            "targets": [k.value for k in self.targets],
            "magnitudes": list(self.magnitudes),
            "magnitude_unit": self.magnitude_unit,
            "default_magnitude": self.default_magnitude,
        }


_ANY_SERVING = (
    ComponentKind.APP_SERVER, ComponentKind.SQL_DB, ComponentKind.CACHE,
    ComponentKind.API_GATEWAY, ComponentKind.LOAD_BALANCER, ComponentKind.QUEUE,
    ComponentKind.REPLICA, ComponentKind.OBJECT_STORE, ComponentKind.EXTERNAL_API,
)

CATALOGUE: tuple[Scenario, ...] = (
    Scenario(
        id="traffic_surge", name="Traffic surge", category="traffic",
        question="How far can demand rise before the design stops holding?",
        caveat="A SUSTAINED multiple, not a burst. Retry amplification and thundering-herd "
               "transients need a time axis the v1 engine does not have.",
        apply=_traffic_surge, magnitudes=(2.0, 5.0, 10.0, 25.0, 100.0), magnitude_unit="x",
    ),
    Scenario(
        id="capacity_degraded", name="Capacity degraded", category="capacity",
        question="What happens if this tier serves at a fraction of its rated throughput?",
        caveat="The steady-state shadow of a CPU spike, noisy neighbour or degraded node — not the "
               "transient, and not a crash.",
        apply=_capacity_degraded, targets=_ANY_SERVING,
        magnitudes=(0.5, 0.25, 0.1, 0.01), magnitude_unit="x rated rate",
    ),
    Scenario(
        id="instance_loss", name="Lose instances", category="capacity",
        question="Can the remaining instances absorb the load?",
        caveat="At least one instance must remain; a fully dead tier is a hard failure this model "
               "cannot express.",
        apply=_instance_loss, targets=_ANY_SERVING, precondition=_has_replicas,
        magnitudes=(1.0, 2.0, 3.0, 5.0), magnitude_unit=" instance(s)",
    ),
    Scenario(
        id="cache_cold", name="Cache goes cold", category="data",
        question="If every read misses, does the datastore behind it survive?",
        caveat="A sustained 100% miss rate, not the stampede transient.",
        apply=_cache_cold, targets=(ComponentKind.CACHE,), precondition=_has_miss_path,
    ),
    Scenario(
        id="slow_dependency", name="Dependency slows", category="dependency",
        question="How much end-to-end latency does a slow dependency add?",
        caveat="Service time inflates; capacity is unchanged, so utilisation does not move. "
               "Timeouts, retries and circuit breakers are not modelled.",
        apply=_slow_dependency, targets=_ANY_SERVING,
        magnitudes=(2.0, 10.0, 100.0, 1000.0), magnitude_unit="x slower",
    ),
)

_BY_ID = {s.id: s for s in CATALOGUE}


def get(scenario_id: str) -> Scenario:
    """Look up a scenario. Fails closed on an unknown id (never silently no-ops)."""
    try:
        return _BY_ID[scenario_id]
    except KeyError:
        raise ValueError(f"unknown scenario id: {scenario_id!r}") from None


def available(model: SystemModel) -> list[tuple[Scenario, str | None]]:
    """Every (scenario, target_id) pair this model can actually run, in catalogue order.

    A scenario is only offered where it is truthful: targeted ones need a component of a matching
    kind, and `instance_loss` needs a tier already running 2+ instances.
    """
    out: list[tuple[Scenario, str | None]] = []
    for scenario in CATALOGUE:
        if not scenario.targets:
            out.append((scenario, None))
            continue
        for cid, comp in model.components.items():
            if comp.kind not in scenario.targets:
                continue
            if (scenario.precondition is not None
                    and not scenario.precondition(model, cid, scenario.default_magnitude)[0]):
                continue
            out.append((scenario, cid))
    return out


def _runnable_magnitudes(scenario: "Scenario", model: SystemModel, target_id: str | None) -> tuple:
    """The severities that are actually RUNNABLE against this target.

    `Scenario.magnitudes` is a fixed menu. For instance_loss that menu was offered verbatim against
    every tier, so the Twitter panel invited you to lose 5 instances from a Notification Queue that
    has 2 — a button the engine's own precondition would then refuse. Same defect as the cache_cold
    catalogue bug: the panel must never offer what the model cannot do.

    A tier with n instances can lose at most n-1. Losing ALL of them is a different scenario
    entirely — `hard_node_failure`, which is in UNMODELLED because a zero-capacity component is
    outside what this engine can represent.
    """
    if scenario.id != "instance_loss" or target_id is None:
        return scenario.magnitudes
    n = model.components[target_id].instances
    return tuple(m for m in scenario.magnitudes if m <= n - 1)


def catalogue_for(model: SystemModel) -> list[dict]:
    """The runnable catalogue as plain JSON, for the API/UI.

    One entry per (scenario, target) pair `available()` offers, so what the panel renders is exactly
    what the engine will accept — a card can never be a dead button. `unmodelled` rides along so the
    UI can show what is deliberately absent instead of leaving a silent gap.
    """
    return [
        {**scenario.to_dict(),
         "magnitudes": list(_runnable_magnitudes(scenario, model, target_id)),
         "target_id": target_id,
         "target_name": model.components[target_id].name if target_id else None,
         "instances": model.components[target_id].instances if target_id else None,
         "key": scenario.id if target_id is None else f"{scenario.id}:{target_id}"}
        for scenario, target_id in available(model)
    ]


def apply_scenario(model: SystemModel, scenario_id: str, target_id: str | None = None,
                   magnitude: float | None = None) -> SystemModel:
    """Return the perturbed model. Pure; the input model is never mutated.

    `magnitude` selects the severity. It must be one the scenario declares — an arbitrary value is
    refused rather than silently accepted, so a UI cannot invent a severity the catalogue never
    offered and the result stays reproducible from the catalogue alone.
    """
    scenario = get(scenario_id)
    if scenario.magnitudes:
        magnitude = scenario.default_magnitude if magnitude is None else magnitude
        if magnitude not in scenario.magnitudes:
            raise ValueError(
                f"scenario {scenario_id!r} does not offer magnitude {magnitude!r}; "
                f"choose one of {list(scenario.magnitudes)}")
    else:
        magnitude = 1.0
    if scenario.targets:
        if target_id is None:
            raise ValueError(f"scenario {scenario_id!r} requires a target component id")
        if target_id not in model.components:
            raise ValueError(f"unknown target component: {target_id!r}")
        kind = model.components[target_id].kind
        if kind not in scenario.targets:
            raise ValueError(
                f"scenario {scenario_id!r} does not apply to a {kind.value} component")
        if scenario.precondition is not None:
            ok, why = scenario.precondition(model, target_id, magnitude)
            if not ok:
                raise ValueError(f"scenario {scenario_id!r} is not meaningful here: {why}")
    return scenario.apply(model, target_id, magnitude)


@dataclass(frozen=True)
class ScenarioSpec:
    """One scenario, aimed and dialled. Several of these compose into a compound failure."""
    scenario_id: str
    target_id: str | None = None
    magnitude: float | None = None

    @property
    def key(self) -> str:
        return self.scenario_id if self.target_id is None else f"{self.scenario_id}:{self.target_id}"


@dataclass
class ScenarioResult:
    """Two real engine runs plus arithmetic over them. No field here is an independent estimate."""
    scenario_id: str
    scenario_name: str
    category: str
    question: str
    caveat: str
    target_id: str | None
    target_name: str | None
    baseline: SimulationResult
    perturbed: SimulationResult

    # --- derived: arithmetic over the two runs above, nothing else ---
    latency_multiple: float | None   # perturbed / baseline; None when the perturbed side is
                                     # OVERLOADED (unbounded latency) — see run_compound
    utilization_delta: float         # perturbed rho_max - baseline rho_max
    bottleneck_moved: bool
    survives: bool                   # perturbed bottleneck stays at/below SAFE_UTILIZATION
    verdict: str
    # Every scenario in the compound, in the order applied (one entry for a single scenario).
    applied: tuple[dict, ...] = ()

    @property
    def derivation(self) -> list[str]:
        """How the derived fields were obtained — mirrors the engine's own derivation trace."""
        return [
            f"baseline    = simulate(model)                    -> rho={self.baseline.bottleneck_utilization:.3f}, "
            f"latency={self.baseline.mean_latency_ms:.2f}ms",
            f"perturbed   = simulate({self.scenario_id}(model)) -> rho={self.perturbed.bottleneck_utilization:.3f}, "
            + (f"latency={self.perturbed.mean_latency_ms:.2f}ms"
               if math.isfinite(self.perturbed.mean_latency_ms) else "latency=unbounded (overloaded)"),
            (f"latency_multiple  = {self.perturbed.mean_latency_ms:.2f} / "
             f"{self.baseline.mean_latency_ms:.2f} = {self.latency_multiple:.2f}x"
             if self.latency_multiple is not None else
             f"latency_multiple  = UNDEFINED: the perturbed system is overloaded "
             f"(rho={self.perturbed.bottleneck_utilization:.3f} >= 1), so its queue grows without "
             f"limit and its latency is unbounded. There is no multiple to report — under this "
             f"scenario the design stops serving."),
            f"utilization_delta = {self.perturbed.bottleneck_utilization:.3f} - "
            f"{self.baseline.bottleneck_utilization:.3f} = {self.utilization_delta:+.3f}",
            f"survives          = perturbed rho {self.perturbed.bottleneck_utilization:.3f} "
            f"<= safe {SAFE_UTILIZATION:.2f} -> {self.survives}",
        ]


def _verdict(scenario: Scenario, base: SimulationResult, pert: SimulationResult,
             survives: bool, moved: bool) -> str:
    rho = pert.bottleneck_utilization
    if survives:
        return (f"Holds. {pert.bottleneck_name} reaches {rho:.0%} utilisation, still inside the "
                f"{SAFE_UTILIZATION:.0%} safe ceiling.")
    where = f"{pert.bottleneck_name} saturates at {rho:.0%}"
    if moved:
        where += f" — the constraint moves off {base.bottleneck_name}"
    return (f"Breaks. {where}; mean latency goes {base.mean_latency_ms:.0f}ms -> "
            f"{pert.mean_latency_ms:.0f}ms.")


def run_scenario(model: SystemModel, scenario_id: str, target_id: str | None = None,
                 magnitude: float | None = None) -> ScenarioResult:
    """Run one scenario as a counterfactual: simulate the design, then simulate it perturbed."""
    return run_compound(model, [ScenarioSpec(scenario_id, target_id, magnitude)])


def run_compound(model: SystemModel, specs: list[ScenarioSpec]) -> ScenarioResult:
    """Run several scenarios AT ONCE — "the cache is cold *and* the database is slow".

    Perturbations are applied in the given order to build one perturbed model, and the engine runs
    exactly twice: once on the design, once on the compound. That matters for honesty — a compound
    failure is not the sum of its parts' verdicts, because each perturbation changes the arrivals
    and utilisations the next one lands on. Simulating the composed model is the only way to get the
    interaction right.

    Deterministic: the same (model, specs) always yields the same result. Aiming two scenarios at
    the same component is refused, because the second silently compounding the first (halving an
    already-halved capacity) reads as one severity while being another.
    """
    if not specs:
        raise ValueError("run_compound needs at least one scenario")

    seen: set[str] = set()
    for spec in specs:
        if spec.key in seen:
            raise ValueError(
                f"{spec.key!r} appears twice — aim each scenario at a component once, and use its "
                f"magnitude to choose severity")
        seen.add(spec.key)

    baseline = simulate(model)
    perturbed_model = model
    applied: list[dict] = []
    for spec in specs:
        scenario = get(spec.scenario_id)
        magnitude = (scenario.default_magnitude if spec.magnitude is None else spec.magnitude)
        perturbed_model = apply_scenario(
            perturbed_model, spec.scenario_id, spec.target_id, spec.magnitude)
        applied.append({
            "scenario_id": scenario.id,
            "name": scenario.name,
            "category": scenario.category,
            "caveat": scenario.caveat,
            "target_id": spec.target_id,
            "target_name": model.components[spec.target_id].name if spec.target_id else None,
            "magnitude": magnitude if scenario.magnitudes else None,
            "magnitude_unit": scenario.magnitude_unit,
        })
    perturbed = simulate(perturbed_model)

    head = get(specs[0].scenario_id)
    compound = len(specs) > 1
    name = (" + ".join(a["name"] for a in applied) if compound else head.name)
    caveat = (" · ".join(dict.fromkeys(a["caveat"] for a in applied)) if compound else head.caveat)
    question = ("Does the design survive all of these at once?" if compound else head.question)

    base_lat = baseline.mean_latency_ms
    # A "latency multiple" only means something between two FINITE latencies. When the scenario
    # pushes the design past rho = 1 the queue is unstable and the perturbed latency is unbounded,
    # so there is no multiple — the honest answer is "it stops serving", not "inf x worse" and
    # certainly not the clamped constant the old rho=0.999 ceiling used to produce (46,051.7 ms
    # returned identically at 100x, 1,000x and 1,000,000x load). None renders as "unbounded"
    # through the same path the unbounded breakpoint already uses.
    multiple = (
        (perturbed.mean_latency_ms / base_lat)
        if base_lat > 0 and math.isfinite(perturbed.mean_latency_ms) and math.isfinite(base_lat)
        else None
    )
    moved = perturbed.bottleneck_id != baseline.bottleneck_id
    survives = perturbed.bottleneck_utilization <= SAFE_UTILIZATION

    return ScenarioResult(
        scenario_id=head.id if not compound else "+".join(a["scenario_id"] for a in applied),
        scenario_name=name,
        category=head.category,
        question=question,
        caveat=caveat,
        target_id=specs[0].target_id,
        target_name=applied[0]["target_name"],
        applied=tuple(applied),
        baseline=baseline,
        perturbed=perturbed,
        latency_multiple=multiple,
        utilization_delta=perturbed.bottleneck_utilization - baseline.bottleneck_utilization,
        bottleneck_moved=moved,
        survives=survives,
        verdict=_verdict(head, baseline, perturbed, survives, moved),
    )
