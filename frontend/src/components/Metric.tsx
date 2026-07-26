// Every engine number in Keystone must use <Metric>.
// TypeScript enforces that value, band bounds, provenance, and model are ALL provided.
// A bare number anywhere in the UI is a defect — docs/09 §3.1, NFR-1.

type Provenance = "GROUNDED" | "ASSUMPTION" | "GAP";

type ConfidenceBandProps = {
  provenance: Provenance;
  low: number | null;   // null = no cited range yet (not zero uncertainty — just unknown)
  high: number | null;  // null = no cited range yet (not zero uncertainty — just unknown)
  value: number; // the centre value — used to compute relative spread
};

type MetricProps = {
  value: number;       // the engine-computed number
  unit: string;        // e.g. "ms", "req/s", "%"
  low: number | null;         // null = no cited range yet
  high: number | null;        // null = no cited range yet
  provenance: Provenance;
  model: string;       // what produced this number, e.g. "M/M/1 queue"
};

// ConfidenceBand — horizontal bar whose width encodes uncertainty and
// whose hue rides the Doubt→Trust ramp (amber → green). docs/09 §3.1.
export function ConfidenceBand({ provenance, low, high, value }: ConfidenceBandProps) {
  // No cited range to show — render a visibly "unknown width" dashed outline
  // instead of computing a spread from missing numbers. Fabricating a width
  // here would be false precision (docs/09: no bare/faked numbers).
  if (low === null || high === null) {
    return (
      <div className="relative h-1 w-full rounded-full bg-mist mt-1" aria-hidden="true">
        <div className="absolute left-0 top-0 h-full w-full rounded-full border border-dashed border-assumption-amber/50" />
      </div>
    );
  }

  // Relative spread: (range / value), clamped so the bar is always readable.
  const spread = value > 0
    ? Math.min(Math.max((high - low) / value, 0.08), 0.92)
    : 0.5;

  // 3-stop Doubt→Trust ramp (docs/09 §2.4): ASSUMPTION amber → GAP/mixed teal → GROUNDED green.
  const color =
    provenance === "GROUNDED" ? "bg-grounded-green"
    : provenance === "GAP" ? "bg-confidence-teal"
    : "bg-assumption-amber";

  return (
    <div className="relative h-1 w-full rounded-full bg-mist mt-1" aria-hidden="true">
      <div
        className={`absolute left-0 top-0 h-full rounded-full transition-all ease-settle duration-band ${color}`}
        style={{ width: `${Math.round(spread * 100)}%` }}
      />
    </div>
  );
}

// Metric — the canonical number primitive. Cannot render without all required props.
export function Metric({ value, unit, low, high, provenance, model }: MetricProps) {
  const pillStyle =
    provenance === "GROUNDED" ? "text-grounded-green border-grounded-green"
    : provenance === "GAP" ? "text-confidence-teal border-confidence-teal"
    : "text-assumption-amber border-assumption-amber";

  const rangeLabel =
    low === null || high === null
      ? "no cited range yet — unknown, not zero"
      : `${low}–${high} ${unit}`;

  return (
    // group + focusable = the band is an inspectable instrument: hover OR keyboard-focus reveals the
    // "x-ray" (docs/09 §3.1 living band / §4.2 provenance x-ray). architect-blue focus ring works on
    // both the paper report and the dark landing seam, so no per-surface ring-offset is needed.
    <span
      tabIndex={0}
      className="group relative inline-flex flex-col gap-0.5 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
      aria-label={`${value}${unit}, provenance ${provenance}, range ${rangeLabel}, model ${model}`}
    >
      {/* Value in mono — typeface signals "engine computed this" (docs/09 §2.5) */}
      <span className="font-mono text-mono-data tabular-nums leading-none">
        {value}
        <span className="text-ink-muted ml-0.5 text-xs">{unit}</span>
      </span>

      {/* Band — width = uncertainty, hue = confidence level */}
      <ConfidenceBand provenance={provenance} low={low} high={high} value={value} />

      {/* Provenance pill + model attribution */}
      <span className="flex items-center gap-1.5 mt-0.5">
        <span className={`font-mono text-provenance uppercase tracking-widest border rounded px-1 py-px ${pillStyle}`}>
          {provenance}
        </span>
        <span className="font-mono text-provenance text-ink-muted">{model}</span>
      </span>

      {/* X-ray popover — reveals HOW the number was made. CSS-only (group-hover / group-focus-within),
          so it needs no framework API and rides the global reduced-motion path. */}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-30 mt-2 hidden w-max max-w-[16rem] flex-col gap-1 rounded-lg border border-mist bg-paper p-3 text-left shadow-lg group-hover:flex group-focus-within:flex"
      >
        <span className="font-sans text-provenance uppercase tracking-widest text-ink-muted">
          how this number was made
        </span>
        <span className="font-serif text-label text-slate-ink">
          model: <span className="font-mono">{model}</span>
        </span>
        <span className="font-serif text-label text-slate-ink">
          range: <span className="font-mono">{rangeLabel}</span>
        </span>
      </span>
    </span>
  );
}
