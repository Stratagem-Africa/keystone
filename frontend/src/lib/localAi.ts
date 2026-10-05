// The local AI path (#204): routes under /local/* that drive the operator's OWN Claude, and only
// answer the person at this machine (prototype/api/local_guard.py). The browser cannot tell on its
// own whether it is talking to such a server, so it asks GET /local/status before offering the path.

export interface LocalStatus {
  available: boolean;   // false → the AI path is not offered; `reason` says why
  reason: string;
  ingest_provider: string;   // who designs the structure (e.g. claude_cli); "stub" = offline library
  council_provider: string;  // who writes the design decisions (e.g. claude_panel)
}

/** Ask the API whether this browser may use the local AI routes. Never throws: any failure (old
 *  server without the route, network error) simply means "not available". */
export async function fetchLocalStatus(api: string, signal?: AbortSignal): Promise<LocalStatus | null> {
  try {
    const res = await fetch(`${api}/local/status`, { signal });
    if (!res.ok) return null;
    return (await res.json()) as LocalStatus;
  } catch {
    return null;
  }
}
