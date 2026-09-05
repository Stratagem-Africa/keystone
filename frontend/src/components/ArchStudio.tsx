"use client";

import { useEffect, useRef, useState } from "react";
import { CanvasEditor, type CanvasSeed } from "@/components/CanvasEditor";
import { seedFromArchMap, type ArchMap } from "@/lib/archMap";

// The one architecture surface. Describe an intent → the engine designs + simulates a DEEP architecture
// (POST /generate) → it opens on the beautiful, animated map (the self-contained renderer, journeys +
// flow particles + drill-down). One clear "Edit" toggle swaps to the editable canvas (same design,
// seeded) where you refine + re-simulate; the map re-renders to reflect the edit. One door:
// describe → see → (edit) → verdict.
//
// Prime directive: every number comes from the engine (/generate, then /simulate on edits). This
// component computes none. Public + offline-pinned (never a live LLM), so no sign-in is needed.

type GenerateResponse = ArchMap & {
  matched?: string | null; // which reference architecture (null = no offline match → generic fallback)
  catalogue?: string[];
};

type State = "idle" | "generating" | "done" | "error";
type Mode = "map" | "edit";

const EXAMPLES = [
  "A platform like Twitter",
  "An online store checkout with payments",
  "A flash-sale ticket booking site",
  "A URL shortener, mostly reads",
];

const API = process.env.NEXT_PUBLIC_API_URL;

export function ArchStudio() {
  const [intent, setIntent] = useState("");
  const [state, setState] = useState<State>("idle");
  const [mode, setMode] = useState<Mode>("map");
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [genId, setGenId] = useState(0); // bumps each generation → remounts the canvas with a fresh seed
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function generate(text: string) {
    const brief = text.trim();
    if (!brief) return;
    if (!API) {
      setErrorMsg(
        "The API URL was not configured at build time — NEXT_PUBLIC_API_URL is baked into the bundle at " +
          "`next build`, not read at runtime. Set it (e.g. http://localhost:8000) and rebuild.",
      );
      setState("error");
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState("generating");
    setErrorMsg(null);
    try {
      const res = await fetch(`${API}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: brief, render: true }), // render:true → the animated map HTML
        signal: controller.signal,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `the generator returned ${res.status}`);
      }
      const data: GenerateResponse = await res.json();
      if (controller.signal.aborted) return;
      setResult(data);
      setGenId((n) => n + 1);
      setMode("map");
      setState("done");
    } catch (err) {
      if (controller.signal.aborted) return;
      setErrorMsg(err instanceof Error ? err.message : "something went wrong");
      setState("error");
    }
  }

  function reset() {
    abortRef.current?.abort();
    setState("idle");
    setResult(null);
    setIntent("");
    setErrorMsg(null);
    textareaRef.current?.focus();
  }

  const busy = state === "generating";
  const liveMessage =
    state === "generating"
      ? "Designing a layered architecture and simulating it on the engine…"
      : state === "done" && result
        ? `Ready. ${result.nodes.length} components, ${result.flows.length} request journeys.`
        : "";

  // Seed the editable canvas from the current design (positioned nodes + edges + engine verdict).
  const seed: CanvasSeed | null = result
    ? { ...seedFromArchMap(result), systemRps: Math.round(result.meta.offered_load_rps), archMap: result }
    : null;

  const tabBtn = (active: boolean) =>
    `font-sans text-label px-3 py-1 rounded-full transition-colors duration-ui ${
      active ? "bg-[var(--cv-blue)] text-[var(--cv-paper)]" : "text-[var(--cv-muted)] hover:text-[var(--cv-ink)]"
    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]`;

  return (
    <div className="flex flex-col gap-8">
      <p role="status" aria-live="polite" className="sr-only">{liveMessage}</p>

      {/* Describe */}
      <form
        onSubmit={(e) => { e.preventDefault(); void generate(intent); }}
        className="flex flex-col gap-4"
        aria-busy={busy}
      >
        <label htmlFor="intent" className="font-sans text-label uppercase tracking-widest text-ink-muted">
          Describe what you want to build
        </label>
        <textarea
          id="intent"
          ref={textareaRef}
          rows={3}
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          placeholder="e.g. a platform like Twitter"
          className="w-full rounded-lg border border-steel bg-graphite text-paper font-serif text-body px-4 py-3 placeholder:text-ink-muted/60 resize-none transition-all ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-provenance text-ink-muted mr-1">Try:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => { setIntent(ex); void generate(ex); }}
              disabled={busy}
              className="font-sans text-provenance text-ink-muted border border-steel rounded-full px-3 py-1 transition-colors ease-settle duration-ui hover:text-paper hover:border-architect-blue disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
            >
              {ex}
            </button>
          ))}
        </div>
        <button
          type="submit"
          disabled={!intent.trim() || busy}
          className="self-start font-sans text-label font-medium px-6 py-3 rounded-full bg-paper text-slate-ink transition-all ease-settle duration-ui hover:bg-mist active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-ink"
        >
          {busy ? "Designing…" : "Generate architecture →"}
        </button>
      </form>

      {state === "generating" && (
        <p className="font-mono text-provenance text-ink-muted animate-pulse">
          designing a layered architecture · simulating on the deterministic engine…
        </p>
      )}

      {state === "error" && (
        <div role="alert" className="border border-assumption-amber rounded-lg p-6 flex flex-col gap-2">
          <p className="font-mono text-provenance uppercase tracking-widest text-assumption-amber">could not generate</p>
          <p className="font-serif text-body text-paper max-w-[60ch]">{errorMsg}</p>
        </div>
      )}

      {/* Result — full-screen. Default = the beautiful animated map; one "Edit" toggle to refine. */}
      {state === "done" && result && seed && (
        <div className="canvas-glass fixed inset-0 z-50 flex flex-col">
          <div className="flex items-center justify-between gap-4 px-4 py-2 border-b border-[var(--cv-line)]">
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="font-sans font-semibold text-[var(--cv-ink)] shrink-0">keystone</span>
              <span className="font-mono text-[11px] text-[var(--cv-muted)] truncate">
                {intent}
                {result.matched == null && (
                  <span className="text-[var(--cv-amber)]"> · generic starting point — Edit to fit</span>
                )}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <div className="flex items-center gap-1 rounded-full border border-[var(--cv-line)] p-0.5">
                <button className={tabBtn(mode === "map")} onClick={() => setMode("map")}>Map</button>
                <button className={tabBtn(mode === "edit")} onClick={() => setMode("edit")}>✎ Edit</button>
              </div>
              <button
                onClick={reset}
                className="font-sans text-label font-medium px-4 py-1.5 rounded-full bg-[var(--cv-ink)] text-[var(--cv-paper)] transition-transform duration-ui active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]"
              >
                ✕ New design
              </button>
            </div>
          </div>

          <div className="flex-1 min-h-0">
            {/* Map (default): the exact self-contained animated renderer, isolated in a sandboxed iframe. */}
            <iframe
              title={`Architecture map for: ${intent}`}
              srcDoc={result.html ?? ""}
              sandbox="allow-scripts"
              className={`w-full h-full border-0 bg-[var(--cv-paper)] ${mode === "map" ? "block" : "hidden"}`}
            />
            {/* Edit: the editable canvas, seeded from the design. On re-simulate it updates the map too. */}
            {mode === "edit" && (
              <CanvasEditor
                key={genId}
                seed={seed}
                onSimulated={(arch) =>
                  setResult((prev) => (prev ? { ...arch, matched: prev.matched, catalogue: prev.catalogue } : prev))
                }
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
