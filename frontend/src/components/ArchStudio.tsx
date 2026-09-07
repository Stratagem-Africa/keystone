"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { CanvasEditor, type CanvasSeed } from "@/components/CanvasEditor";
import { ArchCanvas, type SweepFrame } from "@/components/ArchCanvas";
import { ChaosPanel } from "@/components/ChaosPanel";
import { DesignPanel } from "@/components/DesignPanel";
import { FixPanel } from "@/components/FixPanel";
import { LoadTransport } from "@/components/LoadTransport";
import { seedFromArchMap, type ArchMap, type ArchMapNode } from "@/lib/archMap";
import {
  runScenario, type ScenarioOption, type ScenarioRun, type ScenarioSpec, type ScenarioSubject,
  type Unmodelled,
} from "@/lib/scenarios";
import { planCapacity, type RemediationPlan } from "@/lib/remediation";
import { downloadSpec, exportSpec, importSpec } from "@/lib/spec";

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
  sweep?: SweepFrame[];         // one real simulate() run per load stop
  scenarios?: ScenarioOption[]; // the chaos scenarios THIS design can truthfully run
  unmodelled?: Unmodelled;      // and the ones the engine refuses to fake, with reasons
};

type State = "idle" | "generating" | "done" | "error";
type Mode = "map" | "edit";

const EXAMPLES = [
  "A platform like Twitter",
  "An online store checkout with payments",
  "A flash-sale ticket booking site",
  "A link shortener — far more clicks than new links",
];

const API = process.env.NEXT_PUBLIC_API_URL;

export function ArchStudio() {
  const [intent, setIntent] = useState("");
  const [state, setState] = useState<State>("idle");
  const [mode, setMode] = useState<Mode>("map");
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [genId, setGenId] = useState(0); // bumps each generation → remounts the canvas with a fresh seed
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  // -1 = "not chosen yet"; resolved to the design-load stop once the sweep arrives.
  const [loadIndex, setLoadIndex] = useState(-1);
  const [chaos, setChaos] = useState<ScenarioRun | null>(null);
  const [chaosRunning, setChaosRunning] = useState<string | null>(null);
  const [chaosError, setChaosError] = useState<string | null>(null);
  const chaosAbort = useRef<AbortController | null>(null);
  // A generated design must be perturbed via its intent (the topology cannot carry flow branch
  // probabilities). Once the user edits on the canvas, the topology IS the design, so we switch.
  const [edited, setEdited] = useState(false);
  const [rail, setRail] = useState<"verdict" | "chaos" | "fix">("verdict");
  const [fixPlan, setFixPlan] = useState<RemediationPlan | null>(null);
  const [fixRunning, setFixRunning] = useState(false);
  const [fixError, setFixError] = useState<string | null>(null);
  const [fixApplied, setFixApplied] = useState(false);
  const fixAbort = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [specBusy, setSpecBusy] = useState(false);
  const [activeFlowIndex, setActiveFlowIndex] = useState<number | null>(null);
  const [selectedNode, setSelectedNode] = useState<ArchMapNode | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function generate(text: string) {
    const brief = text.trim();
    if (!brief) return;
    if (!API) {
      setErrorMsg(
        "Keystone doesn't know where its API is. The address is baked in when the app is built, not read while it runs — " +
          "so set NEXT_PUBLIC_API_URL (for example http://localhost:8000) and build again.",
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
        // sweep:true → the load axis (one real simulate() per stop). render:false → no HTML string;
        // the map is a React component now, so the self-contained document is no longer needed.
        body: JSON.stringify({ intent: brief, render: false, sweep: true }),
        signal: controller.signal,
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `Keystone's design service could not build this design (error ${res.status})`);
      }
      const data: GenerateResponse = await res.json();
      if (controller.signal.aborted) return;
      setResult(data);
      setLoadIndex(-1);
      setEdited(false);
      setActiveFlowIndex(null);
      setSelectedNode(null);
      setFixPlan(null);
      setFixApplied(false);
      setFixError(null);
      setChaos(null);
      setChaosError(null);
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
    chaosAbort.current?.abort();
    setState("idle");
    setResult(null);
    setChaos(null);
    setChaosError(null);
    setLoadIndex(-1);
    setEdited(false);
    setActiveFlowIndex(null);
    setSelectedNode(null);
    setFixPlan(null);
    setFixApplied(false);
    setFixError(null);
    setIntent("");
    setErrorMsg(null);
    textareaRef.current?.focus();
  }

  const busy = state === "generating";
  const liveMessage =
    state === "generating"
      ? "Designing your system and running it through the simulator…"
      : state === "done" && result
        ? `Ready. ${result.nodes.length} parts, and ${result.flows.length} paths a request can take through them.`
        : "";

  // Seed the editable canvas from the current design (positioned nodes + edges + engine verdict).
  const seed: CanvasSeed | null = result
    ? { ...seedFromArchMap(result), systemRps: Math.round(result.meta.offered_load_rps), archMap: result }
    : null;

  // A chaos scenario is a counterfactual: the engine simulates the design, then the perturbed
  // model, and we swap the canvas to the perturbed run. Nothing is animated between the two —
  // they are two separate engine answers.
  async function launchScenario(specs: ScenarioSpec[]) {
    if (!API || !seed || !result || specs.length === 0) return;
    chaosAbort.current?.abort();
    const controller = new AbortController();
    chaosAbort.current = controller;
    setChaosRunning("running");
    setChaosError(null);
    try {
      const run = await runScenario(API, subject!, specs, controller.signal);
      if (controller.signal.aborted) return;
      setChaos(run);
      setLoadIndex(-1);  // a scenario answers at the design load; the load axis restarts from there
      setSelectedNode(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setChaosError(err instanceof Error ? err.message : "the scenario could not be run");
    } finally {
      if (!controller.signal.aborted) setChaosRunning(null);
    }
  }

  // The design as POST /scenario and /remediate need it: intent while it is still the generated
  // design (topologies cannot carry flow branch probabilities), the drawn topology once edited.
  const subject: ScenarioSubject | null = !result || !seed
    ? null
    : edited
      ? {
          mode: "topology",
          name: result.meta.title,
          system_rps: Math.round(result.meta.offered_load_rps),
          nodes: seed.nodes.map((n) => ({
            id: n.id, kind: n.kind, name: n.name,
            per_instance_rps: n.per_instance_rps, instances: n.instances,
          })),
          edges: seed.edges,
        }
      : { mode: "intent", intent };

  async function planFix(targetRps: number) {
    if (!API || !subject) return;
    fixAbort.current?.abort();
    const controller = new AbortController();
    fixAbort.current = controller;
    setFixRunning(true);
    setFixError(null);
    try {
      const p = await planCapacity(API, subject, targetRps, controller.signal);
      if (controller.signal.aborted) return;
      setFixPlan(p);
      setFixApplied(false);
    } catch (err) {
      if (controller.signal.aborted) return;
      setFixError(err instanceof Error ? err.message : "could not work out what to add to carry that much traffic");
    } finally {
      if (!controller.signal.aborted) setFixRunning(false);
    }
  }

  // What the canvas shows: the perturbed run while a scenario is active, otherwise the design.
  const shown: ArchMap | null =
    fixApplied && fixPlan ? fixPlan.after_map : chaos ? chaos.perturbed : result;
  const frames: SweepFrame[] = useMemo(
    () => (chaos || fixApplied ? [] : ((result?.sweep as SweepFrame[] | undefined) ?? [])),
    [chaos, fixApplied, result],
  );
  // The sweep brackets the design load (0.25x … 10x), so stop 0 is NOT the design. Open on the
  // stop the user actually asked for, and make that where "back to design load" returns.
  const baseIndex = useMemo(() => {
    const i = frames.findIndex((f) => f.multiple === 1);
    return i >= 0 ? i : 0;
  }, [frames]);
  const effectiveIndex = loadIndex < 0 ? baseIndex : Math.min(loadIndex, frames.length - 1);
  const frame = frames.length > 0 ? frames[effectiveIndex] : null;

  // Save the design as the spec file docs/05 §4 specifies — inputs only, so re-opening it and
  // running the engine reproduces the run instead of replaying a stale verdict.
  async function saveSpec() {
    if (!API || !subject) return;
    setSpecBusy(true);
    try {
      downloadSpec(await exportSpec(API, subject));
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "could not save this design");
    } finally {
      setSpecBusy(false);
    }
  }

  async function openSpec(file: File) {
    if (!API) return;
    setSpecBusy(true);
    try {
      const arch = await importSpec(API, JSON.parse(await file.text()));
      setResult({ ...arch, matched: arch.meta.title, catalogue: result?.catalogue });
      setEdited(true);            // an opened spec IS the design; perturb it as a topology
      setChaos(null); setChaosError(null); setFixPlan(null); setFixApplied(false);
      setLoadIndex(-1); setActiveFlowIndex(null); setSelectedNode(null);
      setIntent(arch.meta.title);
      setGenId((n) => n + 1);
      setState("done");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "that file is not a Keystone design");
      setState("error");
    } finally {
      setSpecBusy(false);
    }
  }

  const railBtn = (active: boolean) =>
    `flex-1 rounded-md px-2 py-1.5 font-sans text-[11.5px] font-semibold transition-colors ${
      active ? "bg-[var(--cv-blue)] text-[var(--cv-paper)]" : "text-[var(--cv-muted)] hover:text-[var(--cv-ink)]"
    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]`;

  const tabBtn = (active: boolean) =>
    `font-sans text-label px-3 py-1 rounded-full transition-colors duration-ui ${
      active ? "bg-[var(--cv-blue)] text-[var(--cv-paper)]" : "text-[var(--cv-muted)] hover:text-[var(--cv-ink)]"
    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]`;

  return (
    <div className="flex flex-col gap-8">
      <p role="status" aria-live="polite" className="sr-only">{liveMessage}</p>

      {/* Mounted at the top level, not inside the result view: opening a saved design is something
          you do BEFORE you have one on screen. */}
      <input
        ref={fileRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = "";      // re-selecting the same file must still fire onChange
          if (f) void openSpec(f);
        }}
      />

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

        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy || specBusy}
          className="self-start font-sans text-label text-ink-muted underline underline-offset-4 transition-colors hover:text-paper disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
        >
          …or open a saved design (.keystone.json)
        </button>
      </form>

      {state === "generating" && (
        <p className="font-mono text-provenance text-ink-muted animate-pulse">
          designing your system · running it through the simulator — same description in, same numbers out, every time…
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
        <div
          className="canvas-glass fixed inset-0 z-50 flex flex-col"
          // painted inline as well as via the class: a bare custom class in globals.css can be
          // dropped by Turbopack in dev, which would leave this overlay transparent over the page
          style={{ background: "var(--cv-paper)", color: "var(--cv-ink)" }}
        >
          <div className="flex items-center justify-between gap-4 px-4 py-2 border-b border-[var(--cv-line)]">
            <div className="flex items-baseline gap-2 min-w-0">
              <span className="font-sans font-semibold text-[var(--cv-ink)] shrink-0">keystone</span>
              <span className="font-mono text-[11px] text-[var(--cv-muted)] truncate">
                {intent}
                {result.matched == null && (
                  <span className="text-[var(--cv-amber)]"> · no match found — this is a generic shape, not your design</span>
                )}
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => void saveSpec()}
                  disabled={specBusy}
                  title="Save this design to a file you can keep, share, compare with later versions and open again"
                  className="font-sans text-label px-2.5 py-1 rounded-full text-[var(--cv-muted)] transition-colors hover:text-[var(--cv-ink)] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]"
                >
                  ⭳ Save
                </button>
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={specBusy}
                  title="Open a design you saved earlier"
                  className="font-sans text-label px-2.5 py-1 rounded-full text-[var(--cv-muted)] transition-colors hover:text-[var(--cv-ink)] disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cv-blue)]"
                >
                  ⭱ Open
                </button>
              </div>
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

          <div className="flex min-h-0 flex-1">
            {/* Map (default): the architecture map as a real component — engine output in, canvas out.
                It can be re-pointed at a sweep frame or a chaos scenario's perturbed run without a
                round-trip through a rendered HTML string. */}
            {mode === "map" && shown && (
              <>
                <div className="flex min-w-0 flex-1 flex-col">
                  <div className="min-h-0 flex-1">
                    <ArchCanvas
                      arch={shown}
                      frame={frame}
                      targetId={chaos?.scenario.target_id ?? null}
                      activeFlowIndex={activeFlowIndex}
                      selectedId={selectedNode?.id ?? null}
                      onSelectNode={(n) => { setSelectedNode(n); setRail("verdict"); }}
                    />
                  </div>
                  {frames.length > 0 && (
                    <LoadTransport
                      frames={frames}
                      index={effectiveIndex}
                      baseIndex={baseIndex}
                      onIndex={setLoadIndex}
                    />
                  )}
                  {chaos && (
                    <p
                      className="px-4 py-2 font-mono text-[10.5px]"
                      style={{ borderTop: "1px solid var(--cv-line)", color: "var(--cv-muted)" }}
                    >
                      you are looking at a what-if: <b style={{ color: "var(--cv-ink)" }}>{chaos.scenario.name}</b> —
                      the traffic slider comes back when you go back to the design
                    </p>
                  )}
                </div>
                <aside
                  className="flex w-[320px] shrink-0 flex-col overflow-hidden"
                  style={{ borderLeft: "1px solid var(--cv-line)", background: "var(--cv-paper)" }}
                  aria-label="Verdict, Break it and Fix it panels for this design"
                >
                  <div className="flex shrink-0 gap-1 p-2" style={{ borderBottom: "1px solid var(--cv-line)" }}>
                    <button onClick={() => setRail("verdict")} className={railBtn(rail === "verdict")}>
                      Verdict
                    </button>
                    <button onClick={() => setRail("chaos")} className={railBtn(rail === "chaos")}>
                      Break it
                    </button>
                    <button onClick={() => setRail("fix")} className={railBtn(rail === "fix")}>
                      Fix it
                    </button>
                  </div>
                  <div className="min-h-0 flex-1">
                    {rail === "fix" ? (
                      <FixPanel
                        targetRps={frame?.load_rps ?? shown.meta.offered_load_rps}
                        plan={fixPlan}
                        running={fixRunning}
                        error={fixError}
                        applied={fixApplied}
                        onPlan={() => void planFix(frame?.load_rps ?? shown.meta.offered_load_rps)}
                        onApply={() => { setFixApplied(true); setChaos(null); }}
                        onRevert={() => setFixApplied(false)}
                      />
                    ) : rail === "verdict" ? (
                      <DesignPanel
                        arch={shown}
                        unmatched={result.matched === null && !chaos && !fixApplied}
                        selected={selectedNode}
                        activeFlowIndex={activeFlowIndex}
                        onFlow={setActiveFlowIndex}
                        onClearSelection={() => setSelectedNode(null)}
                      />
                    ) : (
                      <ChaosPanel
                        scenarios={result.scenarios ?? []}
                        unmodelled={result.unmodelled ?? {}}
                        active={chaos}
                        running={chaosRunning !== null}
                        error={chaosError}
                        onRun={(specs) => void launchScenario(specs)}
                        onClear={() => { setChaos(null); setChaosError(null); }}
                      />
                    )}
                  </div>
                </aside>
              </>
            )}
            {/* Edit: the editable canvas, seeded from the design. On re-simulate it updates the map too. */}
            {mode === "edit" && (
              <CanvasEditor
                key={genId}
                seed={seed}
                onSimulated={(arch) => {
                  // The edit is now the design: its own scenario catalogue rides along on /simulate,
                  // and further scenarios must run against the topology, not the original intent.
                  setEdited(true);
                  setChaos(null);
                  setResult((prev) => (prev ? { ...arch, matched: prev.matched, catalogue: prev.catalogue } : prev));
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
