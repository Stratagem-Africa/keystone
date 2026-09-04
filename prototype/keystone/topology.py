"""Canvas topology -> validated SystemModel (deterministic, NO LLM).

An interactive canvas gives an explicit, typed topology (nodes + edges). This converts it
straight into the engine's `SystemModel`, bypassing the LLM/ingestion path entirely — the
user *drew* the structure, so there is nothing to infer. The deterministic engine then
simulates that model exactly as it does for a blueprint.

Prime directive intact: this only builds INPUTS (component capacities + flows). Every metric
(utilisation / bottleneck / latency / cost) still comes solely from `simulation.simulate`.
Per-component capacity/latency default to the grounded benchmark corpus (ADR-006) per kind
where available, else a documented seed — always tagged `ASSUMPTION` and overridable per node.
Fail-closed: an invalid topology raises `IngestError` via `validate_model` before the engine
ever sees it.

Input `topology` shape (matches the canvas JSON):
    {"name": "...", "system_rps": 10000,
     "nodes": [{"id","kind","name",  # required
                "per_instance_rps","instances","base_latency_ms","monthly_cost_cents"}],  # optional overrides
     "edges": [["from_id","to_id"], ...]}
"""
from __future__ import annotations

from keystone.ingestion import validate_model
from keystone.model import (
    Assumption, Component, ComponentKind, Flow, FlowStep, SystemModel, Workload,
)

# Documented seed defaults per kind: (per_instance_rps, base_latency_ms, monthly_cost_cents).
# Same seed benchmarks the blueprints use (provenance=ASSUMPTION, to be field-calibrated). Where the
# curated corpus (ADR-006) has a grounded central for rps/latency, it overlays these below.
_KIND_DEFAULTS: dict[ComponentKind, tuple[float, float, int]] = {
    ComponentKind.CDN:           (50_000.0, 20.0,  5_000),
    ComponentKind.LOAD_BALANCER: (30_000.0, 1.0,   2_500),
    ComponentKind.API_GATEWAY:   (5_000.0,  5.0,   3_000),
    ComponentKind.APP_SERVER:    (1_200.0,  8.0,   3_500),
    ComponentKind.CACHE:         (100_000.0, 0.5,  18_000),
    ComponentKind.SQL_DB:        (8_000.0,  5.0,   42_000),
    ComponentKind.REPLICA:       (8_000.0,  5.0,   30_000),
    ComponentKind.QUEUE:         (20_000.0, 2.0,   4_000),
    ComponentKind.OBJECT_STORE:  (5_500.0,  30.0,  2_000),
    ComponentKind.EXTERNAL_API:  (100.0,    140.0, 0),
}
_MAX_FLOWS = 8   # cap derived flows so a dense graph can't explode into thousands of paths


def _grounded_defaults() -> dict[ComponentKind, tuple[float, float]]:
    """Overlay grounded corpus centrals (rps, latency) onto the seed defaults where available.
    Failure-safe: a missing/broken corpus just leaves the seed defaults in place."""
    out: dict[ComponentKind, tuple[float, float]] = {}
    try:
        from keystone.benchmarks.benchmark_corpus import CuratedKnowledgeBase
        kb = CuratedKnowledgeBase.from_default_corpus()
    except Exception:
        return out
    for kind in ComponentKind:
        rps = kb.ground(kind, "per_instance_rps")
        lat = kb.ground(kind, "base_latency_ms")
        if rps is not None or lat is not None:
            base = _KIND_DEFAULTS.get(kind)
            out[kind] = (rps.value if rps is not None else (base[0] if base else 1_000.0),
                         lat.value if lat is not None else (base[1] if base else 1.0))
    return out


def _component_from_node(node: dict, grounded: dict) -> Component:
    kind = ComponentKind(str(node["kind"]))
    seed = _KIND_DEFAULTS.get(kind, (1_000.0, 1.0, 1_000))
    g = grounded.get(kind)
    rps = float(node.get("per_instance_rps") or (g[0] if g else seed[0]))
    lat = node.get("base_latency_ms")
    lat = float(lat) if lat is not None else (g[1] if g else seed[1])
    cost = int(node.get("monthly_cost_cents", seed[2]))
    return Component(
        id=str(node["id"]), kind=kind, name=str(node.get("name") or node["id"]),
        per_instance_rps=rps, instances=int(node.get("instances", 1)),
        base_latency_ms=lat, monthly_cost_per_instance=cost, provenance="ASSUMPTION",
    )


def _derive_flows(comp_ids: list[str], edges: list, client_ids: set[str]) -> list[Flow]:
    """Turn the graph into engine flows = entry->terminal request paths (client nodes excluded from the
    path; they are the traffic SOURCE, not a served component). Simple paths, capped at _MAX_FLOWS,
    equal shares summing to 1.0. Falls back to one flow over all components when the graph has no usable
    edges (e.g. a freshly-dropped node), so any topology is at least simulatable."""
    served = [c for c in comp_ids if c not in client_ids]
    if not served:
        return []
    adj: dict[str, list[str]] = {c: [] for c in served}
    indeg: dict[str, int] = {c: 0 for c in served}
    for a, b in edges:
        if a in adj and b in adj:            # component->component edge
            adj[a].append(b); indeg[b] += 1
        elif a in client_ids and b in adj:   # client->component: b is an entry
            indeg.setdefault(b, indeg.get(b, 0))
    fed_by_client = {b for a, b in edges if a in client_ids and b in adj}
    entries = [c for c in served if indeg[c] == 0 or c in fed_by_client] or [served[0]]

    paths: list[list[str]] = []
    def walk(node: str, acc: list[str], seen: set[str]) -> None:
        if len(paths) >= _MAX_FLOWS:
            return
        acc = acc + [node]
        nxts = [n for n in adj[node] if n not in seen]
        if not nxts:
            paths.append(acc); return
        for n in nxts:
            walk(n, acc, seen | {node})
    for e in entries:
        if len(paths) >= _MAX_FLOWS:
            break
        walk(e, [], set())

    if not paths:
        paths = [served]                     # no edges at all -> one flow touching everything
    share = round(1.0 / len(paths), 6)
    flows = [Flow(name=f"path {i+1}: " + " → ".join(p), share=share,
                  path=[FlowStep(cid) for cid in p]) for i, p in enumerate(paths)]
    # fix rounding drift so shares sum to exactly 1.0 (validate_model checks ~1.0)
    drift = round(1.0 - sum(f.share for f in flows), 6)
    if flows and drift:
        flows[0] = Flow(flows[0].name, round(flows[0].share + drift, 6), flows[0].path)
    return flows


def build_model_from_topology(topology: dict, *, name: str | None = None,
                              system_rps: float | None = None) -> SystemModel:
    """Deterministically build a validated SystemModel from a canvas topology. Raises IngestError
    (fail-closed, via validate_model) if the resulting model is invalid — the engine never sees a
    bad model. No LLM, no network; grounded corpus defaults are best-effort."""
    nodes = topology.get("nodes") or []
    if not nodes:
        from keystone.ingestion import IngestError
        raise IngestError("topology has no nodes")
    edges = [list(e) for e in (topology.get("edges") or [])]
    grounded = _grounded_defaults()

    client_ids = {str(n["id"]) for n in nodes if str(n.get("kind")) == ComponentKind.CLIENT.value}
    components = {str(n["id"]): _component_from_node(n, grounded)
                 for n in nodes if str(n.get("kind")) != ComponentKind.CLIENT.value}
    if not components:
        from keystone.ingestion import IngestError
        raise IngestError("topology has only client nodes — nothing to simulate")

    flows = _derive_flows(list(components), edges, client_ids)
    model = SystemModel(
        name=name or str(topology.get("name") or "Canvas design"),
        components=components,
        flows=flows,
        workload=Workload(system_rps=float(system_rps if system_rps is not None
                                           else topology.get("system_rps") or 1_000),
                          description="from interactive canvas"),
        assumptions=[Assumption("topology", "Structure supplied directly on the canvas; per-component "
                                "capacities are seed/grounded defaults unless edited.",
                                confidence="low", source="user")],
    )
    validate_model(model)   # fail closed — never hand the engine an invalid model
    return model
