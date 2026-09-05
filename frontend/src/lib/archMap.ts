// Types for the /simulate contract (prototype/api/main.py, prototype/keystone/arch_map.py).
// The engine is the only producer of these numbers — this file never computes anything,
// it only shapes what the API already returned.

export const COMPONENT_KINDS = [
  "client",
  "cdn",
  "load_balancer",
  "api_gateway",
  "app_server",
  "cache",
  "sql_db",
  "replica",
  "queue",
  "object_store",
  "external_api",
] as const;

export type ComponentKind = (typeof COMPONENT_KINDS)[number];

// Mirrors _KIND_ICON / _KIND_ROLE in prototype/keystone/arch_map.py — presentation labels
// only (icon + plain-English role), kept in sync by hand since the frontend can't import
// the Python source of truth.
export const KIND_META: Record<ComponentKind, { icon: string; role: string; label: string }> = {
  client: { icon: "👤", role: "Your users and their browsers", label: "Client" },
  cdn: { icon: "🌐", role: "Serves static content from the edge, close to users", label: "CDN" },
  load_balancer: { icon: "⚖️", role: "Spreads incoming traffic across your servers", label: "Load balancer" },
  api_gateway: { icon: "🚪", role: "The front door — routes and guards every request", label: "API gateway" },
  app_server: { icon: "⚙️", role: "The workhorse that runs your app's logic", label: "App server" },
  cache: { icon: "⚡", role: "Keeps hot data in memory for fast reads", label: "Cache" },
  sql_db: { icon: "🗄️", role: "The system of record — your durable data", label: "SQL database" },
  replica: { icon: "📑", role: "A read-only copy of the database, sharing the read load", label: "Read replica" },
  queue: { icon: "📨", role: "Holds background work to process later", label: "Queue" },
  object_store: { icon: "🪣", role: "Stores files and large uploads (images, blobs)", label: "Object store" },
  external_api: { icon: "🔌", role: "A third-party service your system depends on", label: "External API" },
};

export interface TopologyNode {
  id: string;
  kind: ComponentKind;
  name?: string;
  per_instance_rps?: number;
  instances?: number;
  base_latency_ms?: number;
  monthly_cost_cents?: number;
}

export interface SimulateRequest {
  name?: string;
  system_rps?: number;
  nodes: TopologyNode[];
  edges: [string, string][];
  render?: boolean; // also return the self-contained interactive HTML map (so an edit re-renders it)
}

export type Provenance = "GROUNDED" | "RECONCILE" | "ASSUMPTION" | "GAP";
export type NodeStatus = "ok" | "hot" | "saturated";

export interface ArchMapEvidence {
  metric: string;
  your_value: number;
  central: number;
  low: number;
  high: number;
  unit: string;
  status: "GROUNDED" | "RECONCILE";
  measured_on: string | null;
  sources: { source: string; reference: string }[];
}

export interface ArchMapNode {
  id: string;
  name: string;
  kind: string;
  icon: string;
  role: string;
  layer: string;
  layer_label: string;
  layer_order: number;
  capacity_rps: number;
  per_instance_rps: number;
  instances: number;
  base_latency_ms: number;
  monthly_cost_cents: number;
  arrival_rps: number | null;
  utilization: number | null;
  mean_latency_ms: number | null;
  saturated: boolean;
  status: NodeStatus;
  is_bottleneck: boolean;
  is_spof: boolean;
  provenance: Provenance;
  evidence: ArchMapEvidence[];
}

export interface ArchMapFlowStep {
  component_id: string;
  visit_prob: number;
}

export interface LatencyStats {
  mean_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

export interface ArchMapFlow {
  name: string;
  share: number;
  color: string;
  steps: ArchMapFlowStep[];
  latency: LatencyStats | null;
}

export interface ArchMapMetric {
  key: string;
  value: number;
  unit: "rps" | "ms" | "usd_minor_per_month" | "ratio";
  model: string;
  confidence: string;
  low: number | null;
  high: number | null;
}

export interface ArchMapAssumption {
  subject: string;
  statement: string;
  confidence: string;
  provenance: string;
}

export interface ArchMapLayer {
  id: string;
  label: string;
  order: number;
}

export interface ArchMapVerdict {
  bottleneck_id: string | null;
  bottleneck_name: string;
  bottleneck_utilization: number | null;
  breakpoint_rps_safe: number | null;
  breakpoint_rps_theoretical: number | null;
  spofs: string[];
  monthly_cost_cents: number;
  latency: LatencyStats;
}

export interface ArchMapMeta {
  title: string;
  engine_version: string;
  accuracy_level: string;
  offered_load_rps: number;
  confidence: string;
  high_stakes: boolean;
  domain_flags: string[];
}

export interface ArchMap {
  meta: ArchMapMeta;
  verdict: ArchMapVerdict;
  layers: ArchMapLayer[];
  nodes: ArchMapNode[];
  flows: ArchMapFlow[];
  metrics: ArchMapMetric[];
  caveats: string[];
  derivation: string[];
  assumptions: ArchMapAssumption[];
  html?: string; // present when the endpoint was asked to render (the self-contained interactive map)
}

export interface ApiErrorBody {
  detail?: string;
}

// ─── Seeding the editable canvas from a generated design ──────────────────────
// The studio flow is: describe → /generate returns an ArchMap → seed the editable canvas with it so
// the user lands on the *generated* architecture (never a blank/starter grid), then edits + re-simulates.
export interface SeedNode {
  id: string;
  kind: ComponentKind;
  name: string;
  per_instance_rps?: number;
  instances?: number;
  x: number;
  y: number;
}

/** Derive an editable topology (positioned nodes + edges) from an engine-produced ArchMap.
 *  Layout mirrors the arch-map's layered bands: each layer is a horizontal row (y = layer_order),
 *  nodes spread left-to-right within it. Edges come from the flow steps (consecutive component pairs,
 *  deduped) — the same graph the engine simulated. Every number stays the engine's; this only
 *  reconstructs the editable *shape*. */
export function seedFromArchMap(arch: ArchMap): { nodes: SeedNode[]; edges: [string, string][] } {
  const kinds = COMPONENT_KINDS as readonly string[];
  const rowInLayer: Record<number, number> = {};
  const nodes: SeedNode[] = arch.nodes.map((n) => {
    const col = rowInLayer[n.layer_order] ?? 0;
    rowInLayer[n.layer_order] = col + 1;
    return {
      id: n.id,
      kind: (kinds.includes(n.kind) ? n.kind : "app_server") as ComponentKind,
      name: n.name,
      per_instance_rps: n.per_instance_rps,
      instances: n.instances,
      x: col * 220,
      y: n.layer_order * 150,
    };
  });
  const seen = new Set<string>();
  const edges: [string, string][] = [];
  for (const f of arch.flows) {
    for (let i = 0; i + 1 < f.steps.length; i++) {
      const a = f.steps[i].component_id;
      const b = f.steps[i + 1].component_id;
      const key = `${a}->${b}`;
      if (a !== b && !seen.has(key)) {
        seen.add(key);
        edges.push([a, b]);
      }
    }
  }
  return { nodes, edges };
}
