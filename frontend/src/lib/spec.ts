// The Keystone spec file (prototype/keystone/export.py, POST /export + /import).
//
// A design you can save, commit, diff and re-open. The file carries INPUTS only — no verdict — so
// re-opening it and running the engine reproduces the run rather than replaying a stale answer.

import type { ArchMap } from "./archMap";
import type { ScenarioSubject } from "./scenarios";

export interface SpecExport {
  spec: Record<string, unknown>;
  filename: string;
  /** Components on no flow: they receive nothing, report 0% utilisation, and still cost money. */
  orphans: string[];
}

function subjectBody(subject: ScenarioSubject) {
  return subject.mode === "intent"
    ? { intent: subject.intent }
    : {
        name: subject.name,
        system_rps: subject.system_rps,
        nodes: subject.nodes,
        edges: subject.edges,
      };
}

export async function exportSpec(api: string, subject: ScenarioSubject): Promise<SpecExport> {
  const res = await fetch(`${api}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subjectBody(subject)),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `export failed (${res.status})`);
  }
  return (await res.json()) as SpecExport;
}

export async function importSpec(api: string, spec: unknown): Promise<ArchMap> {
  const res = await fetch(`${api}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ spec }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `import failed (${res.status})`);
  }
  return (await res.json()) as ArchMap;
}

/** Hand the spec to the browser as a download. Kept out of the component so the studio does not
 *  grow DOM plumbing it has no other reason to know about. */
export function downloadSpec({ spec, filename }: SpecExport): void {
  const blob = new Blob([JSON.stringify(spec, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
