"use client";

import { useState } from "react";
import type { ArchMap, ArchMapMetric, ArchMapNode } from "@/lib/archMap";

// The verdict rail: what the engine concluded, how confident it is, and where it is wrong.
//
// This is the half of the product a diagram-and-animate tool has no equivalent for, so it is not
// tucked behind a toggle. Every number arrives with the model that produced it; the confidence band
// is shown when the engine could derive one and explicitly marked absent when it could not (an
// omitted band is a finding, never a blank); "Where this is wrong" is always present and never
// collapsed away to make the panel look tidier.
//
// PRIME DIRECTIVE: this file computes no metric. Money is formatted from the engine's integer minor
// units without float arithmetic (ADR-008), and everything else is displayed as given.

function fmtMoneyFromCents(cents: number): string {
  const neg = cents < 0;
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100);
  const rest = abs % 100;
  return `${neg ? "-" : ""}$${dollars.toLocaleString("en-US")}.${String(rest).padStart(2, "0")}`;
}

function fmtRps(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toFixed(0);
}

// Latency is null when a component is over capacity (rho >= 1): the engine returns inf rather than a
// fake number, so we show "—", never crash. Mirrors fmtRps — an absent number is a finding, not a blank.
function fmtMs(n: number | null, digits = 0): string {
  return n === null || !Number.isFinite(n) ? "—" : n.toFixed(digits);
}

function fmtMetric(m: ArchMapMetric): string {
  if (m.unit === "usd_minor_per_month") return `${fmtMoneyFromCents(m.value)} / mo`;
  if (m.unit === "ratio") return `${(m.value * 100).toFixed(1)}%`;
  if (m.unit === "ms") return `${m.value.toFixed(1)} ms`;
  if (m.unit === "rps") return `${fmtRps(m.value)} req/s`;
  return String(m.value);
}

const METRIC_LABEL: Record<string, string> = {
  bottleneck_utilization: "How full the busiest part is (utilisation)",
  breakpoint_rps_safe: "Safe limit — stay under this",
  breakpoint_rps_theoretical: "Breaking point — no safety margin",
  mean_latency_ms: "Average response time",
  p50_ms: "Typical response time (p50 — half are slower)",
  p95_ms: "Slow response time (p95 — 5 in 100 are slower)",
  p99_ms: "Slowest response time (p99 — 1 in 100 is still slower)",
  monthly_cost: "Monthly cost",
};

const PROVENANCE_TONE: Record<string, { bg: string; fg: string }> = {
  GROUNDED: { bg: "rgba(74,222,128,.15)", fg: "var(--cv-green)" },
  RECONCILE: { bg: "rgba(251,191,36,.16)", fg: "var(--cv-amber)" },
  ASSUMPTION: { bg: "rgba(150,170,235,.16)", fg: "var(--cv-muted)" },
  GAP: { bg: "rgba(248,113,113,.15)", fg: "var(--cv-red)" },
};

function Chip({ text }: { text: string }) {
  const tone = PROVENANCE_TONE[text] ?? PROVENANCE_TONE.ASSUMPTION;
  return (
    <span
      className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
      style={{ background: tone.bg, color: tone.fg }}
    >
      {text}
    </span>
  );
}

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="flex items-baseline gap-1.5 text-[10px] font-bold uppercase tracking-[0.16em]" style={{ color: "var(--cv-muted)" }}>
        {title}
        {count !== undefined && <span style={{ opacity: 0.7 }}>({count})</span>}
      </h3>
      {children}
    </section>
  );
}

// Flow names arrive as backend ids ("driver_ping", "trip_update", "check_availability") and were
// rendered raw, so the panel showed snake_case to people who have never seen snake_case. Display
// only — `f.name` stays the key everywhere else, so nothing downstream shifts.
function humanFlow(name: string): string {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

interface DesignPanelProps {
  arch: ArchMap;
  /** True when no reference architecture matched the intent — the design on screen is a neutral
   *  starting shape, not a design of what was asked for. Stated here, not just in the chrome. */
  unmatched?: boolean;
  selected: ArchMapNode | null;
  activeFlowIndex: number | null;
  onFlow: (i: number | null) => void;
  onClearSelection: () => void;
}

export function DesignPanel({
  arch, unmatched = false, selected, activeFlowIndex, onFlow, onClearSelection,
}: DesignPanelProps) {
  const [showWorking, setShowWorking] = useState(false);
  const { meta, verdict } = arch;

  // ── a selected component takes over the rail ──
  if (selected) {
    const cap = selected.capacity_rps;
    return (
      <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">
        <button onClick={onClearSelection} className="self-start text-[10.5px] font-semibold" style={{ color: "var(--cv-blue)" }}>
          ← back to the verdict
        </button>
        <div className="cv-panel p-3">
          <div className="flex items-start gap-2">
            <span aria-hidden className="text-[15px] leading-none">{selected.icon}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-semibold leading-tight" style={{ color: "var(--cv-ink)" }}>{selected.name}</p>
              <p className="mt-0.5 text-[11px] leading-snug" style={{ color: "var(--cv-muted)" }}>{selected.role}</p>
            </div>
            <Chip text={selected.provenance} />
          </div>
          <dl className="mt-3 flex flex-col gap-1 text-[11.5px]">
            {[
              ["Receives", `${fmtRps(selected.arrival_rps)} requests per second`],
              ["Capacity", `${fmtRps(cap)} requests per second (${selected.instances} copies × ${fmtRps(selected.per_instance_rps)} each)`],
              ["How full it is (utilisation)", selected.utilization === null ? "—" : `${(selected.utilization * 100).toFixed(1)}%`],
              ["Time to do its work (not counting waiting in line)", `${selected.base_latency_ms.toFixed(1)} ms`],
              ["Cost", `${fmtMoneyFromCents(selected.monthly_cost_cents * selected.instances)} / mo`],
            ].map(([k, v]) => (
              <div key={k} className="flex items-baseline justify-between gap-3">
                <dt style={{ color: "var(--cv-muted)" }}>{k}</dt>
                <dd className="tabular-nums font-semibold" style={{ color: "var(--cv-ink)" }}>{v}</dd>
              </div>
            ))}
          </dl>
        </div>

        {selected.evidence.length > 0 ? (
          <Section title="Published figures we found" count={selected.evidence.length}>
            {selected.evidence.map((e, i) => (
              <div key={i} className="cv-panel p-2.5">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-[11.5px] font-semibold" style={{ color: "var(--cv-ink)" }}>{e.metric}</span>
                  <Chip text={e.status} />
                </div>
                <p className="mt-1 text-[10.5px] tabular-nums" style={{ color: "var(--cv-muted)" }}>
                  your number: {e.your_value} {e.unit} · published elsewhere: {e.central} (published range {e.low}–{e.high})
                </p>
                {e.measured_on && (
                  <p className="mt-1 text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                    the setup behind that figure: {e.measured_on}
                  </p>
                )}
                {e.sources.map((s, j) => (
                  <p key={j} className="mt-1 text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                    {s.source} — {s.reference}
                  </p>
                ))}
              </div>
            ))}
          </Section>
        ) : (
          <p className="text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
            We found no published figure for how much this part can handle. The number above is a starting default, labelled
            <b> ASSUMPTION</b> — meaning we guessed it. Nobody measured your setup.
          </p>
        )}
      </div>
    );
  }

  // ── the verdict ──
  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3">
      {/* No reference matched: the numbers below are the engine's arithmetic on a PLACEHOLDER shape.
          That has to sit above the verdict, not beside the title, or the verdict reads as an answer
          to the question that was actually asked. */}
      {unmatched && (
        <div className="cv-panel p-3" style={{ borderLeft: "3px solid var(--cv-amber)" }}>
          <p className="text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--cv-amber)" }}>
            Not a design of what you asked for
          </p>
          <p className="mt-1.5 text-[11.5px] leading-snug" style={{ color: "var(--cv-ink)" }}>
            Nothing in the reference library matched your description, so this is a neutral
            starting layout — a load balancer, app servers, a cache and one database. The parts, their sizes and the traffic figure are all placeholders —
            every figure below is correct arithmetic on <em>those placeholders</em>, and describes
            this generic layout, not your app. Change it on the canvas, then run the numbers again.
          </p>
        </div>
      )}

      {/* High-stakes domains carry a mandatory expert-review flag (docs/03). Never suppressed. */}
      {meta.high_stakes && (
        <div className="cv-panel p-3" style={{ borderLeft: "3px solid var(--cv-amber)" }}>
          <p className="text-[11px] font-bold uppercase tracking-wider" style={{ color: "var(--cv-amber)" }}>
            Expert review required
          </p>
          <p className="mt-1.5 text-[11.5px] leading-snug" style={{ color: "var(--cv-ink)" }}>
            This design touches a high-stakes domain
            {meta.domain_flags.length > 0 && (
              <> (<span className="font-mono">{meta.domain_flags.join(", ")}</span>)</>
            )}
            . These numbers are directional — the right ballpark, not a safe basis for launching. Nothing here is certified and no expert has reviewed it: have someone who has run a system like this check it first.
          </p>
        </div>
      )}

      <Section title="The verdict">
        <div className="cv-panel flex flex-col gap-2.5 p-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: "var(--cv-muted)" }}>What it costs</p>
            <p className="text-[19px] font-semibold tabular-nums" style={{ color: "var(--cv-ink)" }}>
              {fmtMoneyFromCents(verdict.monthly_cost_cents)}
              <span className="text-[12px] font-normal" style={{ color: "var(--cv-muted)" }}> / month</span>
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: "var(--cv-muted)" }}>Where it starts to strain</p>
            <p className="text-[19px] font-semibold tabular-nums" style={{ color: "var(--cv-ink)" }}>
              ~{fmtRps(verdict.breakpoint_rps_safe)}
              <span className="text-[12px] font-normal" style={{ color: "var(--cv-muted)" }}> requests per second</span>
            </p>
            {/* When several components are within a few points of each other, naming ONE of them
                here is a coin-flip printed as a determination — the inputs that separate them carry
                far more uncertainty than the gap does. Say "joint suspects" in the headline rather
                than leaving the correction to a caveat further down the page that contradicts it. */}
            {(verdict.bottleneck_contenders?.length ?? 1) > 1 ? (
              <p className="mt-0.5 text-[11px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                before <b style={{ color: "var(--cv-ink)" }}>{verdict.bottleneck_contenders!.length} parts</b> run out of room together —{" "}
                {verdict.bottleneck_contenders!.join(", ")}. They are within{" "}
                {(verdict.bottleneck_margin_pts ?? 0).toFixed(1)} points of each other, which is closer
                than we can tell apart. Treat them as joint suspects and measure before you spend.
              </p>
            ) : (
              <p className="mt-0.5 text-[11px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                before <b style={{ color: "var(--cv-ink)" }}>{verdict.bottleneck_name}</b> runs out of room — the first part to give way
                {verdict.bottleneck_utilization !== null && (
                  <>. It is already {(verdict.bottleneck_utilization * 100).toFixed(0)}% full</>
                )}
              </p>
            )}
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: "var(--cv-muted)" }}>Response time (latency)</p>
            <p className="text-[12.5px] tabular-nums" style={{ color: "var(--cv-ink)" }}>
              {fmtMs(verdict.latency.mean_ms, 1)} ms on average
              <span style={{ color: "var(--cv-muted)" }}>
                {" "}· p95 {fmtMs(verdict.latency.p95_ms)} ms — 5 in 100 are slower · p99 {fmtMs(verdict.latency.p99_ms)} ms — 1 in 100 is slower
              </span>
            </p>
          </div>
          <p className="text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
            <b>Confidence:</b> {meta.confidence} · accuracy grade {meta.accuracy_level} — the right ballpark only, not safe to build on
          </p>
        </div>
      </Section>

      {verdict.spofs.length > 0 && (
        <Section title="Single points of failure — nothing takes over if one fails" count={verdict.spofs.length}>
          <ul className="flex flex-col gap-1">
            {verdict.spofs.map((s) => (
              <li key={s} className="text-[11.5px]" style={{ color: "var(--cv-ink)" }}>
                <span style={{ color: "var(--cv-amber)" }}>▲</span> {s}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="What people actually do (request journeys)" count={arch.flows.length}>
        {arch.flows.map((f, i) => (
          <button
            key={f.name}
            onClick={() => onFlow(activeFlowIndex === i ? null : i)}
            className="cv-panel w-full p-2.5 text-left transition-colors hover:bg-white/[0.04] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1"
            style={{
              outlineColor: "var(--cv-blue)",
              borderLeft: activeFlowIndex === i ? `3px solid ${f.color}` : "3px solid transparent",
            }}
          >
            <span className="flex items-baseline gap-2">
              <span aria-hidden className="inline-block h-2 w-2 shrink-0 rounded-sm" style={{ background: f.color }} />
              <span className="text-[12px] font-semibold" style={{ color: "var(--cv-ink)" }}>{humanFlow(f.name)}</span>
            </span>
            <span className="mt-0.5 block text-[10.5px] tabular-nums" style={{ color: "var(--cv-muted)" }}>
              {(f.share * 100).toFixed(0)}% of traffic
              {f.latency && <> · p99 {fmtMs(f.latency.p99_ms)} ms (1 in 100 is slower)</>}
            </span>
          </button>
        ))}
      </Section>

      <Section title="The main numbers" count={arch.metrics.length}>
        <div className="cv-panel divide-y" style={{ borderColor: "var(--cv-line)" }}>
          {arch.metrics.map((m) => (
            <div key={m.key} className="p-2.5" style={{ borderTopColor: "var(--cv-line)" }}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[11.5px]" style={{ color: "var(--cv-muted)" }}>
                  {METRIC_LABEL[m.key] ?? m.key}
                </span>
                <span className="tabular-nums text-[12px] font-semibold" style={{ color: "var(--cv-ink)" }}>
                  {fmtMetric(m)}
                </span>
              </div>
              <p className="mt-1 text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                {m.low !== null && m.high !== null ? (
                  <>estimated range {m.low.toFixed(1)}–{m.high.toFixed(1)} · worked out with </>
                ) : (
                  <span style={{ color: "var(--cv-amber)" }}>no range — the cited evidence is not precise enough to give one; unknown, not zero · worked out with </span>
                )}
                <span className="font-mono">{m.model}</span>
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* Always present, never collapsed. Honesty is the feature (docs/03). */}
      <Section title="Where this is wrong" count={arch.caveats.length}>
        <ul className="flex flex-col gap-2">
          {arch.caveats.map((c, i) => (
            <li key={i} className="text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
              {c}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Where these numbers came from" count={arch.assumptions.length}>
        <ul className="flex flex-col gap-1.5">
          {arch.assumptions.map((a, i) => (
            <li key={i} className="flex items-start gap-2">
              <Chip text={a.provenance} />
              <span className="text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                <b style={{ color: "var(--cv-ink)" }}>{a.subject}</b> — {a.statement}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <div>
        <button onClick={() => setShowWorking((v) => !v)} className="text-[10.5px] font-semibold" style={{ color: "var(--cv-blue)" }}>
          {showWorking ? "▾" : "▸"} how these numbers were computed ({arch.derivation.length} steps)
        </button>
        {showWorking && (
          <ol className="mt-2 flex list-decimal flex-col gap-1.5 pl-4">
            {arch.derivation.map((d, i) => (
              <li key={i} className="text-[10px] leading-snug" style={{ color: "var(--cv-muted)" }}>{d}</li>
            ))}
          </ol>
        )}
      </div>

      <p className="pt-1 text-[9.5px] leading-snug" style={{ color: "var(--cv-muted)", opacity: 0.8 }}>
        Engine {meta.engine_version} · {fmtRps(meta.offered_load_rps)} requests per second going in. Every figure above came from
        Keystone&apos;s own simulation engine, which gives the same answer every time it runs. No AI wrote any number on this page.
      </p>
    </div>
  );
}
