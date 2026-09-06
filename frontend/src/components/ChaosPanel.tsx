"use client";

import { useMemo, useState } from "react";
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  type ScenarioCategory,
  type ScenarioOption,
  type ScenarioRun,
  type ScenarioSpec,
  type Unmodelled,
} from "@/lib/scenarios";

// The chaos panel. Each card runs a COUNTERFACTUAL: the engine simulates the design, then simulates
// it perturbed, and both runs come back with their own confidence and caveats.
//
// Two things a poke-the-running-sim tool cannot do, and this can:
//  - dial the severity, because a scenario is a parameter on a model, not a nudge to a live system;
//  - select several and run them TOGETHER, composed into one model and simulated once. A compound
//    failure is not the sum of its parts' verdicts — each perturbation changes the arrivals and
//    utilisations the next one lands on — so composing then simulating is the only honest way.
//
// The panel lists only what the engine can express on THIS design; what it refuses to model at all
// is rendered with the reason rather than quietly omitted.

interface ChaosPanelProps {
  scenarios: ScenarioOption[];
  unmodelled: Unmodelled;
  active: ScenarioRun | null;
  running: boolean;
  error: string | null;
  onRun: (specs: ScenarioSpec[]) => void;
  onClear: () => void;
}

function fmtMagnitude(value: number, unit: string): string {
  const n = Number.isInteger(value) ? String(value) : String(value);
  return unit.startsWith(" ") ? `${n}${unit}` : `${n}${unit}`;
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
  scenarios, unmodelled, active, running, error, onRun, onClear,
}: ChaosPanelProps) {
  const [showLimits, setShowLimits] = useState(false);
  const [showWorking, setShowWorking] = useState(false);
  // key -> chosen magnitude. Presence in the map == selected.
  const [selected, setSelected] = useState<Record<string, number | null>>({});

  const grouped = useMemo(() => {
    const by = new Map<ScenarioCategory, ScenarioOption[]>();
    for (const s of scenarios) {
      const list = by.get(s.category) ?? [];
      list.push(s);
      by.set(s.category, list);
    }
    return CATEGORY_ORDER.filter((c) => by.has(c)).map((c) => ({ category: c, items: by.get(c)! }));
  }, [scenarios]);

  const byKey = useMemo(() => new Map(scenarios.map((s) => [s.key, s])), [scenarios]);
  const selectedKeys = Object.keys(selected);

  const toggle = (s: ScenarioOption) =>
    setSelected((prev) => {
      const next = { ...prev };
      if (s.key in next) delete next[s.key];
      else next[s.key] = s.magnitudes.length > 0 ? s.default_magnitude : null;
      return next;
    });

  const setMagnitude = (key: string, m: number) =>
    setSelected((prev) => ({ ...prev, [key]: m }));

  const run = () => {
    const specs: ScenarioSpec[] = selectedKeys
      .map((k) => byKey.get(k))
      .filter((s): s is ScenarioOption => Boolean(s))
      .map((s) => ({ scenario_id: s.id, target_id: s.target_id, magnitude: selected[s.key] }));
    if (specs.length) onRun(specs);
  };

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
          Break it on purpose
        </h2>
        {active && (
          <button onClick={onClear} className="rounded px-2 py-0.5 text-[10.5px] font-semibold" style={{ color: "var(--cv-blue)" }}>
            ← back to the design
          </button>
        )}
      </div>

      {/* ── result ── */}
      {active && (
        <div
          className="cv-panel p-3"
          style={{ borderLeft: `3px solid ${active.delta.survives ? "var(--cv-green)" : "var(--cv-red)"}` }}
        >
          <div className="flex items-baseline gap-2">
            <span
              className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
              style={{
                background: active.delta.survives ? "rgba(74,222,128,.15)" : "rgba(248,113,113,.15)",
                color: active.delta.survives ? "var(--cv-green)" : "var(--cv-red)",
              }}
            >
              {active.delta.survives ? "holds" : "breaks"}
            </span>
            <span className="text-[12.5px] font-semibold" style={{ color: "var(--cv-ink)" }}>
              {active.scenario.name}
            </span>
          </div>

          {active.scenario.applied.length > 1 && (
            <ul className="mt-1.5 flex flex-col gap-0.5">
              {active.scenario.applied.map((a, i) => (
                <li key={i} className="text-[10.5px]" style={{ color: "var(--cv-muted)" }}>
                  · {a.name}
                  {a.target_name && ` — ${a.target_name}`}
                  {a.magnitude !== null && ` @ ${fmtMagnitude(a.magnitude, a.magnitude_unit)}`}
                </li>
              ))}
            </ul>
          )}

          <p className="mt-2 text-[12px] leading-snug" style={{ color: "var(--cv-ink)" }}>{active.delta.verdict}</p>

          <div className="mt-3 flex flex-col gap-1">
            <DeltaRow
              label="Mean latency"
              value={`${active.delta.baseline_latency_ms.toFixed(0)} → ${active.delta.perturbed_latency_ms.toFixed(0)} ms`}
              tone={active.delta.latency_multiple > 1.5 ? "var(--cv-red)" : undefined}
            />
            <DeltaRow label="Change" value={`${active.delta.latency_multiple.toFixed(1)}×`} />
            <DeltaRow
              label="Constraint"
              value={active.delta.bottleneck_moved
                ? `moves → ${active.delta.perturbed_bottleneck}`
                : `stays on ${active.delta.perturbed_bottleneck}`}
              tone={active.delta.bottleneck_moved ? "var(--cv-amber)" : undefined}
            />
          </div>

          <p className="mt-3 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
            <b>Confidence:</b> {active.delta.perturbed_confidence}
          </p>
          <p className="mt-1.5 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
            <b>This does not model:</b> {active.scenario.caveat}
          </p>

          <button onClick={() => setShowWorking((v) => !v)} className="mt-2 text-[10.5px] font-semibold" style={{ color: "var(--cv-blue)" }}>
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
        <p className="cv-panel p-2.5 text-[11.5px] leading-snug" style={{ color: "var(--cv-amber)" }}>{error}</p>
      )}

      {/* ── run bar ── */}
      <div className="flex items-center gap-2">
        <button
          onClick={run}
          disabled={selectedKeys.length === 0 || running}
          className="flex-1 rounded-full px-3 py-2 text-[11.5px] font-semibold transition-transform active:scale-[0.98] disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
          style={{ background: "var(--cv-blue)", color: "var(--cv-paper)", outlineColor: "var(--cv-blue)" }}
        >
          {running
            ? "Running…"
            : selectedKeys.length === 0
              ? "Pick what fails"
              : selectedKeys.length === 1
                ? "Run this failure"
                : `Run ${selectedKeys.length} together`}
        </button>
        {selectedKeys.length > 0 && (
          <button onClick={() => setSelected({})} className="shrink-0 text-[10.5px] font-semibold" style={{ color: "var(--cv-muted)" }}>
            clear
          </button>
        )}
      </div>
      {selectedKeys.length > 1 && (
        <p className="text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>
          These run as one compound failure — composed into a single model and simulated once, because
          the combined result is not the sum of the individual verdicts.
        </p>
      )}

      {/* ── catalogue ── */}
      {grouped.map(({ category, items }) => (
        <div key={category} className="flex flex-col gap-1.5">
          <h3 className="text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
            {CATEGORY_LABEL[category]}
          </h3>
          {items.map((s) => {
            const isSelected = s.key in selected;
            return (
              <div
                key={s.key}
                className="cv-panel p-2.5"
                style={{ borderLeft: isSelected ? "3px solid var(--cv-blue)" : "3px solid transparent" }}
              >
                <button
                  onClick={() => toggle(s)}
                  title={s.question}
                  className="w-full text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
                  style={{ outlineColor: "var(--cv-blue)" }}
                >
                  <span className="flex items-baseline gap-2">
                    <span
                      aria-hidden
                      className="mt-0.5 inline-flex h-3 w-3 shrink-0 items-center justify-center rounded-[3px] text-[9px] font-bold"
                      style={{
                        border: `1px solid ${isSelected ? "var(--cv-blue)" : "var(--cv-steel)"}`,
                        background: isSelected ? "var(--cv-blue)" : "transparent",
                        color: "var(--cv-paper)",
                      }}
                    >
                      {isSelected ? "✓" : ""}
                    </span>
                    <span className="min-w-0 flex-1 text-[12px] font-semibold" style={{ color: "var(--cv-ink)" }}>
                      {s.name}
                    </span>
                  </span>
                  {s.target_name && (
                    <span className="mt-0.5 block pl-5 text-[10.5px]" style={{ color: "var(--cv-muted)" }}>
                      {s.target_name}
                    </span>
                  )}
                </button>

                {isSelected && s.magnitudes.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1 pl-5">
                    {s.magnitudes.map((m) => {
                      const on = selected[s.key] === m;
                      return (
                        <button
                          key={m}
                          onClick={() => setMagnitude(s.key, m)}
                          aria-pressed={on}
                          className="rounded px-1.5 py-0.5 text-[10px] font-semibold tabular-nums transition-colors focus-visible:outline focus-visible:outline-2"
                          style={{
                            background: on ? "rgba(125,211,252,.18)" : "rgba(150,170,235,.10)",
                            color: on ? "var(--cv-blue)" : "var(--cv-muted)",
                            outlineColor: "var(--cv-blue)",
                          }}
                        >
                          {fmtMagnitude(m, s.magnitude_unit)}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}

      {/* ── what we deliberately do not model ── */}
      <div className="mt-1">
        <button onClick={() => setShowLimits((v) => !v)} className="text-[10.5px] font-semibold" style={{ color: "var(--cv-muted)" }}>
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
