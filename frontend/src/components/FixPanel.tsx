"use client";

import { useState } from "react";
import type { RemediationPlan } from "@/lib/remediation";

// "It's over capacity" is only half an answer. This panel gives the other half: the smallest
// instance change that makes the design hold at the load you are looking at, what that costs, and —
// where adding instances would be the wrong answer entirely — the architectural options instead.
//
// The planner picks instance counts; the engine decides whether they worked. Everything shown here
// is one of those two engine runs or their difference.

function money(cents: number): string {
  const neg = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  return `${neg ? "−" : ""}$${Math.floor(abs / 100).toLocaleString("en-US")}.${String(abs % 100).padStart(2, "0")}`;
}

function rps(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toFixed(0);
}

interface FixPanelProps {
  /** The load currently on screen — what a plan would be built for. */
  targetRps: number;
  plan: RemediationPlan | null;
  running: boolean;
  error: string | null;
  applied: boolean;
  onPlan: () => void;
  onApply: () => void;
  onRevert: () => void;
}

export function FixPanel({
  targetRps, plan, running, error, applied, onPlan, onApply, onRevert,
}: FixPanelProps) {
  const [showLimits, setShowLimits] = useState(false);
  const [showWorking, setShowWorking] = useState(false);

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
      <h2 className="text-[11px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
        Make it handle the traffic
      </h2>

      <button
        onClick={onPlan}
        disabled={running}
        className="rounded-full px-3.5 py-2 text-[11.5px] font-semibold transition-transform active:scale-[0.98] disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        style={{ background: "var(--cv-blue)", color: "var(--cv-paper)", outlineColor: "var(--cv-blue)" }}
      >
        {running ? "Working it out…" : `Plan for ${rps(targetRps)} requests a second`}
      </button>
      <p className="text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>
        This plans for the traffic on the canvas right now — to plan for a different amount, move the slider first.
      </p>

      {error && (
        <p className="cv-panel p-2.5 text-[11.5px] leading-snug" style={{ color: "var(--cv-amber)" }}>{error}</p>
      )}

      {plan && (
        <>
          <div
            className="cv-panel p-3"
            style={{ borderLeft: `3px solid ${plan.holds ? "var(--cv-green)" : "var(--cv-amber)"}` }}
          >
            <span
              className="inline-block rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
              style={{
                background: plan.holds ? "rgba(74,222,128,.15)" : "rgba(251,191,36,.16)",
                color: plan.holds ? "var(--cv-green)" : "var(--cv-amber)",
              }}
            >
              {plan.holds ? "fixable with more copies" : "more copies aren't enough"}
            </span>
            <p className="mt-2 text-[12px] leading-snug" style={{ color: "var(--cv-ink)" }}>{plan.verdict}</p>

            <dl className="mt-3 flex flex-col gap-1 text-[11.5px]">
              {[
                ["Busiest part, % of capacity used (utilisation)", `${((plan.before.bottleneck_utilization ?? 0) * 100).toFixed(0)}% → ${((plan.after.bottleneck_utilization ?? 0) * 100).toFixed(0)}%`],
                ["Average response time (mean latency)", `${plan.before.mean_latency_ms.toFixed(0)} → ${plan.after.mean_latency_ms.toFixed(0)} ms`],
                ["Monthly cost", `${money(plan.before.monthly_cost_cents)} → ${money(plan.after.monthly_cost_cents)}`],
                ["Cost difference", `${plan.monthly_cost_delta_cents >= 0 ? "+" : ""}${money(plan.monthly_cost_delta_cents)} / month`],
              ].map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between gap-3">
                  <dt style={{ color: "var(--cv-muted)" }}>{k}</dt>
                  <dd className="tabular-nums font-semibold" style={{ color: "var(--cv-ink)" }}>{v}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
              <b>How much to trust the numbers after the change (confidence):</b> {plan.after.confidence}
            </p>
          </div>

          {plan.remedies.length > 0 && (
            <section className="flex flex-col gap-1.5">
              <h3 className="text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
                Add more copies ({plan.remedies.length})
              </h3>
              {plan.remedies.map((r) => (
                <div key={r.component_id} className="cv-panel p-2.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-semibold" style={{ color: "var(--cv-ink)" }}>{r.component_name}</span>
                    <span className="shrink-0 tabular-nums text-[12px] font-bold" style={{ color: "var(--cv-green)" }}>
                      {r.from_instances} → {r.to_instances} copies
                    </span>
                  </div>
                  <p className="mt-1 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>{r.reason}</p>
                </div>
              ))}
              <button
                onClick={applied ? onRevert : onApply}
                className="mt-1 self-start text-[10.5px] font-semibold"
                style={{ color: "var(--cv-blue)" }}
              >
                {applied ? "← show the original design" : "→ show the fixed design on the canvas"}
              </button>
            </section>
          )}

          {plan.blockers.length > 0 && (
            <section className="flex flex-col gap-1.5">
              <h3 className="text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-amber)" }}>
                Adding more copies won&apos;t fix these ({plan.blockers.length})
              </h3>
              {plan.blockers.map((b) => (
                <div key={b.component_id} className="cv-panel p-2.5" style={{ borderLeft: "3px solid var(--cv-amber)" }}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-semibold" style={{ color: "var(--cv-ink)" }}>{b.component_name}</span>
                    <span className="shrink-0 tabular-nums text-[11.5px]" style={{ color: "var(--cv-red)" }}>
                      {(b.utilization * 100).toFixed(0)}% of capacity
                    </span>
                  </div>
                  <p className="mt-1 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>{b.guidance}</p>
                </div>
              ))}
            </section>
          )}

          <div>
            <button onClick={() => setShowLimits((v) => !v)} className="text-[10.5px] font-semibold" style={{ color: "var(--cv-amber)" }}>
              {showLimits ? "▾" : "▸"} how this plan could be wrong ({plan.limits.length} known limits)
            </button>
            {showLimits && (
              <ul className="mt-2 flex flex-col gap-2">
                {plan.limits.map((l, i) => (
                  <li key={i} className="text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>{l}</li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <button onClick={() => setShowWorking((v) => !v)} className="text-[10.5px] font-semibold" style={{ color: "var(--cv-blue)" }}>
              {showWorking ? "▾" : "▸"} how this plan was reached ({plan.derivation.length} steps)
            </button>
            {showWorking && (
              <ol className="mt-2 flex list-decimal flex-col gap-1.5 pl-4">
                {plan.derivation.map((d, i) => (
                  <li key={i} className="text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>{d}</li>
                ))}
              </ol>
            )}
          </div>
        </>
      )}
    </div>
  );
}
