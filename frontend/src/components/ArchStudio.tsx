"use client";

import { useEffect, useRef, useState } from "react";
import { CanvasEditor, type CanvasSeed } from "@/components/CanvasEditor";
import { seedFromArchMap, type ArchMap } from "@/lib/archMap";

// The one architecture surface. Type an intent → the engine designs + simulates a DEEP architecture
// (POST /generate) → it opens on the editable canvas, already showing the engine's verdict, where you
// refine any node and re-simulate. One flow: describe → living, editable design. No separate map /
// canvas / report pages — this is all of them.
//
// Prime directive: every number comes from the engine (/generate, then /simulate on edits). This
// component computes none. The endpoint is public + pinned to the offline $0 path (never a live LLM),
// so no sign-in is needed and it can't drive metered spend.

type GenerateResponse = ArchMap & {
  matched?: string | null; // which reference architecture (null = no offline match → generic fallback)
  catalogue?: string[];
};

type State = "idle" | "generating" | "done" | "error";

// Example intents — mirror the offline reference catalogue so they work today at $0 with no key.
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
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [genId, setGenId] = useState(0); // bumps each generation → remounts the canvas with the new seed
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
        body: JSON.stringify({ intent: brief }),
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
        ? `Ready. ${result.nodes.length} components on the canvas — edit any node and re-simulate.`
        : "";

  // Seed the editable canvas from the generated design (positioned nodes + edges + the engine verdict),
  // so it opens on the architecture, not a blank grid.
  const seed: CanvasSeed | null = result
    ? { ...seedFromArchMap(result), systemRps: Math.round(result.meta.offered_load_rps), archMap: result }
    : null;

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

      {/* Result — the editable canvas, full-screen, seeded with the generated design + its verdict. */}
      {state === "done" && result && seed && (
        <div className="canvas-glass fixed inset-0 z-50 flex flex-col">
          <div className="flex items-center justify-between gap-4 px-4 py-2 border-b border-[var(--cv-line)]">
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="font-sans font-semibold text-[var(--cv-ink)] shrink-0">keystone</span>
              <span className="font-mono text-[11px] text-[var(--cv-muted)] truncate">
                {intent}
                {result.matched == null && (
                  <span className="text-[var(--cv-amber)]"> · generic starting point — edit it to fit</span>
                )}
              </span>
            </div>
            <button
              onClick={reset}
              className="shrink-0 font-sans text-label font-medium px-4 py-1.5 rounded-full bg-[var(--cv-ink)] text-[var(--cv-paper)] transition-transform duration-ui active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]"
            >
              ✕ New design
            </button>
          </div>
          <div className="flex-1 min-h-0">
            <CanvasEditor key={genId} seed={seed} />
          </div>
        </div>
      )}
    </div>
  );
}
