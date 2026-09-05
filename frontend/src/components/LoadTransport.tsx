"use client";

import type { SweepFrame } from "./ArchCanvas";

// The load axis. Each stop on this slider is a REAL `simulate()` run at that offered load
// (`arch_map.build_load_sweep`) — dragging steps between engine results, it never interpolates
// between them. That is the honest analogue of a live traffic dial: the design does not "run",
// it is re-solved, and every stop is an answer the engine actually gave.

interface LoadTransportProps {
  frames: SweepFrame[];
  index: number;
  /** The stop that IS the design load (multiple 1) — where "back" returns to. */
  baseIndex: number;
  onIndex: (i: number) => void;
  disabled?: boolean;
}

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return n.toFixed(0);
}

export function LoadTransport({ frames, index, baseIndex, onIndex, disabled = false }: LoadTransportProps) {
  if (frames.length === 0) return null;
  const frame = frames[Math.min(index, frames.length - 1)];
  const peak = frame.bottleneck_utilization;
  const tone =
    peak === null || !Number.isFinite(peak)
      ? "var(--cv-muted)"
      : peak > 1
        ? "var(--cv-red)"
        : peak > 0.85
          ? "var(--cv-amber)"
          : "var(--cv-green)";

  // The first stop at or beyond saturation — "push to where it breaks" in one click.
  const breakIdx = frames.findIndex((f) => (f.bottleneck_utilization ?? 0) > 1);
  const target = breakIdx >= 0 ? breakIdx : frames.length - 1;
  const atTarget = index === target;

  return (
    <div
      className="flex items-center gap-4 px-4 py-2.5"
      style={{ borderTop: "1px solid var(--cv-line)", background: "var(--cv-panel)" }}
    >
      <button
        onClick={() => onIndex(atTarget ? baseIndex : target)}
        disabled={disabled}
        className="shrink-0 rounded-full px-3.5 py-1.5 text-[11.5px] font-semibold transition-transform active:scale-[0.98] disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        style={{ background: "var(--cv-blue)", color: "var(--cv-paper)", outlineColor: "var(--cv-blue)" }}
      >
        {atTarget ? "↺ Back to design load" : `▶ Push to ${fmt(frames[target].load_rps)} rps`}
      </button>

      <input
        type="range"
        min={0}
        max={frames.length - 1}
        step={1}
        value={Math.min(index, frames.length - 1)}
        onChange={(e) => onIndex(Number(e.target.value))}
        disabled={disabled}
        aria-label="Offered load — each stop is a separate engine run"
        className="h-1 min-w-0 flex-1 cursor-pointer appearance-none rounded-full disabled:opacity-40"
        style={{ background: "rgba(150,170,235,.22)", accentColor: "var(--cv-blue)" }}
      />

      <div className="flex shrink-0 items-baseline gap-3 font-mono text-[11.5px] tabular-nums">
        <span style={{ color: "var(--cv-ink)" }}>{fmt(frame.load_rps)} rps</span>
        <span style={{ color: "var(--cv-muted)" }}>{frame.multiple}×</span>
        <span style={{ color: tone }}>
          peak {peak === null || !Number.isFinite(peak) ? "—" : `${Math.round(peak * 100)}%`}
        </span>
      </div>

      <p className="hidden shrink-0 text-[10px] leading-tight lg:block" style={{ color: "var(--cv-muted)", maxWidth: "20ch" }}>
        every stop is its own engine run — nothing between them is interpolated
      </p>
    </div>
  );
}
