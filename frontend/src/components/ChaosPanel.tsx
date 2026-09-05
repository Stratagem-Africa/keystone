"use client";

import { useMemo, useState } from "react";
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  type ScenarioCategory,
  type ScenarioOption,
  type ScenarioRun,
  type Unmodelled,
} from "@/lib/scenarios";

// The chaos panel. Each card runs a COUNTERFACTUAL: the engine simulates the design as drawn, then
// simulates it perturbed, and both runs come back with their own confidence and caveats.
//
// Two deliberate differences from the tools this resembles:
//  1. Nothing is poked at runtime — a scenario is a model perturbation, so the same card always
//     produces the same answer.
//  2. The panel only lists what the engine can express on THIS design. Scenarios that would be a
//     no-op here are withheld by the API, and the ones we refuse to model at all are shown, with
//     the reason, rather than quietly omitted.

interface ChaosPanelProps {
  scenarios: ScenarioOption[];
  unmodelled: Unmodelled;
  active: ScenarioRun | null;
  runningKey: string | null;
  error: string | null;
  onRun: (option: ScenarioOption) => void;
  onClear: () => void;
}

function DeltaRow({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-[11.5px]">
      <span style={{ color: "var(--cv-muted)" }}>{label}</span>
      <span className="tabular-nums font-semibold" style={{ color: tone ?? "var(--cv-ink)" }}>{value}</span>
    </div>
  );
}

export function ChaosPanel({
  scenarios, unmodelled, active, runningKey, error, onRun, onClear,
}: ChaosPanelProps) {
  const [showLimits, setShowLimits] = useState(false);
  const [showWorking, setShowWorking] = useState(false);

  const grouped = useMemo(() => {
    const by = new Map<ScenarioCategory, ScenarioOption[]>();
    for (const s of scenarios) {
      const list = by.get(s.category) ?? [];
      list.push(s);
      by.set(s.category, list);
    }
    return CATEGORY_ORDER.filter((c) => by.has(c)).map((c) => ({ category: c, items: by.get(c)! }));
  }, [scenarios]);

  const activeKey = active
    ? active.scenario.target_id
      ? `${active.scenario.id}:${active.scenario.target_id}`
      : active.scenario.id
    : null;

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
          Break it on purpose
        </h2>
        {active && (
          <button
            onClick={onClear}
            className="rounded px-2 py-0.5 text-[10.5px] font-semibold transition-colors hover:bg-white/10"
            style={{ color: "var(--cv-blue)" }}
          >
            ← back to the design
          </button>
        )}
      </div>

      {/* ── the result of the active scenario ── */}
      {active && (
        <div
          className="cv-panel p-3"
          style={{ borderLeft: `3px solid ${active.delta.survives ? "var(--cv-green)" : "var(--cv-red)"}` }}
        >
          <div className="flex items-baseline gap-2">
            <span
              className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
              style={{
                background: active.delta.survives ? "rgba(74,222,128,.15)" : "rgba(248,113,113,.15)",
                color: active.delta.survives ? "var(--cv-green)" : "var(--cv-red)",
              }}
            >
              {active.delta.survives ? "holds" : "breaks"}
            </span>
            <span className="text-[12.5px] font-semibold" style={{ color: "var(--cv-ink)" }}>
              {active.scenario.name}
              {active.scenario.target_name && (
                <span style={{ color: "var(--cv-muted)" }}> · {active.scenario.target_name}</span>
              )}
            </span>
          </div>

          <p className="mt-2 text-[12px] leading-snug" style={{ color: "var(--cv-ink)" }}>
            {active.delta.verdict}
          </p>

          <div className="mt-3 flex flex-col gap-1">
            <DeltaRow
              label="Mean latency"
              value={`${active.delta.baseline_latency_ms.toFixed(0)} → ${active.delta.perturbed_latency_ms.toFixed(0)} ms`}
              tone={active.delta.latency_multiple > 1.5 ? "var(--cv-red)" : undefined}
            />
            <DeltaRow label="Change" value={`${active.delta.latency_multiple.toFixed(1)}×`} />
            <DeltaRow
              label="Constraint"
              value={
                active.delta.bottleneck_moved
                  ? `moves → ${active.delta.perturbed_bottleneck}`
                  : `stays on ${active.delta.perturbed_bottleneck}`
              }
              tone={active.delta.bottleneck_moved ? "var(--cv-amber)" : undefined}
            />
          </div>

          <p className="mt-3 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
            <b>Confidence:</b> {active.delta.perturbed_confidence}
          </p>
          <p className="mt-1.5 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
            <b>This does not model:</b> {active.scenario.caveat}
          </p>

          <button
            onClick={() => setShowWorking((v) => !v)}
            className="mt-2 text-[10.5px] font-semibold"
            style={{ color: "var(--cv-blue)" }}
          >
            {showWorking ? "▾" : "▸"} how these numbers were reached
          </button>
          {showWorking && (
            <pre
              className="mt-1.5 overflow-x-auto rounded p-2 text-[10px] leading-relaxed"
              style={{ background: "rgba(0,0,0,.28)", color: "var(--cv-muted)" }}
            >
              {active.delta.derivation.join("\n")}
            </pre>
          )}
        </div>
      )}

      {error && (
        <p className="cv-panel p-2.5 text-[11.5px] leading-snug" style={{ color: "var(--cv-amber)" }}>
          {error}
        </p>
      )}

      {/* ── the runnable catalogue ── */}
      {grouped.map(({ category, items }) => (
        <div key={category} className="flex flex-col gap-1.5">
          <h3 className="text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
            {CATEGORY_LABEL[category]}
          </h3>
          {items.map((s) => {
            const isActive = activeKey === s.key;
            const isRunning = runningKey === s.key;
            return (
              <button
                key={s.key}
                onClick={() => onRun(s)}
                disabled={runningKey !== null}
                title={s.question}
                className="cv-panel group w-full p-2.5 text-left transition-colors disabled:opacity-50 hover:bg-white/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
                style={{
                  outlineColor: "var(--cv-blue)",
                  borderLeft: isActive ? "3px solid var(--cv-blue)" : "3px solid transparent",
                }}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[12px] font-semibold" style={{ color: "var(--cv-ink)" }}>
                    {s.name}
                  </span>
                  {isRunning && (
                    <span className="text-[10px]" style={{ color: "var(--cv-blue)" }}>running…</span>
                  )}
                </div>
                {s.target_name && (
                  <span className="mt-0.5 block text-[10.5px]" style={{ color: "var(--cv-muted)" }}>
                    {s.target_name}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}

      {/* ── what we deliberately do not model ── */}
      <div className="mt-1">
        <button
          onClick={() => setShowLimits((v) => !v)}
          className="text-[10.5px] font-semibold"
          style={{ color: "var(--cv-muted)" }}
        >
          {showLimits ? "▾" : "▸"} what this engine will not fake ({Object.keys(unmodelled).length})
        </button>
        {showLimits && (
          <ul className="mt-2 flex flex-col gap-2">
            {Object.entries(unmodelled).map(([key, why]) => (
              <li key={key} className="text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                <b style={{ color: "var(--cv-ink)" }}>{key.replace(/_/g, " ")}</b> — {why}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
