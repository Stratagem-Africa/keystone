"""Architecture map — an interactive, engine-driven view of a validated design (Doc 04 / docs/09).

Serialises the canonical `SystemModel` + the deterministic `SimulationResult` into (1) a plain
JSON-able data map and (2) a self-contained interactive HTML page (like `report.py` emits
markdown). It is a *layered topology* where every RESULT number is engine-computed — inputs are
declared and cited, never invented — and every node wears its provenance, the engine's bottleneck /
SPOF / saturation states, the cited confidence evidence, the L0 (Directional) label, the high-stakes
expert-review flag, and a mandatory "where this is wrong" panel. A diagramming tool draws boxes; this
draws a *validated, cited, honest* design.

Prime directive: this only READS an already-computed `SimulationResult` (+ the model's declared
inputs and cited evidence). It produces NO number of its own and never authors a number envelope —
so the string that names that envelope's constructor is deliberately absent from this file (the
ADR-007 guard scans for it). Deterministic + offline: no LLM, no timestamp, no randomness, so the
same (model, sim) yields byte-identical output — a committed golden, exactly like the md reports.
"""
from __future__ import annotations

import json
import math

from keystone import __version__ as _ENGINE_VERSION
from keystone.council import is_high_stakes
from keystone.model import ComponentKind, SystemModel
from keystone.provenance import GROUNDABLE_METRICS
from keystone.simulation import SimulationResult

# Canonical left→right layer bands for layout. Every ComponentKind maps to exactly one band, so any
# model lays out deterministically. This is a DISPLAY grouping only — not an engine concept.
_LAYERS: tuple[tuple[str, str, tuple[ComponentKind, ...]], ...] = (
    ("client",   "Client",   (ComponentKind.CLIENT,)),
    ("edge",     "Edge",     (ComponentKind.CDN, ComponentKind.LOAD_BALANCER)),
    ("gateway",  "Gateway",  (ComponentKind.API_GATEWAY,)),
    ("compute",  "Compute",  (ComponentKind.APP_SERVER,)),
    ("cache",    "Cache",    (ComponentKind.CACHE,)),
    ("data",     "Data",     (ComponentKind.SQL_DB, ComponentKind.REPLICA, ComponentKind.OBJECT_STORE)),
    ("async",    "Async",    (ComponentKind.QUEUE,)),
    ("external", "External", (ComponentKind.EXTERNAL_API,)),
)
_KIND_LAYER: dict[ComponentKind, tuple[str, str, int]] = {
    k: (lid, label, i) for i, (lid, label, kinds) in enumerate(_LAYERS) for k in kinds
}
# A stable palette assigned to flows in model order (display only — carries no meaning about the number).
_FLOW_COLORS = ("#2f6feb", "#2e7d4f", "#8a5cf6", "#c7811a", "#c2463b", "#0f766e", "#b45309", "#6d28d9")


def _status(utilization: float, saturated: bool) -> str:
    """Display bucket for a component's load — mirrors report.py's Component-load column exactly."""
    if saturated:
        return "saturated"
    if utilization >= 0.85:
        return "hot"
    return "ok"


def _layer_of(kind: ComponentKind) -> tuple[str, str, int]:
    # Fail safe: an unmapped kind (should be impossible — every ComponentKind is in _LAYERS) lands in a
    # trailing "other" band rather than raising, so a new kind never breaks the map before its layer is added.
    return _KIND_LAYER.get(kind, ("other", "Other", len(_LAYERS)))


def _grounded_evidence(comp) -> list[dict]:
    """Cited input evidence attached to this component's metrics — the SAME rows report.py renders.
    GROUNDED = the component's value sits inside the cited band; RECONCILE = it falls outside and the
    modeler's value was KEPT (never overwritten — ADR-004/006). Reads evidence only; no number made."""
    out: list[dict] = []
    for metric in sorted(GROUNDABLE_METRICS):
        g = comp.groundings.get(metric)
        if not g:
            continue
        v = getattr(comp, metric)
        in_band = g.confidence_low <= v <= g.confidence_high
        out.append({
            "metric": metric,
            "your_value": v,
            "central": g.value,
            "low": g.confidence_low,
            "high": g.confidence_high,
            "unit": g.unit,
            "status": "GROUNDED" if in_band else "RECONCILE",
            "measured_on": g.measured_context,
            "sources": [{"source": c.source, "reference": c.reference} for c in g.citations],
        })
    return out


# The provenance vocabulary the view understands (matches the CSS classes + the JS provColor keys). A
# component's `provenance` is a free-form str (possibly LLM-ingested), so any out-of-vocab value is
# clamped to ASSUMPTION rather than passed through — else it silently loses its amber (honesty) styling
# and a node could read LESS uncertain than it is (docs/09 §2.4: assumption-amber is load-bearing).
_PROV_VOCAB = frozenset({"GROUNDED", "RECONCILE", "ASSUMPTION", "GAP"})


def _node_provenance(comp, evidence: list[dict]) -> str:
    """Node-level provenance label. RECONCILE if any grounded metric fell outside its cited band, else
    GROUNDED if anything is grounded, else the component's own default (clamped to the known vocabulary)."""
    if any(e["status"] == "RECONCILE" for e in evidence):
        return "RECONCILE"
    if evidence:
        return "GROUNDED"
    p = (comp.provenance or "ASSUMPTION").upper()
    return p if p in _PROV_VOCAB else "ASSUMPTION"


def _json_safe(obj):
    """Recursively replace non-finite floats (e.g. an unbounded breakpoint = system_rps·1/ρ when ρ→0)
    with None, so the embedded blob is STRICT JSON that JS `JSON.parse` accepts (it rejects Infinity).
    The renderer shows None as 'unbounded'. Paired with `allow_nan=False` below: if any non-finite
    value slips through un-sanitised, json.dumps RAISES rather than emitting invalid JSON — fail closed."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def build_arch_map(model: SystemModel, sim: SimulationResult) -> dict:
    """The deterministic engine→map serialisation. Numbers come from `sim` (engine results) and the
    model's declared inputs; provenance/evidence come from the model. Nothing here computes a metric."""
    # Nodes, sorted by (layer order, id) for a stable, layered layout.
    nodes: list[dict] = []
    for cid in sorted(model.components):
        comp = model.components[cid]
        cr = sim.components.get(cid)
        lid, llabel, lorder = _layer_of(comp.kind)
        evidence = _grounded_evidence(comp)
        nodes.append({
            "id": comp.id,
            "name": comp.name,
            "kind": comp.kind.value,
            "layer": lid,
            "layer_label": llabel,
            "layer_order": lorder,
            # Design INPUTS (from the model — not engine results).
            "capacity_rps": comp.capacity_rps,
            "per_instance_rps": comp.per_instance_rps,   # read the input directly (never re-derive by division)
            "instances": comp.instances,
            "base_latency_ms": comp.base_latency_ms,
            "monthly_cost_cents": comp.monthly_cost,
            # Engine RESULTS (read from the simulation; the engine is their sole author).
            "arrival_rps": cr.arrival_rps if cr else None,
            "utilization": cr.utilization if cr else None,
            "mean_latency_ms": cr.mean_latency_ms if cr else None,
            "saturated": bool(cr.saturated) if cr else False,
            "status": _status(cr.utilization, cr.saturated) if cr else "ok",
            "is_bottleneck": comp.id == sim.bottleneck_id,
            "is_spof": comp.is_spof,
            # Honesty: input provenance + the cited evidence behind it.
            "provenance": _node_provenance(comp, evidence),
            "evidence": evidence,
        })
    nodes.sort(key=lambda n: (n["layer_order"], n["id"]))

    layers = [{"id": lid, "label": label, "order": i} for i, (lid, label, _k) in enumerate(_LAYERS)]

    # Flows = the edges AND the playable journeys. Colour assigned in model order; latency matched by name.
    flat_by_name = {fl.name: fl for fl in sim.flow_latencies}
    flows: list[dict] = []
    for i, fl in enumerate(model.flows):
        lat = flat_by_name.get(fl.name)
        flows.append({
            "name": fl.name,
            "share": fl.share,
            "color": _FLOW_COLORS[i % len(_FLOW_COLORS)],
            "steps": [{"component_id": s.component_id, "visit_prob": s.visit_prob} for s in fl.path],
            "latency": ({"mean_ms": lat.mean_ms, "p50_ms": lat.p50_ms,
                         "p95_ms": lat.p95_ms, "p99_ms": lat.p99_ms} if lat else None),
        })

    # Headline metric envelope — a LIST to preserve the engine's deterministic order (report.py order).
    metrics = [{"key": k, "value": m.value, "unit": m.unit, "model": m.model,
                "confidence": m.confidence, "low": m.low, "high": m.high}
               for k, m in sim.metrics.items()]

    arch = {
        "meta": {
            "title": model.name,
            "engine_version": _ENGINE_VERSION,
            "accuracy_level": "L0 (Directional)",
            "offered_load_rps": sim.system_rps,
            "confidence": sim.confidence,
            "high_stakes": is_high_stakes(model.domain_flags),
            "domain_flags": sorted(model.domain_flags),
        },
        "verdict": {
            "bottleneck_id": sim.bottleneck_id,
            "bottleneck_name": sim.bottleneck_name,
            "bottleneck_utilization": sim.bottleneck_utilization,
            "breakpoint_rps_safe": sim.breakpoint_rps_safe,
            "breakpoint_rps_theoretical": sim.breakpoint_rps_theoretical,
            "spofs": list(sim.spofs),
            "monthly_cost_cents": sim.monthly_cost,
            "latency": {"mean_ms": sim.mean_latency_ms, "p50_ms": sim.p50_ms,
                        "p95_ms": sim.p95_ms, "p99_ms": sim.p99_ms},
        },
        "layers": layers,
        "nodes": nodes,
        "flows": flows,
        "metrics": metrics,
        "caveats": list(sim.caveats),           # the mandatory "where this is wrong"
        "derivation": list(sim.derivation),     # how the numbers were computed (engine trace)
        "assumptions": [{"subject": a.subject, "statement": a.statement,
                         "confidence": a.confidence, "provenance": a.provenance}
                        for a in model.assumptions],
    }
    return _json_safe(arch)


# ---------------------------------------------------------------------------------------------------
# HTML rendering. All dynamic/untrusted content lives in the JSON blob and is written into the DOM via
# `textContent` (never innerHTML) by the script below, so component names / citations / assumptions from
# (possibly LLM-ingested) input cannot inject markup. The blob itself is `<`/`>`/`&`-escaped so a stray
# "</script>" in the data can't break out of the data island. The CSS/JS are static.
# ---------------------------------------------------------------------------------------------------

_CSS = """
:root{
  --paper:#f5f4f0; --panel:#ffffff; --ink:#1b2230; --muted:#5b6472; --line:#dcdee4; --steel:#c3c8d2;
  --blue:#2f6feb; --graphite:#333a48;
  /* MEANING colours (docs/09 §2.4) — grounded-green + assumption-amber, canonical tokens, spent
     ONLY on confidence/provenance. Never used for chrome or load. */
  --green:#2fb67c; --amber:#e8a33d;
  /* LOAD status is an operational engine RESULT, not a confidence signal, so it must NOT borrow the
     meaning colours — a neutral -> red "danger" ramp, distinct in hue from amber/green. */
  --ok:#8a93a6; --hot:#c2410c; --sat:#a5342a;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:var(--paper);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
#stage{position:fixed;inset:0;cursor:grab;overflow:hidden;
  background:
    radial-gradient(1100px 700px at 15% -10%,#eceef4 0%,transparent 60%),
    linear-gradient(180deg,#f7f7f4,#efeef0)}
#stage.grabbing{cursor:grabbing}
#grid{position:absolute;inset:-3000px;pointer-events:none;
  background-image:linear-gradient(rgba(40,60,110,.05) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(40,60,110,.05) 1px,transparent 1px);
  background-size:40px 40px}
#viewport{position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform}
svg#edges{position:absolute;left:0;top:0;overflow:visible;pointer-events:none}
.glass{background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:0 8px 26px rgba(20,30,60,.10)}

/* header */
#head{position:fixed;left:16px;top:14px;z-index:20;max-width:min(560px,54vw);padding:12px 16px}
#head h1{margin:0;font-size:18px;font-weight:750;letter-spacing:.2px}
#head .sub{color:var(--muted);font-size:12px;margin-top:3px;line-height:1.45}
#head .row{display:flex;flex-wrap:wrap;gap:8px;margin-top:9px;align-items:center}
.badge{font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;letter-spacing:.02em}
.badge.l0{background:#eef3ff;color:#274690;border:1px solid #cdd9f6}
.badge.load{background:#f0f1f4;color:var(--graphite);border:1px solid var(--line)}
.badge.conf{background:#fbf5ea;color:#8a5a12;border:1px solid #efe0c4}
#hs{position:fixed;left:16px;top:96px;z-index:20;max-width:min(560px,54vw);padding:10px 14px;
  background:#fbeae7;border:1px solid #e6b7ae;border-radius:10px;color:#8a2b20;font-size:12px;line-height:1.4;display:none}
#hs.on{display:block}

/* control dock */
#dock{position:fixed;right:14px;top:14px;z-index:20;width:250px;padding:12px;display:flex;flex-direction:column;gap:12px}
#dock .lbl{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);font-weight:800;margin-bottom:5px}
.jbtn{display:block;width:100%;text-align:left;font-size:12.5px;padding:7px 9px;border-radius:8px;cursor:pointer;
  color:var(--ink);border:1px solid var(--line);background:#fff;margin-bottom:5px;line-height:1.2}
.jbtn:hover{border-color:var(--steel);background:#f6f8ff}
.jbtn.active{background:#eef3ff;border-color:#b9ccf5}
.jbtn small{display:block;color:var(--muted);font-size:10.5px;margin-top:2px}
.jbtn .sw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:baseline}
.viewbtns{display:flex;gap:6px}
.vb{flex:1;text-align:center;font-size:12px;padding:6px 0;border-radius:8px;cursor:pointer;color:var(--muted);
  border:1px solid var(--line);background:#fff}
.vb:hover{color:var(--ink);border-color:var(--steel)}
.tbtn{width:100%;text-align:left;font-size:12px;padding:7px 9px;border-radius:8px;cursor:pointer;color:var(--ink);
  border:1px solid var(--line);background:#fff}
.tbtn:hover{border-color:var(--steel);background:#f6f8ff}

/* nodes */
.node{position:absolute;width:190px;border-radius:11px;padding:9px 11px 10px;cursor:pointer;background:#fff;
  border:1px solid var(--line);box-shadow:0 3px 10px rgba(20,30,60,.08);
  transition:transform .15s ease,box-shadow .15s ease,opacity .18s ease;overflow:hidden}
.node:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--pc,var(--steel))}
.node .nm{font-size:12.5px;font-weight:700;line-height:1.15;padding-right:4px}
.node .kd{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em;margin-top:2px}
.node .util{margin-top:7px;height:5px;border-radius:3px;background:#edeef2;overflow:hidden}
.node .util > i{display:block;height:100%;border-radius:3px;background:var(--sc,var(--ok))}
.node .meta{display:flex;justify-content:space-between;align-items:center;margin-top:6px;font-size:10.5px;color:var(--muted)}
.node .meta b{color:var(--ink);font-variant-numeric:tabular-nums}
.node .tags{position:absolute;right:8px;top:8px;display:flex;gap:4px}
.node .tag{font-size:8.5px;font-weight:800;padding:1px 5px;border-radius:5px;letter-spacing:.03em}
.tag.bn{background:#fbe3df;color:#a5342a}
.tag.spof{background:#f3ecff;color:#5b34b0}
.tag.dv.matched{background:#e5f2ea;color:#1f6b40}
.tag.dv.soft{background:#fbf3e3;color:#8a5a12}
.tag.dv.hard{background:#fbe3df;color:#a5342a}
.tag.dv.not_compared{background:#eef0f3;color:#5b6472}
.badge.audit{background:#f0f4ff;color:#2a3f7a;border:1px solid #cdd9f6}
.node:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(20,30,60,.16)}
.node.dim{opacity:.22;filter:saturate(.6)}
.node.hot{box-shadow:0 0 0 1px var(--sc),0 6px 18px rgba(20,30,60,.14)}
.node.sel{box-shadow:0 0 0 2px var(--blue),0 8px 22px rgba(20,30,60,.18)}
.lhead{position:absolute;font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;font-weight:800;
  color:var(--muted);opacity:.85}
path.edge{fill:none;stroke-linecap:round;transition:stroke-opacity .18s,stroke-width .18s}

/* side panel */
#panel{position:fixed;right:14px;top:14px;bottom:14px;width:340px;z-index:30;padding:0;transform:translateX(380px);
  transition:transform .26s cubic-bezier(.2,.8,.2,1);display:flex;flex-direction:column;overflow:hidden}
#panel.open{transform:none}
#panel .ph{padding:15px 18px 12px;border-bottom:1px solid var(--line);position:relative}
#panel .ph .k{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);font-weight:800}
#panel .ph h2{margin:5px 0 2px;font-size:17px}
#panel .ph .tech{font-size:11.5px;color:var(--muted)}
#panel .pb{padding:14px 18px;overflow:auto}
#panel .cls{position:absolute;right:12px;top:12px;cursor:pointer;color:var(--muted);font-size:18px;width:26px;height:26px;
  display:grid;place-items:center;border-radius:8px}
#panel .cls:hover{background:#f0f1f4;color:var(--ink)}
.sec{font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);font-weight:800;margin:15px 0 7px}
.kv{display:flex;justify-content:space-between;gap:10px;font-size:12.5px;padding:4px 0;border-bottom:1px dashed var(--line)}
.kv .v{font-variant-numeric:tabular-nums;font-weight:600;text-align:right}
.tagline{font-size:10.5px;color:var(--muted);margin-top:3px}
.prov{display:inline-block;font-size:10px;font-weight:800;padding:2px 8px;border-radius:6px;letter-spacing:.03em}
.prov.GROUNDED{background:#e5f2ea;color:#1f6b40}
.prov.RECONCILE,.prov.ASSUMPTION,.prov.GAP{background:#fbf3e3;color:#8a5a12}
.ev{border:1px solid var(--line);border-radius:9px;padding:9px 10px;margin-top:8px;background:#fbfbfc}
.ev .m{font-size:12px;font-weight:700}
.ev .band{font-size:11px;color:var(--muted);margin-top:3px;font-variant-numeric:tabular-nums}
.ev .src{font-size:10.5px;color:var(--muted);margin-top:4px;word-break:break-word}
.ev .on{font-size:10.5px;color:#7a675a;margin-top:4px;font-style:italic}
.note{font-size:11px;color:var(--muted);line-height:1.5;margin-top:6px}

/* bottom drawers (verdict / where-wrong / metrics) */
#drawer{position:fixed;left:16px;right:16px;bottom:14px;z-index:22;max-height:44vh;padding:0;overflow:hidden;display:none}
#drawer.open{display:flex;flex-direction:column}
#drawer .dh{display:flex;align-items:center;justify-content:space-between;padding:11px 16px;border-bottom:1px solid var(--line)}
#drawer .dh h3{margin:0;font-size:13.5px}
#drawer .db{padding:12px 16px;overflow:auto}
#drawer .cls{cursor:pointer;color:var(--muted);font-size:18px}
table.k{border-collapse:collapse;width:100%;font-size:12px}
table.k th,table.k td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}
table.k td.n{text-align:right;font-variant-numeric:tabular-nums}
.wrongli{font-size:12.5px;line-height:1.5;margin:0 0 7px;padding-left:2px}
.legend{position:fixed;left:16px;bottom:14px;z-index:18;padding:10px 13px;display:flex;gap:18px;flex-wrap:wrap}
.legend .col .t{font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);font-weight:800;margin-bottom:4px}
.legend .r{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);margin-bottom:2px}
.legend .chip{width:10px;height:10px;border-radius:3px;border:1px solid rgba(0,0,0,.1)}
.legend .ln{width:20px;height:0;border-top:3px solid;border-radius:2px}
#hint{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);z-index:8;color:#9aa0ad;font-size:11px;pointer-events:none}
.credit{position:fixed;right:16px;bottom:12px;z-index:8;color:#a6abb6;font-size:10.5px}
"""


def _render_js() -> str:
    """The static renderer. Reads the #arch-data island and paints the map. No number is computed here —
    it formats engine values for display (the same %/rps/ms/$ formatting the markdown report uses)."""
    return r"""
const DATA = JSON.parse(document.getElementById('arch-data').textContent);
const $ = (s,r=document)=>r.querySelector(s);
const el=(t,c,txt)=>{const e=document.createElement(t);if(c)e.className=c;if(txt!=null)e.textContent=txt;return e;};
const pct=v=>v==null?'—':(v*100).toFixed(0)+'%';
const rps=v=>v==null?'unbounded':Math.round(v).toLocaleString();
const ms=v=>v==null?'—':Math.round(v).toLocaleString()+' ms';
const usd=c=>c==null?'—':'$'+(c/100).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const statusColor={ok:'var(--ok)',hot:'var(--hot)',saturated:'var(--sat)'};
const provColor={GROUNDED:'var(--green)',RECONCILE:'var(--amber)',ASSUMPTION:'var(--amber)',GAP:'var(--amber)'};
// Audit overlay (optional): model-vs-observed divergence maps onto the confidence semantics —
// matched=green ("reality confirms it"), soft=amber ("where this is wrong"), hard=red (failure).
const AUDIT=DATA.meta.audit||null;
const divColor={matched:'var(--green)',soft:'var(--amber)',hard:'#c2463b',not_compared:'var(--muted)',not_observed:'var(--steel)'};
const divBadge={matched:'✓ matched',soft:'⚠ soft',hard:'⛔ HARD',not_compared:'– n/c',not_observed:''};
const gapStr=g=>g==null?'':(g>=0?'+':'')+Math.round(g*100)+'%';

// ---- layout ---------------------------------------------------------------
const COLW=250,ROWH=140,PADX=70,PADY=90,NW=190,NH=94;
const nodeById={};DATA.nodes.forEach(n=>nodeById[n.id]=n);
// dense-rank the layers actually present, so empty bands leave no gap
const presentOrders=[...new Set(DATA.nodes.map(n=>n.layer_order))].sort((a,b)=>a-b);
const colIndex={};presentOrders.forEach((o,i)=>colIndex[o]=i);
const byCol={};DATA.nodes.forEach(n=>{(byCol[colIndex[n.layer_order]] ||= []).push(n);});
const maxRows=Math.max(...Object.values(byCol).map(a=>a.length),1);
const pos={};
Object.entries(byCol).forEach(([ci,arr])=>{
  arr.sort((a,b)=>a.id<b.id?-1:1);
  const off=(maxRows-arr.length)/2;
  arr.forEach((n,ri)=>{pos[n.id]={x:PADX+ci*COLW, y:PADY+(ri+off)*ROWH};});
});
const W=PADX*2+presentOrders.length*COLW, H=PADY*2+maxRows*ROWH;

const viewport=$('#viewport'), svg=$('#edges');
svg.setAttribute('width',W);svg.setAttribute('height',H);
viewport.style.width=W+'px';viewport.style.height=H+'px';

// layer headers
const seenCol={};
DATA.nodes.forEach(n=>{const ci=colIndex[n.layer_order];if(seenCol[ci])return;seenCol[ci]=1;
  const h=el('div','lhead',n.layer_label);h.style.left=(PADX+ci*COLW)+'px';h.style.top=(PADY-34)+'px';viewport.appendChild(h);});

// ---- edges (flows = journeys) --------------------------------------------
const edgeEls=[]; // {path, flow, from, to}
DATA.flows.forEach(f=>{
  for(let i=0;i<f.steps.length-1;i++){
    const a=pos[f.steps[i].component_id], b=pos[f.steps[i+1].component_id];
    if(!a||!b)continue;
    const x1=a.x+NW,y1=a.y+NH/2, x2=b.x,y2=b.y+NH/2, mx=(x1+x2)/2;
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d',`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`);
    p.setAttribute('class','edge');p.setAttribute('stroke',f.color);
    p.setAttribute('stroke-width',(1.2+f.share*3).toFixed(2));p.setAttribute('stroke-opacity','.5');
    svg.appendChild(p);
    edgeEls.push({path:p,flow:f.name,from:f.steps[i].component_id,to:f.steps[i+1].component_id});
  }
});

// ---- node cards -----------------------------------------------------------
const nodeEls={};
DATA.nodes.forEach(n=>{
  const d=el('div','node'+(n.status==='hot'||n.status==='saturated'?' hot':''));
  d.style.left=pos[n.id].x+'px';d.style.top=pos[n.id].y+'px';
  // In audit mode the left edge signals DIVERGENCE (the audit's core finding); otherwise provenance.
  d.style.setProperty('--pc', n.divergence?(divColor[n.divergence.status]||'var(--steel)'):(provColor[n.provenance]||'var(--steel)'));
  d.style.setProperty('--sc',statusColor[n.status]);
  const tags=el('div','tags');
  if(n.divergence&&n.divergence.status!=='not_observed')
    tags.appendChild(el('span','tag dv '+n.divergence.status,(divBadge[n.divergence.status]+' '+gapStr(n.divergence.gap)).trim()));
  if(n.is_bottleneck)tags.appendChild(el('span','tag bn','⚑ BN'));
  if(n.is_spof)tags.appendChild(el('span','tag spof','SPOF'));
  d.appendChild(tags);
  d.appendChild(el('div','nm',n.name));
  d.appendChild(el('div','kd',n.kind.replace(/_/g,' ')));
  const bar=el('div','util');const fill=el('i');fill.style.width=Math.min(100,(n.utilization||0)*100)+'%';bar.appendChild(fill);d.appendChild(bar);
  const meta=el('div','meta');
  const u=el('span');u.appendChild(document.createTextNode('util '));const ub=el('b',null,pct(n.utilization));u.appendChild(ub);
  const cap=el('span',null,rps(n.capacity_rps)+' rps cap');
  meta.appendChild(u);meta.appendChild(cap);d.appendChild(meta);
  d.onclick=(e)=>{e.stopPropagation();openNode(n);};
  // While a journey is focused, hover must NOT clobber it — leave the active-flow highlight intact.
  d.onmouseenter=()=>{if(!activeFlow)hoverNode(n.id);};
  d.onmouseleave=()=>{if(!activeFlow)clearHover();};
  viewport.appendChild(d);nodeEls[n.id]=d;
});

// ---- hover / flow focus ---------------------------------------------------
let activeFlow=null;
function setEdge(e,on){e.path.setAttribute('stroke-opacity',on?'.95':'.12');e.path.setAttribute('stroke-width',on?(2.4):(1));}
function hoverNode(id){
  const touch=new Set([id]);
  edgeEls.forEach(e=>{const on=(e.from===id||e.to===id);setEdge(e,on);if(on){touch.add(e.from);touch.add(e.to);}});
  DATA.nodes.forEach(n=>nodeEls[n.id].classList.toggle('dim',!touch.has(n.id)));
}
function clearHover(){edgeEls.forEach(e=>{e.path.setAttribute('stroke-opacity','.5');e.path.setAttribute('stroke-width',(1.2+ (DATA.flows.find(f=>f.name===e.flow)?.share||.3)*3).toFixed(2));});DATA.nodes.forEach(n=>nodeEls[n.id].classList.remove('dim'));}
function focusFlow(f){
  activeFlow=f.name;
  const ids=new Set(f.steps.map(s=>s.component_id));
  edgeEls.forEach(e=>setEdge(e,e.flow===f.name));
  DATA.nodes.forEach(n=>nodeEls[n.id].classList.toggle('dim',!ids.has(n.id)));
  const lat=f.latency;
  $('#jcap').classList.add('show');
  $('#jcapT').textContent='Journey · '+f.name+'  ('+(f.share*100).toFixed(0)+'% of traffic)';
  $('#jcapS').textContent=lat?`this path: mean ${ms(lat.mean_ms)} · p50 ${ms(lat.p50_ms)} · p95 ${ms(lat.p95_ms)} · p99 ${ms(lat.p99_ms)}`:'no per-flow latency';
}
function clearFlow(){activeFlow=null;$('#jcap').classList.remove('show');clearHover();document.querySelectorAll('.jbtn').forEach(b=>b.classList.remove('active'));}

// ---- detail panel ---------------------------------------------------------
const panel=$('#panel');
function kv(parent,k,v,tag){const r=el('div','kv');r.appendChild(el('span','k',k));const vv=el('span','v',v);r.appendChild(vv);parent.appendChild(r);if(tag){const t=el('div','tagline',tag);parent.appendChild(t);} }
function openNode(n){
  DATA.nodes.forEach(m=>nodeEls[m.id].classList.toggle('sel',m.id===n.id));
  $('#pKind').textContent=n.kind.replace(/_/g,' ')+(n.is_bottleneck?' · BOTTLENECK':'')+(n.is_spof?' · SPOF':'');
  $('#pName').textContent=n.name;
  $('#pTech').textContent=n.instances+'× instance'+(n.instances>1?'s':'')+' · '+rps(n.capacity_rps)+' rps capacity';
  const b=$('#pBody');b.textContent='';
  const s1=el('div','sec','Engine-computed (this run)');b.appendChild(s1);
  kv(b,'Arrival', rps(n.arrival_rps)+' rps');
  kv(b,'Utilisation', pct(n.utilization), n.status==='saturated'?'SATURATED — beyond the model’s stable range':(n.status==='hot'?'running hot (≥85%)':'within safe range'));
  kv(b,'Mean service', ms(n.mean_latency_ms));
  const s2=el('div','sec','Design inputs (your model)');b.appendChild(s2);
  kv(b,'Capacity', rps(n.capacity_rps)+' rps ('+n.instances+'× '+rps(n.per_instance_rps)+')');
  kv(b,'Base latency', ms(n.base_latency_ms));
  kv(b,'Monthly cost', usd(n.monthly_cost_cents));
  const s3=el('div','sec','Provenance');b.appendChild(s3);
  const pv=el('span','prov '+n.provenance,n.provenance);b.appendChild(pv);
  if(n.evidence.length){
    n.evidence.forEach(e=>{
      const c=el('div','ev');
      c.appendChild(el('div','m',e.metric+' — '+e.status));
      c.appendChild(el('div','band','your value '+fmtEv(e,e.your_value)+'  ·  cited central '+fmtEv(e,e.central)+'  ·  band '+fmtEv(e,e.low)+'–'+fmtEv(e,e.high)));
      if(e.measured_on)c.appendChild(el('div','on','measured on: '+e.measured_on));
      e.sources.forEach(sc=>c.appendChild(el('div','src','↳ '+sc.source+' — '+sc.reference)));
      b.appendChild(c);
    });
    b.appendChild(el('div','note','The engine used YOUR value, not the benchmark. RECONCILE = your value fell outside the cited band and was kept, not overwritten — a human should check the context (hardware / region / workload).'));
  }else{
    b.appendChild(el('div','note','No cited evidence attached to this component’s inputs — treat its capacity/latency as an ASSUMPTION (L0). Grounding adds citations; it never changes a computed number.'));
  }
  if(n.divergence&&n.divergence.rows.length){
    b.appendChild(el('div','sec','Observed vs predicted (audit)'));
    n.divergence.rows.forEach(r=>{
      const c=el('div','ev');
      c.appendChild(el('div','m',r.metric+' — '+r.verdict+(r.severity?' ('+r.severity+')':'')));
      c.appendChild(el('div','band','observed '+fmtEv(r,r.observed)+'  ·  predicted '+(r.predicted==null?'—':fmtEv(r,r.predicted))+'  ·  gap '+(r.gap_ratio==null?'n/a':gapStr(r.gap_ratio))));
      if(r.source)c.appendChild(el('div','src','↳ observed: '+r.source));
      if(r.note)c.appendChild(el('div','on',r.note));
      b.appendChild(c);
    });
    b.appendChild(el('div','note','Observed values are read-only EVIDENCE — they never changed an engine number (prime directive); divergences are surfaced for review, never auto-resolved (ADR-004).'));
  }
  panel.classList.add('open');
}
function fmtEv(e,v){if(v==null)return '—';if(e.unit==='rps')return rps(v)+' rps';if(e.unit==='ms')return ms(v);if(e.unit&&e.unit.indexOf('usd')>=0)return usd(v);return (''+v);}
function closePanel(){panel.classList.remove('open');DATA.nodes.forEach(m=>nodeEls[m.id].classList.remove('sel'));}
$('#panelClose').onclick=closePanel;
// Click-away and Escape must dismiss the panel too, so the dock + "where this is wrong" controls it
// covers are never stranded behind it after the first node click.
window.addEventListener('keydown',e=>{if(e.key==='Escape'){closePanel();clearFlow();}});

// ---- header / verdict / where-wrong / metrics -----------------------------
$('#ttl').textContent=DATA.meta.title;
$('#subttl').textContent=AUDIT?'Audit map · model vs OBSERVED reality — where your running system diverges from the design'
  :'Architecture map · every result is engine-computed; every input is declared and carries its provenance';
$('#bL0').textContent=DATA.meta.accuracy_level;
$('#bLoad').textContent=rps(DATA.meta.offered_load_rps)+' req/s offered';
// Show the engine's FULL confidence qualifier — never strip the parenthetical (it is the honesty
// payload, e.g. "directional…" / "a component is saturated; beyond the model's stable range").
$('#bConf').textContent='confidence: '+(DATA.meta.confidence||'');
$('#bConf').title=DATA.meta.confidence||'';
if(AUDIT){const ab=$('#bAudit');ab.style.display='';
  ab.textContent='audit: '+AUDIT.matched+' matched · '+AUDIT.diverged+' diverged ('+AUDIT.hard+' hard)';
  ab.title=AUDIT.overall;
  $('#legProv').style.display='none';$('#legDiv').style.display='';}
if(DATA.meta.high_stakes){$('#hs').classList.add('on');
  $('#hs').textContent='⚠ HIGH-STAKES DOMAIN — mandatory expert review. This design REQUIRES expert / legal / security review before any production use. Keystone does not certify safety or production-readiness.';}

// journeys
const jb=$('#jbtns');
DATA.flows.forEach(f=>{const btn=el('button','jbtn');const sw=el('span','sw');sw.style.background=f.color;
  const t=el('span');t.appendChild(sw);t.appendChild(document.createTextNode(f.name));btn.appendChild(t);
  btn.appendChild(el('small',null,(f.share*100).toFixed(0)+'% of traffic'+(f.latency?' · p99 '+ms(f.latency.p99_ms):'')));
  btn.onclick=()=>{const was=btn.classList.contains('active');clearFlow();if(!was){btn.classList.add('active');focusFlow(f);}};jb.appendChild(btn);});

// verdict drawer content
function buildVerdict(){const v=DATA.verdict,b=$('#dbVerdict');b.textContent='';
  if(AUDIT){b.appendChild(el('div','sec','Audit — model vs observed reality'));
    b.appendChild(el('div','wrongli','Overall: '+AUDIT.overall));
    b.appendChild(el('div','wrongli','Reconciliation: '+AUDIT.matched+' matched · '+AUDIT.diverged+' diverged ('+AUDIT.hard+' hard) · '+AUDIT.unit_mismatch+' unit-mismatch · '+AUDIT.no_prediction+' not predicted (of '+AUDIT.observed_count+' observed).'));
    // When the map reads as a pass (matches, no divergences), say plainly that a match is not a guarantee.
    if(AUDIT.reads_as_pass)
      b.appendChild(el('div','wrongli','A matched metric is consistent with the prediction within tolerance — it is NOT a validation pass or a guarantee of correctness (L0, Directional).'));
    (DATA.audit_unmatched||[]).forEach(u=>b.appendChild(el('div','wrongli','• not tied to a component — '+(u.component_id||'(system)')+' / '+u.metric+': '+u.note)));
    b.appendChild(el('div','note','Observed values are read-only evidence — no engine number was changed (prime directive); divergences are surfaced for review, never auto-resolved (ADR-004) — your model’s value is kept, not overwritten. L0: a divergence flags where to look, not a certified defect.'));}
  const rows=[['Bottleneck',v.bottleneck_name+'  ('+pct(v.bottleneck_utilization)+' utilisation)'],
    ['Max safe load','~'+rps(v.breakpoint_rps_safe)+' req/s  (85% ceiling) · ~'+rps(v.breakpoint_rps_theoretical)+' theoretical'],
    ['Latency (dominant path)','p50 '+ms(v.latency.p50_ms)+' · p95 '+ms(v.latency.p95_ms)+' · p99 '+ms(v.latency.p99_ms)],
    ['Single points of failure',v.spofs.length?v.spofs.join(', '):'none detected'],
    ['Estimated monthly cost',usd(v.monthly_cost_cents)],
    ['Overall confidence',DATA.meta.confidence]];
  const tbl=el('table','k');rows.forEach(([k,val])=>{const tr=el('tr');tr.appendChild(el('th',null,k));tr.appendChild(el('td',null,val));tbl.appendChild(tr);});b.appendChild(tbl);}
buildVerdict();

// metrics drawer
function buildMetrics(){const b=$('#dbMetrics');b.textContent='';
  const fmt=(u,x)=>x==null?'—':u==='rps'?rps(x)+' req/s':u==='ratio'?pct(x):u&&u.indexOf('usd')>=0?usd(x)+'/mo':ms(x);
  const tbl=el('table','k');const hr=el('tr');['Metric','Value','Range (cited inputs)','Model','Confidence'].forEach(h=>hr.appendChild(el('th',null,h)));tbl.appendChild(hr);
  DATA.metrics.forEach(m=>{const tr=el('tr');tr.appendChild(el('td',null,m.key));
    tr.appendChild(el('td','n',fmt(m.unit,m.value)));
    tr.appendChild(el('td','n',m.low!=null?fmt(m.unit,m.low)+' – '+fmt(m.unit,m.high):'—'));
    tr.appendChild(el('td',null,m.model));tr.appendChild(el('td',null,m.confidence||''));tbl.appendChild(tr);});
  b.appendChild(tbl);
  b.appendChild(el('div','note','Range = the output span when each GROUNDED input is swept across its cited band (assumed inputs held fixed). Input-evidence uncertainty only — NOT a validated-accuracy guarantee; the true value can fall outside it. A — means no grounded input moves that number. Accuracy stays L0 (Directional) until field-calibrated.'));
  if(DATA.derivation.length){b.appendChild(el('div','sec','How these numbers were computed'));const ul=el('div');DATA.derivation.forEach(s=>{const li=el('div','wrongli','• '+s);ul.appendChild(li);});b.appendChild(ul);} }
buildMetrics();

// where-this-is-wrong drawer
function buildWrong(){const b=$('#dbWrong');b.textContent='';
  if(!DATA.caveats.length){b.appendChild(el('div','note','No caveats recorded for this run.'));}
  DATA.caveats.forEach(c=>b.appendChild(el('div','wrongli','• '+c)));
  if(DATA.assumptions.length){b.appendChild(el('div','sec','Assumptions (each editable)'));
    const tbl=el('table','k');const hr=el('tr');['Subject','Statement','Confidence','Provenance'].forEach(h=>hr.appendChild(el('th',null,h)));tbl.appendChild(hr);
    DATA.assumptions.forEach(a=>{const tr=el('tr');tr.appendChild(el('td',null,a.subject));tr.appendChild(el('td',null,a.statement));tr.appendChild(el('td',null,a.confidence));tr.appendChild(el('td',null,a.provenance));tbl.appendChild(tr);});b.appendChild(tbl);} }
buildWrong();

const drawer=$('#drawer');let curDrawer=null;
function toggleDrawer(which,title){if(curDrawer===which){drawer.classList.remove('open');curDrawer=null;return;}
  curDrawer=which;$('#drawerTitle').textContent=title;
  ['Verdict','Metrics','Wrong'].forEach(w=>$('#db'+w).style.display=(w===which?'block':'none'));
  drawer.classList.add('open');}
$('#tVerdict').onclick=()=>toggleDrawer('Verdict','Verdict');
$('#tMetrics').onclick=()=>toggleDrawer('Metrics','Headline metrics (model · confidence)');
$('#tWrong').onclick=()=>toggleDrawer('Wrong','Where this is wrong — read before trusting a number');
$('#drawerClose').onclick=()=>{drawer.classList.remove('open');curDrawer=null;};
toggleDrawer('Verdict','Verdict'); // open on load so the verdict + honesty controls are visible immediately

// ---- pan / zoom -----------------------------------------------------------
let sc=1,tx=40,ty=20,drag=null;const stage=$('#stage');
function apply(){viewport.style.transform=`translate(${tx}px,${ty}px) scale(${sc})`;}
function fit(){const r=stage.getBoundingClientRect();sc=Math.min(1,Math.min((r.width-360)/W,(r.height-220)/H));sc=Math.max(.35,sc);tx=40;ty=90;apply();}
stage.addEventListener('mousedown',e=>{if(e.target.closest('.node,#panel,#dock,#drawer,#head,.jbtn'))return;drag={x:e.clientX-tx,y:e.clientY-ty};stage.classList.add('grabbing');});
window.addEventListener('mousemove',e=>{if(!drag)return;tx=e.clientX-drag.x;ty=e.clientY-drag.y;apply();});
window.addEventListener('mouseup',()=>{drag=null;stage.classList.remove('grabbing');});
stage.addEventListener('wheel',e=>{e.preventDefault();const f=e.deltaY<0?1.1:1/1.1;const r=stage.getBoundingClientRect();const mx=e.clientX-r.left,my=e.clientY-r.top;tx=mx-(mx-tx)*f;ty=my-(my-ty)*f;sc=Math.max(.3,Math.min(2.2,sc*f));apply();},{passive:false});
$('#vFit').onclick=fit;$('#vIn').onclick=()=>{sc=Math.min(2.2,sc*1.15);apply();};$('#vOut').onclick=()=>{sc=Math.max(.3,sc/1.15);apply();};$('#vReset').onclick=()=>{sc=1;tx=40;ty=20;apply();};
stage.addEventListener('click',e=>{if(!e.target.closest('.node,#panel,#dock,#drawer')){clearFlow();closePanel();}});
fit();
"""


def render_html(arch: dict, *, title: str | None = None) -> str:
    """A self-contained interactive HTML page for an arch map. Deterministic (no time / random)."""
    page_title = title or arch["meta"]["title"]
    # Strict JSON (allow_nan=False → raises if a non-finite slipped past _json_safe), then neutralise any
    # "</script>" / entity in string values so the data island cannot break out (XSS defence-in-depth).
    blob = json.dumps(arch, sort_keys=True, ensure_ascii=True, allow_nan=False)
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    esc_title = (page_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Keystone — {esc_title} — Architecture Map</title>
<style>{_CSS}</style>
</head>
<body>
<div id="stage"><div id="grid"></div><div id="viewport"><svg id="edges"></svg></div></div>

<div id="head" class="glass">
  <h1 id="ttl"></h1>
  <div class="sub" id="subttl"></div>
  <div class="row">
    <span class="badge l0" id="bL0"></span>
    <span class="badge load" id="bLoad"></span>
    <span class="badge conf" id="bConf"></span>
    <span class="badge audit" id="bAudit" style="display:none"></span>
  </div>
</div>
<div id="hs"></div>

<div id="dock" class="glass">
  <div>
    <div class="lbl">Explore the design</div>
    <button class="tbtn" id="tVerdict" style="margin-bottom:5px">▸ Verdict</button>
    <button class="tbtn" id="tMetrics" style="margin-bottom:5px">▸ Headline metrics</button>
    <button class="tbtn" id="tWrong">▸ Where this is wrong</button>
  </div>
  <div>
    <div class="lbl">Play a journey (a request flow)</div>
    <div id="jbtns"></div>
  </div>
  <div>
    <div class="lbl">View</div>
    <div class="viewbtns">
      <div class="vb" id="vFit">Fit</div><div class="vb" id="vIn">＋</div>
      <div class="vb" id="vOut">－</div><div class="vb" id="vReset">Reset</div>
    </div>
  </div>
</div>

<div id="panel" class="glass">
  <div class="cls" id="panelClose">×</div>
  <div class="ph"><div class="k" id="pKind"></div><h2 id="pName"></h2><div class="tech" id="pTech"></div></div>
  <div class="pb" id="pBody"></div>
</div>

<div id="drawer" class="glass">
  <div class="dh"><h3 id="drawerTitle"></h3><span class="cls" id="drawerClose">×</span></div>
  <div class="db">
    <div id="dbVerdict"></div><div id="dbMetrics" style="display:none"></div><div id="dbWrong" style="display:none"></div>
  </div>
</div>

<div id="jcap" class="glass" style="position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:24;padding:9px 15px;display:none">
  <style>#jcap.show{{display:block!important}}</style>
  <div class="jt" id="jcapT" style="font-size:12px;font-weight:800;color:var(--blue)"></div>
  <div id="jcapS" style="font-size:12.5px;color:var(--muted);margin-top:2px"></div>
</div>

<div class="legend glass">
  <div class="col" id="legProv"><div class="t">Provenance (confidence)</div>
    <div class="r"><span class="chip" style="background:#2fb67c"></span>Grounded (cited)</div>
    <div class="r"><span class="chip" style="background:#e8a33d"></span>Assumption / reconcile / gap</div></div>
  <div class="col" id="legDiv" style="display:none"><div class="t">Audit · model vs observed</div>
    <div class="r"><span class="chip" style="background:#2fb67c"></span>matched (within tolerance)</div>
    <div class="r"><span class="chip" style="background:#e8a33d"></span>soft divergence</div>
    <div class="r"><span class="chip" style="background:#c2463b"></span>hard divergence</div>
    <div class="r"><span class="chip" style="background:#5b6472"></span>not compared (unit / not predicted)</div>
    <div class="r"><span class="chip" style="background:#c3c8d2"></span>not observed (no telemetry)</div></div>
  <div class="col"><div class="t">Load (engine result)</div>
    <div class="r"><span class="chip" style="background:#8a93a6"></span>ok</div>
    <div class="r"><span class="chip" style="background:#c2410c"></span>hot (≥85%)</div>
    <div class="r"><span class="chip" style="background:#a5342a"></span>saturated</div></div>
</div>

<div id="hint">drag to pan · scroll to zoom · hover a node to trace its flows · click for detail + provenance</div>
<div class="credit">Keystone · deterministic engine · self-contained</div>

<script id="arch-data" type="application/json">{blob}</script>
<script>{_render_js()}</script>
</body>
</html>
"""
