// Types for the chaos-scenario contract (prototype/keystone/scenarios.py, POST /scenario).
//
// Prime directive: a scenario is a *model* perturbation. The engine runs twice — once on the design
// as drawn, once on the perturbed model — and every number below is one of those two engine runs, or
// plain arithmetic over them. This file computes nothing.

import type { ArchMap } from "./archMap";

export type ScenarioCategory = "traffic" | "capacity" | "data" | "dependency";

/** One runnable (scenario, target) pair. The API only ever offers pairs the engine will accept,
 *  so a card here can never be a dead button. */
export interface ScenarioOption {
  key: string; // "cache_cold:cache" — stable identity for React keys and selection
  id: string;
  name: string;
  category: ScenarioCategory;
  question: string;
  caveat: string;
  targets: string[];
  target_id: string | null;
  target_name: string | null;
  /** Selectable severities; empty means the scenario is binary. First entry is the default. */
  magnitudes: number[];
  magnitude_unit: string;
  default_magnitude: number;
}

/** One scenario, aimed and dialled. Several compose into a compound failure. */
export interface ScenarioSpec {
  scenario_id: string;
  target_id: string | null;
  magnitude?: number | null;
}

export interface ScenarioDelta {
  verdict: string;
  survives: boolean;
  bottleneck_moved: boolean;
  /** null when the perturbed design is OVERLOADED: past 100% the queue grows without limit, so
   *  there is no finite multiple. The API has sent null since the unbounded-latency change; this
   *  type said `number`, so TypeScript could not catch the `.toFixed()` calls that crashed the
   *  panel on any scenario severe enough to saturate — which "run all 5" always is. */
  latency_multiple: number | null;
  utilization_delta: number;
  baseline_latency_ms: number;
  perturbed_latency_ms: number | null;
  baseline_bottleneck: string;
  perturbed_bottleneck: string;
  baseline_confidence: string;
  perturbed_confidence: string;
  derivation: string[];
}

export interface AppliedScenario {
  scenario_id: string;
  name: string;
  category: ScenarioCategory;
  caveat: string;
  target_id: string | null;
  target_name: string | null;
  magnitude: number | null;
  magnitude_unit: string;
}

export interface ScenarioRun {
  scenario: {
    id: string;
    name: string;
    category: ScenarioCategory;
    question: string;
    caveat: string;
    target_id: string | null;
    target_name: string | null;
    applied: AppliedScenario[];
  };
  baseline: ArchMap;
  perturbed: ArchMap;
  delta: ScenarioDelta;
}

/** What the engine deliberately refuses to model, keyed by name with the reason. Rendered as-is so
 *  the panel shows the gap instead of leaving it silently absent. */
export type Unmodelled = Record<string, string>;

export const CATEGORY_LABEL: Record<ScenarioCategory, string> = {
  traffic: "Traffic",
  capacity: "Capacity",
  data: "Database and cache",
  dependency: "Services your app waits on",
};

export const CATEGORY_ORDER: ScenarioCategory[] = ["traffic", "capacity", "data", "dependency"];

/** How the design reaches POST /scenario. These are not interchangeable: a generated design must
 *  travel as its `intent`, because a canvas topology cannot carry flow branch probabilities (a
 *  cache-miss path, say) and rebuilding from one would silently change the model being perturbed. */
export type ScenarioSubject =
  | { mode: "intent"; intent: string }
  | {
      mode: "topology";
      name: string;
      system_rps: number;
      nodes: { id: string; kind: string; name?: string; per_instance_rps?: number; instances?: number }[];
      edges: [string, string][];
    };

/** POST /scenario — returns both engine runs plus the delta. Throws with the API's own message so
 *  a refused scenario (wrong kind, no miss path, last instance) surfaces its reason to the user. */
/** Run one scenario, or several at once. A compound is composed into ONE model and simulated once —
 *  it is not the sum of the individual verdicts, because each perturbation changes the arrivals the
 *  next one lands on. */
export async function runScenario(
  api: string,
  subject: ScenarioSubject,
  specs: ScenarioSpec[],
  signal?: AbortSignal,
): Promise<ScenarioRun> {
  const body =
    subject.mode === "intent"
      ? { intent: subject.intent }
      : {
          name: subject.name,
          system_rps: subject.system_rps,
          nodes: subject.nodes,
          edges: subject.edges,
        };
  const res = await fetch(`${api}/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      specs.length === 1
        ? { ...body, scenario_id: specs[0].scenario_id, target_id: specs[0].target_id,
            magnitude: specs[0].magnitude ?? null }
        : { ...body, specs },
    ),
    signal,
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Couldn't run this test — the server returned an error (code ${res.status}).`);
  }
  return (await res.json()) as ScenarioRun;
}
