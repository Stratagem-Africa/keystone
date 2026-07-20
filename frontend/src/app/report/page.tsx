"use client";
// Client Component: this page fetches data in the browser and holds it in
// state, both of which only work outside the default server-rendered flow.

import { useEffect, useState } from "react";
import { Metric } from "@/components/Metric";

// One metric exactly as the engine returns it (see the `Metric` dataclass in
// prototype/keystone/simulation.py). `low`/`high` are `null` whenever there's
// no cited range to show — /design never runs the grounding step, so today
// that's always the case.
type EngineMetric = {
  value: number;
  unit: string;
  model: string;
  confidence: string;
  low: number | null;
  high: number | null;
  caveats: string[];
};

// One row of the "Component load" table (see `ComponentResult` in
// prototype/keystone/simulation.py). Unlike `EngineMetric`, these come back
// as plain numbers — no per-field model/confidence/band, because they're a
// breakdown of the SAME simulation the Verdict metrics already summarise,
// not an independently-sourced claim of their own.
type ComponentResult = {
  id: string;
  name: string;
  arrival_rps: number;
  capacity_rps: number;
  utilization: number;
  mean_latency_ms: number;
  saturated: boolean;
};

// Only the fields the report view actually reads.
type SimulationResult = {
  bottleneck_name: string;
  spofs: string[];
  metrics: Record<string, EngineMetric>;
  components: Record<string, ComponentResult>;
  caveats: string[]; // plain-English limits — "Where this is wrong", docs/03 + docs/09 §3.4
};

// One design decision from the council (see `ADR` in
// prototype/keystone/council.py). This is reasoning, not a computed number —
// no `<Metric>` here. `confidence` is the council's own qualitative word
// ("high"/"med") for how sure it is about the DECISION, a third, separate
// idea from both input-provenance (GROUNDED/ASSUMPTION/GAP) and the engine's
// per-metric confidence sentence — so it gets its own plain label, not
// reused vocabulary from either of those.
type ADR = {
  area: string;
  decision: string;
  rationale: string;
  dissent: string[];
  confidence: string;
  kill_criteria: string[];
  source: string; // "stub" = deterministic placeholder, not a live LLM council
  consensus: string[];
};

type DesignResponse = {
  model: string;
  simulation: SimulationResult;
  adrs: ADR[];
};

// /design bypasses grounding entirely (it builds the reference blueprint
// directly, no KB lookup), so every metric it returns is an ungrounded
// engine estimate — the engine's own caveats say so explicitly ("tagged
// ASSUMPTION, not calibrated to your stack"). Hardcoding ASSUMPTION here is
// accurate for THIS endpoint; revisit if/when a grounded source is wired in.
const PROVENANCE = "ASSUMPTION" as const;

// Some metric keys need light reformatting for display — the engine's raw
// units (a 0–1 ratio, integer cents) aren't what a reader wants to see. This
// only changes how a value is displayed, never what it means.
function displayMetric(key: string, m: EngineMetric): EngineMetric {
  if (key === "bottleneck_utilization") {
    return { ...m, value: Math.round(m.value * 1000) / 10, unit: "%" };
  }
  if (key === "monthly_cost") {
    return { ...m, value: Math.round(m.value) / 100, unit: "USD/mo" };
  }
  if (m.unit === "ms" || m.unit === "rps") {
    return { ...m, value: Math.round(m.value * 10) / 10 };
  }
  return m;
}

function VerdictMetric({
  label,
  metricKey,
  metric,
}: {
  label: string;
  metricKey: string;
  metric: EngineMetric;
}) {
  const m = displayMetric(metricKey, metric);
  return (
    <div className="flex flex-col gap-1">
      <p className="font-sans text-label uppercase tracking-widest text-ink-muted">
        {label}
      </p>
      <Metric value={m.value} unit={m.unit} low={m.low} high={m.high} provenance={PROVENANCE} model={m.model} />
    </div>
  );
}

// Component load table. Deliberately plain numbers, not <Metric> cards: the
// engine doesn't attach a per-field model/confidence/band to these (see the
// ComponentResult type above) — they're a breakdown of the same simulation
// the Verdict section already labeled ASSUMPTION, not a separate claim that
// needs its own provenance tag. One note above the table says so once,
// rather than repeating a pill 24 times (4 components × 6 fields).
function ComponentTable({ components }: { components: Record<string, ComponentResult> }) {
  const rows = Object.values(components);

  return (
    <div className="flex flex-col gap-2">
      <h2 className="font-sans text-h3 font-semibold">Component load</h2>
      <p className="font-mono text-provenance text-ink-muted">
        Same ASSUMPTION-provenance simulation as the Verdict above — see &ldquo;Where this is wrong&rdquo;.
      </p>
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-mist text-left">
            <th className="font-sans text-label uppercase tracking-widest text-ink-muted py-2">Component</th>
            <th className="font-sans text-label uppercase tracking-widest text-ink-muted py-2 text-right">Arrival (rps)</th>
            <th className="font-sans text-label uppercase tracking-widest text-ink-muted py-2 text-right">Capacity (rps)</th>
            <th className="font-sans text-label uppercase tracking-widest text-ink-muted py-2 text-right">Utilisation</th>
            <th className="font-sans text-label uppercase tracking-widest text-ink-muted py-2 text-right">Mean latency (ms)</th>
            <th className="font-sans text-label uppercase tracking-widest text-ink-muted py-2 text-right">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className="border-b border-mist">
              <td className="font-serif text-body py-2">{c.name}</td>
              <td className="font-mono text-mono-data py-2 text-right">{Math.round(c.arrival_rps)}</td>
              <td className="font-mono text-mono-data py-2 text-right">{Math.round(c.capacity_rps)}</td>
              <td className="font-mono text-mono-data py-2 text-right">{Math.round(c.utilization * 1000) / 10}%</td>
              <td className="font-mono text-mono-data py-2 text-right">{Math.round(c.mean_latency_ms * 10) / 10}</td>
              <td className={`font-mono text-provenance py-2 text-right ${c.saturated ? "text-signal-red" : "text-ink-muted"}`}>
                {c.saturated ? "SATURATED" : "ok"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// One ADR — the council's reasoning, not an engine number. Serif for the
// decision/rationale prose (docs/09 §2.5: serif = the model reasoned this).
// Dissent gets its own marginalia color (dissent-indigo) so a recorded
// disagreement reads as a distinct voice, not just more body text. Kill
// criteria get a grounded-green border per docs/09 §6.3 — framing every
// decision as falsifiable, never final.
function ADRCard({ adr }: { adr: ADR }) {
  return (
    <div className="flex flex-col gap-3 border-b border-mist pb-6">
      <h3 className="font-sans text-h3 font-semibold">{adr.area}</h3>

      <p className="font-serif text-body">{adr.decision}</p>
      <p className="font-serif text-body text-ink-muted italic">{adr.rationale}</p>

      {adr.dissent.length > 0 && (
        <ul className="flex flex-col gap-1 border-l-2 border-dissent-indigo pl-4">
          {adr.dissent.map((line, i) => (
            <li key={i} className="font-serif text-body text-dissent-indigo">
              {line}
            </li>
          ))}
        </ul>
      )}

      {adr.kill_criteria.length > 0 && (
        <div className="border border-grounded-green rounded-lg p-3 flex flex-col gap-1">
          <p className="font-mono text-provenance uppercase tracking-widest text-grounded-green">
            Kill criteria — revisit if…
          </p>
          <ul className="list-disc list-inside">
            {adr.kill_criteria.map((line, i) => (
              <li key={i} className="font-serif text-body">
                {line}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="font-mono text-provenance text-ink-muted">
        council confidence: {adr.confidence}
      </p>
    </div>
  );
}

function ADRSection({ adrs }: { adrs: ADR[] }) {
  const isStub = adrs.some((a) => a.source === "stub");

  return (
    <div className="flex flex-col gap-4">
      <h2 className="font-sans text-h3 font-semibold">Design decisions (council)</h2>

      {isStub && (
        // Honesty rule: never let a canned placeholder read as live reasoning.
        <p className="font-mono text-provenance text-assumption-amber">
          ASSUMPTION · Council running in DETERMINISTIC STUB mode — illustrative ADRs, not live reasoning.
        </p>
      )}

      {adrs.map((adr) => (
        <ADRCard key={adr.area} adr={adr} />
      ))}
    </div>
  );
}

// "Where this is wrong" — docs/09 §3.4: "Not a footnote — a full, designed
// section with its own amber left-rule, serif body, and a standing headline:
// 'Read before trusting a number.'" MUST be a persistent, non-dismissable
// surface on every report — so there's no collapse/toggle here on purpose.
//
// Each caveat here is one plain-English sentence straight from the engine's
// `caveats` list (see simulation.py) — the engine doesn't currently pair each
// one with a specific metric key, so we render them as-is rather than
// inventing a linkage the data doesn't actually have.
function WhereThisIsWrong({ caveats }: { caveats: string[] }) {
  return (
    <div className="flex flex-col gap-4 border-l-4 border-assumption-amber pl-6 py-2">
      <h2 className="font-sans text-h1 font-semibold">Where this is wrong</h2>
      <p className="font-mono text-provenance uppercase tracking-widest text-assumption-amber">
        Read before trusting a number
      </p>
      <ul className="flex flex-col gap-3">
        {caveats.map((caveat, i) => (
          <li key={i} className="font-serif text-body">
            {caveat}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ReportPage() {
  const [data, setData] = useState<DesignResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // An async function declared *inside* useEffect, then called immediately.
    // (useEffect itself can't be async — React requires its return value to
    // be a cleanup function or nothing.)
    async function fetchReport() {
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/design`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}), // {} = use every server-side default
        });

        if (!res.ok) {
          throw new Error(`API returned ${res.status}`);
        }

        const json: DesignResponse = await res.json();
        console.log("design response:", json); // <- look at this in devtools
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "unknown error");
      } finally {
        setLoading(false);
      }
    }

    fetchReport();
  }, []); // empty array = run once, when the page first mounts

  if (loading) return <p className="p-8 font-mono text-provenance">Loading report…</p>;
  if (error) return <p className="p-8 font-mono text-provenance text-assumption-amber">Error: {error}</p>;
  if (!data) return null; // fetch finished with no error but also no data — shouldn't happen, keeps TS happy

  const { simulation } = data;

  return (
    <section className="p-8 flex flex-col gap-6">
      <h1 className="font-sans text-h1 font-semibold">Verdict</h1>

      <p className="font-serif text-body">
        Bottleneck: <span className="font-mono text-mono-data">{simulation.bottleneck_name}</span>
      </p>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <VerdictMetric label="Utilisation" metricKey="bottleneck_utilization" metric={simulation.metrics.bottleneck_utilization} />
        <VerdictMetric label="Max safe load" metricKey="breakpoint_rps_safe" metric={simulation.metrics.breakpoint_rps_safe} />
        <VerdictMetric label="Theoretical max" metricKey="breakpoint_rps_theoretical" metric={simulation.metrics.breakpoint_rps_theoretical} />
        <VerdictMetric label="Mean latency" metricKey="mean_latency_ms" metric={simulation.metrics.mean_latency_ms} />
        <VerdictMetric label="p50 latency" metricKey="p50_ms" metric={simulation.metrics.p50_ms} />
        <VerdictMetric label="p95 latency" metricKey="p95_ms" metric={simulation.metrics.p95_ms} />
        <VerdictMetric label="p99 latency" metricKey="p99_ms" metric={simulation.metrics.p99_ms} />
        <VerdictMetric label="Monthly cost" metricKey="monthly_cost" metric={simulation.metrics.monthly_cost} />
      </div>

      {simulation.spofs.length > 0 && (
        // signal-red, not assumption-amber: docs/09 reserves red for real
        // failure modes / SPOFs, and amber exclusively for ASSUMPTION/GAP.
        // A SPOF isn't "we're guessing" — it's "this really can take the
        // whole system down," which is a different kind of claim.
        <p className="font-mono text-provenance text-signal-red">
          Single points of failure: {simulation.spofs.join(", ")}
        </p>
      )}

      <ComponentTable components={simulation.components} />

      <ADRSection adrs={data.adrs} />

      <WhereThisIsWrong caveats={simulation.caveats} />
    </section>
  );
}
