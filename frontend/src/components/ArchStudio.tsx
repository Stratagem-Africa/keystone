"use client";

import { useEffect, useRef, useState } from "react";

// The generation studio: type an intent → the engine designs + simulates a DEEP architecture, and we
// embed the SAME self-contained interactive map the backend renders (POST /generate {render:true}) in a
// sandboxed iframe — no re-implementation of the renderer, zero fidelity loss. The endpoint is stateless,
// public, and pinned to the offline $0 reference path (it never reaches a live LLM), so this surface
// works without sign-in and can't drive metered spend.
//
// Prime directive: every number on this page is the engine's. We only display verdict.* (with pure
// display formatting — cents→dollars, ratio→percent) — we never compute a metric here. Inputs stay
// ASSUMPTION until grounded; the map carries its own "where this is wrong".

type Verdict = {
  bottleneck_name: string | null;
  bottleneck_utilization: number | null;
  breakpoint_rps_safe: number | null;
  monthly_cost_cents: number | null;
  spofs: string[];
};

type GenerateResponse = {
  html: string;
  verdict: Verdict;
  nodes: unknown[];
  flows: unknown[];
  meta?: { title?: string };
  matched?: string | null;   // which reference architecture (null = no offline match → generic fallback)
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

function fmtInt(n: number | null | undefined): string {
  return typeof n === "number" && isFinite(n) ? Math.round(n).toLocaleString() : "—";
}
function fmtPct(n: number | null | undefined): string {
  return typeof n === "number" && isFinite(n) ? `${Math.round(n * 100)}%` : "—";
}
function fmtUsd(cents: number | null | undefined): string {
  // Pure display transform of the engine's integer cents — not a computed metric. Show cents only when
  // present so it can never contradict the map's own cost figure for the same number.
  return typeof cents === "number" && isFinite(cents)
    ? `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
    : "—";
}

export function ArchStudio() {
  const [intent, setIntent] = useState("");
  const [state, setState] = useState<State>("idle");
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Stop an in-flight request (and its setState) if the user navigates away mid-generation.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function generate(text: string) {
    const brief = text.trim();
    if (!brief) return;
    if (!API) {
      setErrorMsg(
        "The API URL was not configured at build time — NEXT_PUBLIC_API_URL is baked into the bundle at " +
          "`next build`, not read at runtime. Set it (e.g. http://localhost:8000) and rebuild."
      );
      setState("error");
      return;
    }
    abortRef.current?.abort();                 // supersede any prior in-flight request
    const controller = new AbortController();
    abortRef.current = controller;
    setState("generating");
    setErrorMsg(null);
    try {
      const res = await fetch(`${API}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intent: brief, render: true }),
        signal: controller.signal,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `the generator returned ${res.status}`);
      }
      const data: GenerateResponse = await res.json();
      if (controller.signal.aborted) return;   // superseded / unmounted — drop the stale response
      setResult(data);
      setState("done");
    } catch (err) {
      if (controller.signal.aborted) return;   // aborted on purpose — not a user-facing error
      setErrorMsg(err instanceof Error ? err.message : "something went wrong");
      setState("error");
    }
  }

  function onExample(ex: string) {
    setIntent(ex);
    void generate(ex);
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

  // A polite, always-mounted live region so screen readers hear each async transition (mount/unmount of
  // the region itself can swallow the announcement, so it lives here permanently and only its text swaps).
  const liveMessage =
    state === "generating" ? "Designing a layered architecture and simulating it on the engine…"
    : state === "done" && result ? `Done. ${result.nodes.length} components. Bottleneck: ${result.verdict.bottleneck_name ?? "none"}.`
    : "";

  return (
    <div className="flex flex-col gap-8">
      <p role="status" aria-live="polite" className="sr-only">{liveMessage}</p>

      {/* Intent input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void generate(intent);
        }}
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
              onClick={() => onExample(ex)}
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

      {/* Generating */}
      {state === "generating" && (
        <p className="font-mono text-provenance text-ink-muted animate-pulse">
          designing a layered architecture · simulating on the deterministic engine…
        </p>
      )}

      {/* Error — role=alert so failures are spoken assertively */}
      {state === "error" && (
        <div role="alert" className="border border-assumption-amber rounded-lg p-6 flex flex-col gap-2">
          <p className="font-mono text-provenance uppercase tracking-widest text-assumption-amber">
            could not generate
          </p>
          <p className="font-serif text-body text-paper max-w-[60ch]">{errorMsg}</p>
        </div>
      )}

      {/* Result */}
      {state === "done" && result && (
        <div className="flex flex-col gap-4">
          {/* Honest no-match notice: nothing matched offline, so this is a generic starting point. */}
          {result.matched == null && (
            <div className="border-l-4 border-assumption-amber pl-4 py-1 flex flex-col gap-1">
              <p className="font-serif text-body text-paper max-w-[62ch]">
                No exact match for that intent yet — here&apos;s a generic starting point you can refine.
              </p>
              {result.catalogue && result.catalogue.length > 0 && (
                <p className="font-mono text-provenance text-ink-muted">
                  Keystone designs these in depth today: {result.catalogue.join(" · ")}
                </p>
              )}
            </div>
          )}
          {result.matched != null && (
            <p className="font-mono text-provenance text-ink-muted">
              Matched reference architecture: <span className="text-paper">{result.matched}</span>
            </p>
          )}

          {/* Verdict strip — every number here is engine-computed (verdict.*), never derived in the UI. */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Bottleneck" value={result.verdict.bottleneck_name ?? "—"}
                  sub={`${fmtPct(result.verdict.bottleneck_utilization)} utilised`} accent />
            <Stat label="Safe capacity" value={`${fmtInt(result.verdict.breakpoint_rps_safe)} req/s`}
                  sub="safe ceiling (85% util)" />
            <Stat label="Est. cost" value={`${fmtUsd(result.verdict.monthly_cost_cents)}/mo`}
                  sub="modelled, not billed" />
            <Stat label="Single points of failure" value={String(result.verdict.spofs?.length ?? 0)}
                  sub={result.verdict.spofs?.slice(0, 2).join(", ") || "none found"} />
          </div>

          <p className="font-mono text-provenance text-ink-muted">
            {result.nodes.length} components · {result.flows.length} request journeys · engine-computed ·{" "}
            <span className="text-assumption-amber">L0 · Directional</span> — inputs are assumptions until grounded
          </p>

          {/* The interactive map — the EXACT self-contained renderer, isolated in a sandboxed iframe
              (allow-scripts only: the renderer needs no same-origin, no storage, no network). */}
          <iframe
            title="Interactive architecture map"
            srcDoc={result.html}
            sandbox="allow-scripts"
            className="w-full h-[80vh] min-h-[560px] rounded-xl border border-steel bg-slate-ink"
          />

          <div className="flex items-center gap-4">
            <button
              onClick={reset}
              className="font-sans text-label text-ink-muted underline underline-offset-2 rounded-sm hover:text-paper transition-colors ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
            >
              Try another intent
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className={`rounded-lg border p-4 flex flex-col gap-1 ${accent ? "border-signal-red/50" : "border-steel"}`}>
      <span className="font-sans text-provenance uppercase tracking-widest text-ink-muted">{label}</span>
      <span className="font-mono text-mono-data text-paper leading-tight">{value}</span>
      {sub && <span className="font-mono text-provenance text-ink-muted">{sub}</span>}
    </div>
  );
}
