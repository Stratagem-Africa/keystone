// Types for the capacity remediation contract (prototype/keystone/remediation.py, POST /remediate).
//
// The planner chooses instance counts (inputs) and the engine decides whether they worked; `before`
// and `after` are two real simulate() runs. Nothing here computes a metric.

import type { ArchMap } from "./archMap";
import type { ScenarioSubject } from "./scenarios";

export interface Remedy {
  component_id: string;
  component_name: string;
  kind: string;
  lever: string;
  from_instances: number;
  to_instances: number;
  added: number;
  reason: string;
}

/** A saturated component the planner refuses to size, because adding instances would be a category
 *  error — a single-writer primary, a third-party dependency, or demand itself. Carries the
 *  architectural options instead of a fabricated number. */
export interface Blocker {
  component_id: string;
  component_name: string;
  kind: string;
  utilization: number;
  guidance: string;
}

export interface RunSummary {
  bottleneck_name: string;
  bottleneck_utilization: number | null;
  mean_latency_ms: number;
  monthly_cost_cents: number;
  confidence: string;
}

export interface RemediationPlan {
  target_rps: number;
  ceiling: number;
  holds: boolean;
  verdict: string;
  remedies: Remedy[];
  blockers: Blocker[];
  monthly_cost_delta_cents: number;
  before: RunSummary;
  after: RunSummary;
  after_map: ArchMap;
  limits: string[];
  derivation: string[];
}

export async function planCapacity(
  api: string,
  subject: ScenarioSubject,
  targetRps: number,
  signal?: AbortSignal,
): Promise<RemediationPlan> {
  const body =
    subject.mode === "intent"
      ? { intent: subject.intent }
      : {
          name: subject.name,
          system_rps: subject.system_rps,
          nodes: subject.nodes,
          edges: subject.edges,
        };
  const res = await fetch(`${api}/remediate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, target_rps: targetRps }),
    signal,
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Couldn't work out a plan for this traffic level — the server returned error code ${res.status}. Nothing on your canvas has changed.`);
  }
  return (await res.json()) as RemediationPlan;
}
