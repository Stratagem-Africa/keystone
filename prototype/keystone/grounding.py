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
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import keystone.benchmarks as _benchmarks
from keystone.knowledge_base import EmptyKnowledgeBase, KnowledgeBase, make_knowledge_base
from keystone.model import COMPUTE_PRICING_RETAINED_BP, Component, PricingRates, SystemModel
from keystone.provenance import GROUNDABLE_METRICS, Citation, Grounding
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


# --------------------------------------------------------------------------- #
# Cost-rate grounding (ADR-009 slice 2) — attach the RATIFIED rate evidence to PricingRates.
# Unlike the component corpus (stub-gated), the rate evidence (grounded_pricing_rates.json) was
# ratified (#71) and the rate VALUES already equal its grounded centrals; this only carries the
# citations + band onto the model so the report can show the rates as GROUNDED. No value changes.
# --------------------------------------------------------------------------- #
_RATE_EVIDENCE = Path(_benchmarks.__file__).parent / "grounded_pricing_rates.json"


def _load_rate_groundings() -> dict[str, Grounding]:
    """Build a `Grounding` per rate id from the ratified evidence file. Each Grounding carries the
    engine value + band + cited sources (≥1, enforced by Grounding). Read-only; produces no number."""
    doc = json.loads(_RATE_EVIDENCE.read_text(encoding="utf-8"))
    out: dict[str, Grounding] = {}
    for r in doc["rates"]:
        cites = tuple(
            Citation(
                source=c["source"], reference=c["url"],
                note=f'{c["quoted"]} — {c["conditions"]}'.replace("\n", " ").replace("\r", " ")[:500],
            )
            for c in r["citations"]
        )
        low, high = r["engine_band"]
        out[r["id"]] = Grounding(value=float(r["engine_value"]), unit=r["engine_unit"],
                                 confidence_low=float(low), confidence_high=float(high), citations=cites)
    return out


# rate id → the PricingRates field whose value the engine actually bills with (the 3 discounts are the
# global COMPUTE_PRICING_RETAINED_BP, not per-model). Used to verify "model value == grounded central"
# before certifying a rate as GROUNDED — so a custom/edited rate is never falsely certified.
_RATE_FIELD = {
    "egress": "egress_micro_usd_per_gb",
    "storage": "storage_micro_usd_per_gb_month",
    "requests": "request_micro_usd_per_thousand",
    "llm_input": "llm_input_micro_usd_per_1k_tokens",
    "llm_output": "llm_output_micro_usd_per_1k_tokens",
}


def _model_rate_value(pricing: PricingRates, rate_id: str):
    """The value the engine bills with for this rate id (per-model field, or the global discount bp)."""
    field = _RATE_FIELD.get(rate_id)
    return getattr(pricing, field) if field is not None else COMPUTE_PRICING_RETAINED_BP.get(rate_id)


def ground_pricing(model: SystemModel, kb: KnowledgeBase) -> SystemModel:
    """Attach the ratified cost-rate evidence to `model.pricing.groundings` so the report can show the
    rates as GROUNDED (with citation + band). Gated like the component grounding: a STRICT no-op under the
    stub KB (returns the original model), so default reports are byte-for-byte unchanged. Never changes a
    rate VALUE — only carries evidence."""
    # `kb` is an on/off ACTIVATION GATE, not the data source: the rate evidence is the single ratified
    # file (grounded_pricing_rates.json), independent of which component-KB is active. The stub means
    # "grounding off" → no-op; any live KB (today only curated) means "on" → attach the ratified rates.
    if isinstance(kb, EmptyKnowledgeBase):
        return model
    # FAIL CLOSED: certify a rate as GROUNDED only when the model's actual rate VALUE equals the grounded
    # central. A custom/edited rate (≠ central) is left ungrounded rather than falsely shown as cited —
    # the seed==central case (every shipped model) attaches all 8; a divergent rate is simply skipped.
    attached = {rid: g for rid, g in _load_rate_groundings().items()
                if _model_rate_value(model.pricing, rid) == g.value}
    if not attached:
        return model
    priced = dataclasses.replace(model.pricing, groundings=attached)
    return dataclasses.replace(model, pricing=priced)


def ground_model(model: SystemModel, kb: KnowledgeBase | None = None) -> SystemModel:
    """Report-generation entry point: attach BOTH component-input evidence (`enrich`, evidence-only) and
    cost-rate evidence (`ground_pricing`) so the report shows GROUNDED/RECONCILE + cited rates.

    ACTIVATION: `kb` defaults to the env-driven Knowledge Base with a **curated** default — grounding is
    ON for generated reports; set `KB_PROVIDER=stub` to turn it off. The LIBRARY `make_knowledge_base()`
    default stays `stub` (safe for programmatic/API/test callers); activation lives here, at the report
    layer. Evidence-only — changes no computed number (the engine never reads a grounding value)."""
    if kb is None:
        kb = make_knowledge_base(os.getenv("KB_PROVIDER") or "curated")
    return ground_pricing(enrich(model, kb).model, kb)
