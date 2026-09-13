"""The Keystone spec file — a `SystemModel` as a single, diffable, version-controllable artifact.

`docs/05 §4` has always specified this: *"The SystemModel … serialises to a single human-readable,
version-controllable spec file (YAML/JSON) — the artifact a user commits to their repo. Re-importing
it reproduces the design."* Until now it did not exist, which meant a design could not be saved,
versioned, diffed, reviewed or shared — every session started from an empty intent box.

Three properties this file is built to guarantee, in order of how much they matter:

1. **Lossless.** `from_dict(to_dict(m)) == m` for every model, including the evidence layer —
   per-component `groundings`, `match_context`, and `pricing.groundings`. Dropping those would round
   -trip the numbers while silently discarding *why they are believed*, turning a GROUNDED design
   into an uncited one. That is an honesty regression wearing a data-loss costume, so the test
   asserts equality on the whole model rather than a field subset.
2. **Deterministic.** The same model always emits byte-identical JSON — keys in declaration order,
   dict members sorted, floats via `repr` round-trip. A spec file that reorders itself is unusable in
   a diff, and a design you cannot review is not a design you can ratify.
3. **Fail-closed.** An unknown spec version, an unknown component kind, a bad reference or a
   malformed payload raises `ExportError`; it never half-loads. Imported models are run through
   `validate_model`, so the engine can never see a model this module admitted.

Prime directive: this module moves *inputs*. It holds no metric, and `simulate()` is untouched — a
spec file plus the engine reproduces the run, which is exactly what makes a shared design checkable.
"""
from __future__ import annotations

import json
from typing import Any

from .grounding import Citation, Grounding
from .ingestion import validate_model
from .model import (
    Assumption, Component, ComponentKind, Flow, FlowStep, PricingRates, SystemModel, Workload,
)

__all__ = ["SPEC_VERSION", "ExportError", "to_dict", "from_dict", "dumps", "loads", "orphans"]

# Bump only for a BREAKING shape change. `from_dict` refuses a version it does not know rather than
# guessing, because a silently mis-parsed spec is worse than a refused one.
SPEC_VERSION = 1


class ExportError(ValueError):
    """A spec file could not be written or read. Always raised instead of a partial model."""


# ─────────────────────────── write ───────────────────────────
def _citation_out(c: Citation) -> dict:
    return {"source": c.source, "reference": c.reference, "note": c.note}


def _grounding_out(g: Grounding) -> dict:
    return {
        "value": g.value,
        "unit": g.unit,
        "confidence_low": g.confidence_low,
        "confidence_high": g.confidence_high,
        "provenance": g.provenance,
        "measured_context": g.measured_context,
        "citations": [_citation_out(c) for c in g.citations],
    }


def _component_out(c: Component) -> dict:
    return {
        "id": c.id,
        "kind": c.kind.value,
        "name": c.name,
        "per_instance_rps": c.per_instance_rps,
        "instances": c.instances,
        "base_latency_ms": c.base_latency_ms,
        "monthly_cost_per_instance": c.monthly_cost_per_instance,
        "egress_gb_per_month": c.egress_gb_per_month,
        "storage_gb": c.storage_gb,
        "requests_per_month": c.requests_per_month,
        "llm_input_tokens_per_month": c.llm_input_tokens_per_month,
        "llm_output_tokens_per_month": c.llm_output_tokens_per_month,
        "provenance": c.provenance,
        # The evidence layer. Sorted so the file is stable in a diff.
        "groundings": {k: _grounding_out(g) for k, g in sorted(c.groundings.items())},
        "match_context": dict(sorted(c.match_context.items())),
    }


def to_dict(model: SystemModel) -> dict:
    """Serialise a model to a plain, JSON-safe dict. Deterministic and complete."""
    p = model.pricing
    return {
        "spec_version": SPEC_VERSION,
        "name": model.name,
        "workload": {
            "system_rps": model.workload.system_rps,
            "description": model.workload.description,
        },
        # Components are emitted as a LIST, not a dict, so the file has a stable declared order and
        # each entry carries its own id — a mapping keyed by id would duplicate it and invite drift.
        "components": [_component_out(c) for c in model.components.values()],
        "flows": [
            {
                "name": f.name,
                "share": f.share,
                "path": [{"component_id": s.component_id, "visit_prob": s.visit_prob}
                         for s in f.path],
            }
            for f in model.flows
        ],
        "assumptions": [
            {"subject": a.subject, "statement": a.statement, "confidence": a.confidence,
             "source": a.source, "provenance": a.provenance}
            for a in model.assumptions
        ],
        "domain_flags": list(model.domain_flags),
        "pricing": {
            "egress_micro_usd_per_gb": p.egress_micro_usd_per_gb,
            "storage_micro_usd_per_gb_month": p.storage_micro_usd_per_gb_month,
            "request_micro_usd_per_thousand": p.request_micro_usd_per_thousand,
            "llm_input_micro_usd_per_1k_tokens": p.llm_input_micro_usd_per_1k_tokens,
            "llm_output_micro_usd_per_1k_tokens": p.llm_output_micro_usd_per_1k_tokens,
            "compute_pricing": p.compute_pricing,
            "groundings": {k: _grounding_out(g) for k, g in sorted(p.groundings.items())},
        },
    }


def dumps(model: SystemModel, *, indent: int = 2) -> str:
    """The spec file as text. `allow_nan=False` fails closed rather than emitting invalid JSON."""
    return json.dumps(to_dict(model), indent=indent, allow_nan=False, ensure_ascii=False) + "\n"


# ─────────────────────────── read ───────────────────────────
def _req(d: dict, key: str, where: str):
    if key not in d:
        raise ExportError(f"{where}: missing required field {key!r}")
    return d[key]


def _citation_in(d: Any, where: str) -> Citation:
    if not isinstance(d, dict):
        raise ExportError(f"{where}: citation must be an object")
    return Citation(source=_req(d, "source", where),
                    reference=_req(d, "reference", where),
                    note=d.get("note", ""))


def _grounding_in(d: Any, where: str) -> Grounding:
    if not isinstance(d, dict):
        raise ExportError(f"{where}: grounding must be an object")
    return Grounding(
        value=_req(d, "value", where),
        unit=_req(d, "unit", where),
        confidence_low=_req(d, "confidence_low", where),
        confidence_high=_req(d, "confidence_high", where),
        citations=tuple(_citation_in(c, f"{where}.citations[{i}]")
                        for i, c in enumerate(d.get("citations", []))),
        provenance=d.get("provenance", "GROUNDED"),
        measured_context=d.get("measured_context", ""),
    )


def _component_in(d: Any, i: int) -> Component:
    where = f"components[{i}]"
    if not isinstance(d, dict):
        raise ExportError(f"{where}: must be an object")
    raw_kind = _req(d, "kind", where)
    try:
        kind = ComponentKind(raw_kind)
    except ValueError:
        raise ExportError(
            f"{where}: unknown component kind {raw_kind!r}; "
            f"known kinds are {sorted(k.value for k in ComponentKind)}") from None
    try:
        return Component(
            id=_req(d, "id", where),
            kind=kind,
            name=_req(d, "name", where),
            per_instance_rps=_req(d, "per_instance_rps", where),
            instances=d.get("instances", 1),
            base_latency_ms=d.get("base_latency_ms", 1.0),
            monthly_cost_per_instance=d.get("monthly_cost_per_instance", 0),
            egress_gb_per_month=d.get("egress_gb_per_month", 0),
            storage_gb=d.get("storage_gb", 0),
            requests_per_month=d.get("requests_per_month", 0),
            llm_input_tokens_per_month=d.get("llm_input_tokens_per_month", 0),
            llm_output_tokens_per_month=d.get("llm_output_tokens_per_month", 0),
            provenance=d.get("provenance", "assumption"),
            groundings={k: _grounding_in(g, f"{where}.groundings[{k}]")
                        for k, g in (d.get("groundings") or {}).items()},
            match_context=dict(d.get("match_context") or {}),
            )
    except ExportError:
        raise
    except ValueError as e:
        # Component.__post_init__ enforces the harm floor (positive capacity, integer money). Surface
        # it as ExportError so a caller catches ONE type for "this spec is not loadable".
        raise ExportError(f"{where}: {e}") from e


def from_dict(payload: Any) -> SystemModel:
    """Rebuild a model from a spec dict. Fail-closed: raises `ExportError`, never a partial model.

    The rebuilt model is run through `validate_model`, so a spec file can never introduce a model
    the engine would refuse — importing is held to the same bar as ingesting.
    """
    if not isinstance(payload, dict):
        raise ExportError("spec must be a JSON object")

    version = payload.get("spec_version")
    if version != SPEC_VERSION:
        raise ExportError(
            f"unsupported spec_version {version!r} (this build reads {SPEC_VERSION}). "
            f"Refusing rather than guessing at a shape it may not understand.")

    raw_components = _req(payload, "components", "spec")
    if not isinstance(raw_components, list):
        raise ExportError("components must be a list")
    components: dict[str, Component] = {}
    for i, rc in enumerate(raw_components):
        c = _component_in(rc, i)
        if c.id in components:
            raise ExportError(f"components[{i}]: duplicate component id {c.id!r}")
        components[c.id] = c

    flows: list[Flow] = []
    for i, rf in enumerate(_req(payload, "flows", "spec")):
        where = f"flows[{i}]"
        if not isinstance(rf, dict):
            raise ExportError(f"{where}: must be an object")
        path = []
        for j, rs in enumerate(_req(rf, "path", where)):
            cid = _req(rs, "component_id", f"{where}.path[{j}]")
            if cid not in components:
                raise ExportError(
                    f"{where}.path[{j}]: references unknown component {cid!r}")
            path.append(FlowStep(component_id=cid, visit_prob=rs.get("visit_prob", 1.0)))
        flows.append(Flow(name=_req(rf, "name", where), share=_req(rf, "share", where), path=path))

    rw = _req(payload, "workload", "spec")
    rp = payload.get("pricing") or {}
    defaults = PricingRates()
    model = SystemModel(
        name=_req(payload, "name", "spec"),
        components=components,
        flows=flows,
        workload=Workload(system_rps=_req(rw, "system_rps", "workload"),
                          description=rw.get("description", "")),
        assumptions=[
            Assumption(subject=_req(a, "subject", f"assumptions[{i}]"),
                       statement=_req(a, "statement", f"assumptions[{i}]"),
                       confidence=a.get("confidence", "med"),
                       source=a.get("source", "assumption"),
                       provenance=a.get("provenance", "ASSUMPTION"))
            for i, a in enumerate(payload.get("assumptions") or [])
        ],
        domain_flags=list(payload.get("domain_flags") or []),
        pricing=PricingRates(
            egress_micro_usd_per_gb=rp.get(
                "egress_micro_usd_per_gb", defaults.egress_micro_usd_per_gb),
            storage_micro_usd_per_gb_month=rp.get(
                "storage_micro_usd_per_gb_month", defaults.storage_micro_usd_per_gb_month),
            request_micro_usd_per_thousand=rp.get(
                "request_micro_usd_per_thousand", defaults.request_micro_usd_per_thousand),
            llm_input_micro_usd_per_1k_tokens=rp.get(
                "llm_input_micro_usd_per_1k_tokens", defaults.llm_input_micro_usd_per_1k_tokens),
            llm_output_micro_usd_per_1k_tokens=rp.get(
                "llm_output_micro_usd_per_1k_tokens", defaults.llm_output_micro_usd_per_1k_tokens),
            compute_pricing=rp.get("compute_pricing", defaults.compute_pricing),
            groundings={k: _grounding_in(g, f"pricing.groundings[{k}]")
                        for k, g in (rp.get("groundings") or {}).items()},
        ),
    )

    # Structural validation, but NOT connectivity. A spec file has to be able to carry any model the
    # engine will actually run, and `simulate()` does not require every component to sit on a flow —
    # `reference_models.build_distributed_cache` ships exactly that shape (a gossip coordinator that
    # costs money and is off the request path). This mirrors the decision already recorded for
    # reconciliation in docs/13: opt out of the connectivity check, and surface an unwired component
    # as a visible soft conflict rather than either hard-failing a valid design or silently
    # simulating it. `orphans()` below is that surface for spec files.
    try:
        validate_model(model, require_connected=False)
    except Exception as e:                                   # IngestError and friends
        raise ExportError(f"spec produced an invalid model: {e}") from e
    return model


def orphans(model: SystemModel) -> list[str]:
    """Component ids on no flow. They receive zero arrivals, so the engine reports 0% utilisation —
    which reads as "plenty of headroom" — while their cost still lands in the monthly total. A
    caller that shows a design should show this list; it is a design smell, not a crash."""
    on_a_flow = {step.component_id for flow in model.flows for step in flow.path}
    return sorted(cid for cid in model.components if cid not in on_a_flow)


def loads(text: str) -> SystemModel:
    """Read a spec file. A parse failure is an `ExportError`, not a raw json error."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExportError(f"not valid JSON: {e}") from e
    return from_dict(payload)
