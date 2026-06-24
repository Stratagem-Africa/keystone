"""Grounding seam (ADR-006, the L0→L1 lever) — attach cited KB evidence to a model's INPUT numbers.

This is where the curated benchmark corpus stops being inert: `enrich()` asks the Knowledge Base to
ground each component's three INPUT metrics (`per_instance_rps`, `base_latency_ms`,
`monthly_cost_per_instance`) and, when evidence exists, attaches it to `Component.groundings` so the
report can show GROUNDED (with citation + band) vs ASSUMPTION.

Prime directive (the whole reason this module exists and is kept honest):
  - It only ever touches an **input** a human modeler/blueprint already sets — never a derived number.
    The KB seam itself (`require_groundable_metric`) cannot return a derived metric, and this module
    **does not import `keystone.simulation`** (a reviewer-checkable separation: it cannot compute a result).
  - **Evidence-only by default** (`override=False`): it attaches evidence and classifies the modeler's
    value as in-band / out-of-band, but moves NO value — so `simulate()` computes byte-identical numbers.
  - **`override=True`** is the sanctioned "change an input" lever: it substitutes the grounded central
    BEFORE the engine runs. An out-of-band modeler value is always reported for **reconciliation** and
    is **kept, never silently clobbered** — even under override only matched metrics move.

Default-off: under `KB_PROVIDER=stub` the KB grounds nothing, so `enrich()` returns the original model
unchanged and the report renders zero new bytes. Activation is a manual `KB_PROVIDER=curated` trigger.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from keystone.knowledge_base import KnowledgeBase
from keystone.model import Component, SystemModel
from keystone.provenance import GROUNDABLE_METRICS, Grounding
# NOTE: this module deliberately does NOT depend on the engine module (keystone/simulation.py) —
# grounding rewrites inputs, never a computed result (a reviewer-checkable separation).

_COST_METRIC = "monthly_cost_per_instance"


@dataclass(frozen=True)
class GroundedInput:
    """One input metric matched to evidence. `in_band` = the modeler's value sits inside the cited
    confidence band (GROUNDED); False = it falls outside (RECONCILE — the value was kept, not moved)."""
    component_id: str
    component_name: str
    metric: str
    modeler_value: float
    grounding: Grounding
    in_band: bool


@dataclass
class EnrichResult:
    model: SystemModel                       # the (possibly) enriched model to simulate + report
    groundings: list[GroundedInput] = field(default_factory=list)

    @property
    def out_of_band(self) -> list[GroundedInput]:
        return [g for g in self.groundings if not g.in_band]


def _override_value(metric: str, grounded: float):
    """The value to write when override is on. Money stays **integer cents** (harm floor, ADR-008):
    round-half-up the grounded central to a whole cent. Capacity/latency are floats the engine reads
    directly. `Component.__post_init__` re-validates on `replace`, so a bad type still fails closed."""
    if metric == _COST_METRIC:
        return int(grounded + 0.5)   # grounded >= 0 (enforced by Grounding); round-half-up to int cents
    return grounded


def enrich(model: SystemModel, kb: KnowledgeBase, *, override: bool = False) -> EnrichResult:
    """Attach KB evidence to the model's input metrics. Returns the (possibly enriched) model plus the
    list of matched metrics. Default (`override=False`) moves no value — only attaches evidence — so the
    engine output is unchanged. Context-free (component-kind only) matching in this first slice."""
    found: list[GroundedInput] = []
    new_components: dict[str, Component] = {}
    changed = False

    for cid, comp in model.components.items():
        attach: dict[str, Grounding] = {}
        overrides: dict[str, object] = {}
        for metric in sorted(GROUNDABLE_METRICS):
            g = kb.ground(comp.kind, metric)   # context=None: match by component kind alone (slice 1)
            if g is None:
                continue
            modeler_value = float(getattr(comp, metric))
            in_band = g.confidence_low <= modeler_value <= g.confidence_high
            attach[metric] = g
            found.append(GroundedInput(cid, comp.name, metric, modeler_value, g, in_band))
            if override:
                overrides[metric] = _override_value(metric, g.value)

        if attach or overrides:
            comp = dataclasses.replace(comp, groundings={**comp.groundings, **attach}, **overrides)
            changed = True
        new_components[cid] = comp

    if not changed:
        return EnrichResult(model=model, groundings=found)   # strict no-op (e.g. under the stub KB)
    return EnrichResult(model=dataclasses.replace(model, components=new_components), groundings=found)
