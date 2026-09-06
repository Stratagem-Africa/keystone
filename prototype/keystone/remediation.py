"""Remediation — given a design that no longer holds, propose the change that makes it hold.

This is the other half of `scenarios.py`. A scenario asks *"what breaks it?"*; a remedy asks
*"what fixes it?"*. Both work the same, prime-directive-safe way: the planner only ever chooses an
**input** (an instance count), and `simulate()` is re-run to decide whether that input actually
worked. No metric in a `RemediationPlan` is authored here — `before` and `after` are two real engine
runs, and the cost delta is the difference of their integer-cent totals.

The interesting part is not the arithmetic, it is **which lever is legitimate for which component**.
"Add more instances" is the right answer for a stateless tier and the WRONG answer for a single-writer
primary or a third-party API you do not operate. Getting that wrong is how a capacity tool produces a
confident, expensive, useless recommendation. So the levers are declared per `ComponentKind`, and
anything we cannot honestly size is reported as a **blocker** carrying the architectural options
instead of a fabricated instance count.

Known limit, stated up front rather than buried: the engine models capacity as
`per_instance_rps × instances` — strictly linear. Real systems do not scale linearly; contention and
cross-instance coherency bend the curve (Gunther's Universal Scalability Law), and a shared lock, a
hot shard or a connection-pool ceiling can flatten it entirely. Treat a recommended instance count as
a **floor** — the fewest instances the model needs — never as a promise.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

from .model import ComponentKind, SystemModel
from .simulation import SAFE_UTILIZATION, SimulationResult, simulate

__all__ = [
    "Remedy", "Blocker", "RemediationPlan", "plan_capacity",
    "SCALE_OUT_KINDS", "BLOCKED_KINDS", "SCALING_LIMITS",
]

# Instance count is a genuine lever for these: work is shared across independent workers and the
# model's linear capacity assumption is a defensible first approximation.
SCALE_OUT_KINDS: frozenset[ComponentKind] = frozenset({
    ComponentKind.APP_SERVER,
    ComponentKind.API_GATEWAY,
    ComponentKind.LOAD_BALANCER,
    ComponentKind.CDN,
    ComponentKind.CACHE,
    ComponentKind.QUEUE,
    ComponentKind.OBJECT_STORE,
    ComponentKind.REPLICA,
})

# Adding instances here is not a fix — it is a category error. Each carries the architectural
# options a competent reviewer would actually reach for, unsized, because sizing them needs a
# modelling change (a new topology, a read/write split) this planner is not entitled to invent.
BLOCKED_KINDS: dict[ComponentKind, str] = {
    ComponentKind.SQL_DB: (
        "A relational primary is a single writer — adding instances does not add write capacity. "
        "The real options are: scale the primary vertically; move reads onto replicas (needs a "
        "read/write split in the flows); put a cache in front of the hot read path; or shard by a "
        "key with no cross-shard transactions. Each changes the topology, so Keystone will not "
        "size one for you here."
    ),
    ComponentKind.EXTERNAL_API: (
        "You do not operate this dependency, so you cannot scale it. The options are a higher "
        "service tier or raised rate limit, caching or batching to cut call volume, or an "
        "asynchronous path so its latency stops blocking the request. All are commercial or "
        "architectural decisions, not a capacity number."
    ),
    ComponentKind.CLIENT: (
        "A traffic source is demand, not supply — there is no capacity here to add. If this is the "
        "constraint, the levers are on the demand side: shed or shape load with rate limiting and "
        "backpressure, cut the number of calls per user journey, batch or debounce chatty clients, "
        "or move work off the synchronous path. None of those are a capacity number."
    ),
}

# Published with every plan. These are the ways the recommendation can be wrong.
SCALING_LIMITS: tuple[str, ...] = (
    "Capacity is modelled as per_instance_rps × instances — perfectly linear. Real systems show "
    "diminishing returns from contention and cross-instance coherency (Universal Scalability Law), "
    "so a recommended instance count is a floor, not a guarantee.",
    "Horizontal scaling cannot relieve a bottleneck that is not throughput-shaped: a hot key or "
    "shard, a global lock, a single-writer primary or an exhausted connection pool all survive "
    "adding instances.",
    "The engine sizes for steady state. It says nothing about how fast you can actually acquire the "
    "instances, whether a cold start or warm-up applies, or whether the load arrives as a burst.",
    "The cost delta is the engine's cost model at the configured pricing, and counts compute and "
    "declared usage only. Migration, operational and licence costs are not modelled.",
    "Each component is sized against its own arrival rate. Second-order effects of the new "
    "topology — added coordination, larger fan-out, more connections against the same database — "
    "are not modelled.",
)

_MAX_INSTANCES = 100_000   # sanity bound; past this the answer is "redesign", not "add nodes"
_MAX_ROUNDS = 8


@dataclass(frozen=True)
class Remedy:
    """One proposed change. `to_instances` is an INPUT the planner chose; whether it works is
    decided by re-running the engine, not asserted here."""
    component_id: str
    component_name: str
    kind: str
    lever: str            # currently always "scale_out"
    from_instances: int
    to_instances: int
    reason: str

    @property
    def added(self) -> int:
        return self.to_instances - self.from_instances

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id, "component_name": self.component_name,
            "kind": self.kind, "lever": self.lever,
            "from_instances": self.from_instances, "to_instances": self.to_instances,
            "added": self.added, "reason": self.reason,
        }


@dataclass(frozen=True)
class Blocker:
    """A saturated component this planner will not pretend to fix with a number."""
    component_id: str
    component_name: str
    kind: str
    utilization: float
    guidance: str

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id, "component_name": self.component_name,
            "kind": self.kind, "utilization": self.utilization, "guidance": self.guidance,
        }


@dataclass
class RemediationPlan:
    target_rps: float
    ceiling: float
    before: SimulationResult
    after: SimulationResult
    remedies: list[Remedy]
    blockers: list[Blocker]
    holds: bool
    monthly_cost_delta_cents: int    # after.monthly_cost - before.monthly_cost (both engine outputs)
    limits: tuple[str, ...] = SCALING_LIMITS
    derivation: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if not self.remedies and not self.blockers:
            return (f"No change needed — every component stays at or under the "
                    f"{self.ceiling:.0%} ceiling at {self.target_rps:,.0f} req/s.")
        if self.holds:
            added = ", ".join(
                f"{r.component_name} ×{r.from_instances}→×{r.to_instances}" for r in self.remedies)
            delta = self.monthly_cost_delta_cents
            money = f"${abs(delta) // 100:,}.{abs(delta) % 100:02d}"
            return (f"Holds at {self.target_rps:,.0f} req/s with {added}. "
                    f"Peak utilisation falls to {self.after.bottleneck_utilization:.0%}, "
                    f"for {money}/month more.")
        names = ", ".join(b.component_name for b in self.blockers)
        return (f"Cannot be fixed by adding instances. {names} "
                f"{'is' if len(self.blockers) == 1 else 'are'} the binding constraint and "
                f"need{'s' if len(self.blockers) == 1 else ''} an architectural change.")


def _required_instances(arrival_rps: float, per_instance_rps: float, ceiling: float) -> int:
    """Fewest whole instances that keep arrival/(capacity) at or under `ceiling`.

    This chooses an INPUT to hand back to the engine. It is the same move
    `arch_map.build_load_sweep` makes when it picks the loads to re-simulate at.
    """
    if per_instance_rps <= 0 or ceiling <= 0:
        return 1
    return max(1, math.ceil(arrival_rps / (per_instance_rps * ceiling)))


def plan_capacity(model: SystemModel, target_rps: float | None = None, *,
                  ceiling: float = SAFE_UTILIZATION) -> RemediationPlan:
    """Find the smallest instance-count change that keeps every component under `ceiling`.

    Deterministic: the same (model, target, ceiling) always yields the same plan. Sizing is direct
    rather than a search — arrivals are fixed by the flows, so adding instances changes capacity
    without changing demand — and every resulting figure comes from re-running `simulate()`.
    """
    working = model
    if target_rps is not None:
        working = dataclasses.replace(
            model, workload=dataclasses.replace(model.workload, system_rps=target_rps))
    load = working.workload.system_rps

    before = simulate(working)
    derivation: list[str] = [
        f"Baseline at {load:,.0f} req/s: peak utilisation "
        f"{before.bottleneck_utilization:.3f} on {before.bottleneck_name}.",
        f"Target: every component at or under the {ceiling:.0%} ceiling.",
    ]

    remedies: dict[str, Remedy] = {}
    blockers: dict[str, Blocker] = {}
    current = working

    for round_no in range(_MAX_ROUNDS):
        sim = simulate(current)
        over = [(cid, cr) for cid, cr in sim.components.items() if cr.utilization > ceiling]
        if not over:
            break

        changed = False
        for cid, cr in sorted(over, key=lambda kv: -kv[1].utilization):
            comp = current.components[cid]
            if comp.kind not in SCALE_OUT_KINDS:
                if cid not in blockers:
                    blockers[cid] = Blocker(
                        component_id=cid, component_name=comp.name, kind=comp.kind.value,
                        utilization=cr.utilization,
                        guidance=BLOCKED_KINDS.get(
                            comp.kind, "This component type has no modelled scaling lever."))
                    derivation.append(
                        f"{comp.name} is at {cr.utilization:.0%} but is a {comp.kind.value} — "
                        f"adding instances is not a valid lever; reported as a blocker.")
                continue

            needed = _required_instances(cr.arrival_rps, comp.per_instance_rps, ceiling)
            if needed <= comp.instances or needed > _MAX_INSTANCES:
                if needed > _MAX_INSTANCES and cid not in blockers:
                    blockers[cid] = Blocker(
                        component_id=cid, component_name=comp.name, kind=comp.kind.value,
                        utilization=cr.utilization,
                        guidance=(f"Would need more than {_MAX_INSTANCES:,} instances at this load. "
                                  f"That is a redesign, not a scaling decision."))
                continue

            origin = remedies[cid].from_instances if cid in remedies else comp.instances
            remedies[cid] = Remedy(
                component_id=cid, component_name=comp.name, kind=comp.kind.value,
                lever="scale_out", from_instances=origin, to_instances=needed,
                reason=(f"receives {cr.arrival_rps:,.0f} req/s; "
                        f"{needed} × {comp.per_instance_rps:,.0f} req/s keeps it at or under "
                        f"{ceiling:.0%}"))
            derivation.append(
                f"{comp.name}: {cr.arrival_rps:,.0f} / ({comp.per_instance_rps:,.0f} × "
                f"{ceiling:.2f}) → {needed} instance(s), up from {comp.instances}.")
            comps = dict(current.components)
            comps[cid] = dataclasses.replace(comp, instances=needed)
            current = dataclasses.replace(current, components=comps)
            changed = True

        if not changed:
            break
        if round_no == _MAX_ROUNDS - 1:
            derivation.append(
                f"Stopped after {_MAX_ROUNDS} rounds — the design did not settle; treat this plan "
                f"as incomplete.")

    after = simulate(current)
    holds = all(cr.utilization <= ceiling for cr in after.components.values())
    derivation.append(
        f"Re-simulated the changed design: peak utilisation {after.bottleneck_utilization:.3f} "
        f"on {after.bottleneck_name} — {'within' if holds else 'still above'} the ceiling.")
    derivation.append(
        f"Monthly cost {before.monthly_cost:,} → {after.monthly_cost:,} minor units "
        f"(delta {after.monthly_cost - before.monthly_cost:+,}).")

    return RemediationPlan(
        target_rps=load,
        ceiling=ceiling,
        before=before,
        after=after,
        remedies=sorted(remedies.values(), key=lambda r: -r.added),
        blockers=sorted(blockers.values(), key=lambda b: -b.utilization),
        holds=holds,
        monthly_cost_delta_cents=after.monthly_cost - before.monthly_cost,
        derivation=derivation,
    )
