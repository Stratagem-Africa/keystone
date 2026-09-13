"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ArchMap, ArchMapNode, NodeStatus } from "@/lib/archMap";
import { useReducedMotion } from "@/lib/useReducedMotion";

// The architecture map, as a real React component.
//
// It replaces the sandboxed iframe that used to carry the Python-rendered HTML. Same visual
// language (the `--cv-*` tokens in globals.css mirror arch_map.py's _CSS), but now it is a
// component: it takes engine output as props, so it can be re-pointed at a sweep frame or at a
// chaos scenario's perturbed run without a round-trip through a string template.
//
// PRIME DIRECTIVE. This file computes no metric. Every number rendered here is read straight off
// `arch` (the engine's `build_arch_map` output) or off a `frame` (a real `simulate()` run at a
// different offered load). The only arithmetic is *visual encoding* — turning an engine number
// into a bar width or a particle count, the way a bar chart turns a number into a length. Nothing
// here originates a value, and nothing is interpolated between engine runs.

// ─── layout (deterministic; mirrors the layered bands the engine already assigns) ──────────────
const NODE_W = 268;
const NODE_H = 152;
const GAP_X = 104;
const GAP_Y = 26;
const PAD = 56;
const GAP_SUB = 26;     // gap between wrapped sub-columns inside one layer band
const MAX_ROWS = 4;     // a layer taller than this wraps into another sub-column
const HEADER_H = 30; // room for the column label above each band

export interface SweepFrameNode {
  utilization: number | null;
  arrival_rps: number | null;
  saturated: boolean;
  status: NodeStatus;
}

export interface SweepFrame {
  load_rps: number;
  multiple: number;
  bottleneck_id: string | null;
  bottleneck_utilization: number | null;
  breakpoint_rps_safe: number | null;
  monthly_cost_cents: number;
  nodes: Record<string, SweepFrameNode>;
}

interface Placed {
  node: ArchMapNode;
  x: number;
  y: number;
  /** live values for the currently displayed engine run (design load, or a sweep frame) */
  utilization: number | null;
  arrival_rps: number | null;
  status: NodeStatus;
  isBottleneck: boolean;
}

const STATUS_HUE: Record<NodeStatus, string> = {
  ok: "var(--cv-green)",
  hot: "var(--cv-amber)",
  saturated: "var(--cv-red)",
};

const ZOOM_BTN =
  "rounded px-2.5 py-1 text-[11px] font-semibold transition-colors hover:bg-white/10 " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1";

const STATUS_WORD: Record<NodeStatus, string> = {
  ok: "room to spare",
  hot: "almost full",
  saturated: "over its limit — work piles up",
};

function fmtRps(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}k`;
  return n.toFixed(n < 10 ? 1 : 0);
}

function pct(u: number | null): string {
  return u === null || !Number.isFinite(u) ? "not computed" : `${Math.round(u * 100)}%`;
}

export interface ArchCanvasProps {
  arch: ArchMap;
  /** An engine sweep frame to display instead of the design-load numbers. */
  frame?: SweepFrame | null;
  /** Component the active chaos scenario targets — gets a marker so the cause is visible. */
  targetId?: string | null;
  /** Flow to spotlight; other wires recede. */
  activeFlowIndex?: number | null;
  /** Component currently open in the inspector. */
  selectedId?: string | null;
  onSelectNode?: (node: ArchMapNode) => void;
  /** Right-click a tier to change how many of it there are. The studio re-runs the ENGINE with the
   *  new count — nothing is patched in place, so the numbers that come back are a real simulation
   *  of the edited design. */
  onResizeNode?: (node: ArchMapNode, instances: number) => void;
  /** "Fix the whole design for me" — let the engine size every tier for today's load. */
  onAutosize?: () => void;
}

/** Where the right-click menu is open, if anywhere. */
type SizerState = { node: ArchMapNode; x: number; y: number } | null;

export function ArchCanvas({
  arch, frame = null, targetId = null, activeFlowIndex = null,
  selectedId = null, onSelectNode, onResizeNode, onAutosize,
}: ArchCanvasProps) {
  const reduced = useReducedMotion();
  const [sizer, setSizer] = useState<SizerState>(null);
  const shellRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [autoFit, setAutoFit] = useState(true);
  // Pan offset. A large design (20+ nodes) will not fit even at "Fit", and the header card sits
  // over the top-left of the canvas, so the view has to be movable.
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [panning, setPanning] = useState(false);

  // Dismiss the right-click menu the way every menu is dismissed. Attached once, at the document,
  // so clicking anywhere — canvas, rail, another card — closes it.
  useEffect(() => {
    if (!sizer) return;
    const close = () => setSizer(null);
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setSizer(null); };
    document.addEventListener("click", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("click", close); document.removeEventListener("keydown", esc); };
  }, [sizer]);
  const panStart = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const [showHeader, setShowHeader] = useState(true);

  // ── placement: one column per layer that actually holds nodes, in engine order ──
  const { placed, width, height, columns } = useMemo(() => {
    // One band per layer that actually holds nodes, in the engine's order. Within a band, nodes
    // wrap into sub-columns after MAX_ROWS — a 20-node design otherwise becomes one unreadable
    // vertical stack taller than any viewport.
    const used = arch.layers
      .filter((l) => arch.nodes.some((n) => n.layer === l.id))
      .sort((a, b) => a.order - b.order);

    const inLayer = new Map<string, ArchMapNode[]>();
    for (const l of used) inLayer.set(l.id, arch.nodes.filter((n) => n.layer === l.id));

    // Plain loop, not map-with-accumulator: the react-hooks/immutability rule (React Compiler)
    // rejects reassigning a variable from inside a callback that could outlive the render.
    const bands: { id: string; label: string; order: number; x: number; rows: number; bandWidth: number }[] = [];
    let cursor = PAD;
    for (const l of used) {
      const n = inLayer.get(l.id)!.length;
      const rows = Math.min(n, MAX_ROWS);
      const subCols = Math.max(1, Math.ceil(n / Math.max(1, rows)));
      const bandWidth = subCols * NODE_W + (subCols - 1) * GAP_SUB;
      bands.push({ id: l.id, label: l.label, order: l.order, x: cursor, rows, bandWidth });
      cursor = cursor + bandWidth + GAP_X;
    }
    const byLayer = new Map(bands.map((b) => [b.id, b]));

    const out: Placed[] = [];
    for (const l of used) {
      const band = byLayer.get(l.id)!;
      inLayer.get(l.id)!.forEach((node, i) => {
        const col = Math.floor(i / band.rows);
        const row = i % band.rows;
        const live = frame?.nodes?.[node.id];
        out.push({
          node,
          x: band.x + col * (NODE_W + GAP_SUB),
          y: PAD + HEADER_H + row * (NODE_H + GAP_Y),
          utilization: live ? live.utilization : node.utilization,
          arrival_rps: live ? live.arrival_rps : node.arrival_rps,
          status: live ? live.status : node.status,
          isBottleneck: frame ? frame.bottleneck_id === node.id : node.is_bottleneck,
        });
      });
    }

    const maxRows = Math.max(1, ...bands.map((b) => b.rows));
    return {
      placed: out,
      columns: bands,
      width: cursor - GAP_X + PAD,
      height: PAD * 2 + HEADER_H + maxRows * NODE_H + Math.max(0, maxRows - 1) * GAP_Y,
    };
  }, [arch, frame]);

  const byId = useMemo(() => new Map(placed.map((p) => [p.node.id, p])), [placed]);

  // ── wires: consecutive pairs from every engine flow, deduped, keeping flow identity ──
  const wires = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; from: Placed; to: Placed; color: string; flowIndex: number; d: string }[] = [];
    arch.flows.forEach((flow, flowIndex) => {
      for (let i = 0; i + 1 < flow.steps.length; i++) {
        const a = byId.get(flow.steps[i].component_id);
        const b = byId.get(flow.steps[i + 1].component_id);
        if (!a || !b || a === b) continue;
        const key = `${a.node.id}->${b.node.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const x1 = a.x + NODE_W;
        const y1 = a.y + NODE_H / 2;
        const x2 = b.x;
        const y2 = b.y + NODE_H / 2;
        const bend = Math.max(38, (x2 - x1) * 0.42);
        out.push({
          id: key,
          from: a,
          to: b,
          color: flow.color,
          flowIndex,
          d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`,
        });
      }
    });
    return out;
  }, [arch.flows, byId]);

  const systemRps = frame?.load_rps ?? arch.meta.offered_load_rps ?? 0;

  // ── fit-to-container. Recomputed on resize while autoFit is on. ──
  const fit = useCallback(() => {
    const el = shellRef.current;
    if (!el) return;
    const s = Math.min(el.clientWidth / width, el.clientHeight / height, 1.35);
    setScale(Number.isFinite(s) && s > 0 ? s : 1);
    setOffset({ x: 0, y: 0 });
  }, [width, height]);

  useLayoutEffect(() => {
    if (!autoFit) return;
    fit();
    const el = shellRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [autoFit, fit]);

  const zoom = (delta: number) => {
    setAutoFit(false);
    setScale((s) => Math.min(2.2, Math.max(0.3, s + delta)));
  };

  // Drag the background to pan. Pointer events (not mouse) so trackpad and pen work; the guard
  // keeps a drag that started on a node card from stealing that card's click.
  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button,input,a")) return;
    setAutoFit(false);
    setPanning(true);
    panStart.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const start = panStart.current;
    if (!panning || !start) return;
    setOffset({ x: start.ox + (e.clientX - start.x), y: start.oy + (e.clientY - start.y) });
  };
  const endPan = (e: React.PointerEvent) => {
    if (!panning) return;
    setPanning(false);
    panStart.current = null;
    (e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId);
  };

  return (
    <div
      ref={shellRef}
      className="canvas-glass relative h-full w-full overflow-hidden"
      style={{
        background: "var(--cv-paper)",
        color: "var(--cv-ink)",
        cursor: panning ? "grabbing" : "grab",
        touchAction: "none",
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPan}
      onPointerCancel={endPan}
    >
      {/* dot grid — decoration only */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "radial-gradient(circle, rgba(150,170,235,0.16) 1px, transparent 1px)",
          backgroundSize: "26px 26px",
        }}
      />

      <div
        className="absolute left-1/2 top-1/2 origin-center"
        style={{
          width,
          height,
          transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px)) scale(${scale})`,
          transition: reduced || panning ? "none" : "transform 260ms cubic-bezier(.2,.7,.3,1)",
        }}
      >
        {/* ── wires + particles ── */}
        <svg
          width={width}
          height={height}
          className="absolute inset-0"
          style={{ overflow: "visible" }}
          aria-hidden
        >
          <defs>
            {wires.map((w) => (
              <path key={`p-${w.id}`} id={`wire-${w.id}`} d={w.d} fill="none" />
            ))}
          </defs>
          {wires.map((w) => {
            const muted = activeFlowIndex !== null && w.flowIndex !== activeFlowIndex;
            // Particle COUNT encodes the engine's arrival_rps at the downstream component,
            // relative to system load — a visual encoding of an engine number, like a bar length.
            // It originates nothing: with no engine value, no particles are drawn.
            const rps = w.to.arrival_rps;
            const share = systemRps > 0 && rps !== null ? Math.min(1, rps / systemRps) : 0;
            const count = rps === null ? 0 : Math.max(1, Math.min(5, Math.round(share * 5)));
            // SPEED ENCODES CONGESTION, and it used to encode the opposite. `dur` got SHORTER as a
            // wire got busier, so the fuller a tier became the faster its traffic appeared to fly
            // into it — the reverse of what happens to a real request. Requests now slow as the
            // component they are heading into fills up: gentle to ~70%, then biting hard, mirroring
            // the 1/(1-rho) the engine itself computes. Past 100% they crawl, because the queue is
            // growing faster than it drains.
            const util = w.to.utilization ?? 0;
            const drag = util >= 1 ? 14 : 1 / Math.max(0.08, Math.pow(1 - util, 1.6));
            const dur = Math.min(24, (2.6 - Math.min(1.4, share * 1.4)) * drag);
            // And colour says it too, for anyone who does not read motion.
            const flowTint =
              util >= 1 ? "var(--cv-red)" : util >= 0.85 ? "var(--cv-amber)" : w.color;
            return (
              <g key={w.id} opacity={muted ? 0.18 : 1}>
                <path
                  d={w.d}
                  fill="none"
                  stroke="var(--cv-steel)"
                  strokeWidth={1.5}
                  strokeDasharray="4 6"
                  opacity={0.5}
                />
                {!reduced &&
                  Array.from({ length: count }).map((_, i) => (
                    <circle key={i} r={util >= 1 ? 4 : 3} fill={flowTint}>
                      <animateMotion
                        dur={`${dur}s`}
                        begin={`${(i * dur) / Math.max(1, count)}s`}
                        repeatCount="indefinite"
                        rotate="auto"
                      >
                        <mpath href={`#wire-${w.id}`} />
                      </animateMotion>
                    </circle>
                  ))}
                {reduced && count > 0 && (
                  // Static equivalent: a solid segment carries "this wire is busy" without motion.
                  <path d={w.d} fill="none" stroke={flowTint} strokeWidth={util >= 1 ? 3 : 2} opacity={0.6} />
                )}
              </g>
            );
          })}
        </svg>

        {/* ── column labels ── */}
        {columns.map((c) => (
          <div
            key={c.id}
            className="absolute text-[11px] font-semibold uppercase tracking-[0.18em]"
            style={{ left: c.x, top: PAD, width: c.bandWidth, color: "var(--cv-muted)" }}
          >
            {c.label}
          </div>
        ))}

        {/* ── node cards ── */}
        {placed.map((p) => {
          const hue = STATUS_HUE[p.status];
          const isTarget = targetId === p.node.id;
          const barPct = p.utilization === null || !Number.isFinite(p.utilization)
            ? 0
            : Math.max(2, Math.min(100, p.utilization * 100));
          return (
            <button
              key={p.node.id}
              type="button"
              onClick={() => onSelectNode?.(p.node)}
              onContextMenu={(e) => {
                // Only where it means something: the users are not a machine you can add more of.
                if (p.node.instances == null || !onResizeNode) return;
                e.preventDefault();
                setSizer({ node: p.node, x: e.clientX, y: e.clientY });
              }}
              aria-pressed={selectedId === p.node.id}
              className="cv-panel absolute overflow-hidden text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              style={{
                left: p.x,
                top: p.y,
                width: NODE_W,
                height: NODE_H,
                borderLeft: `3px solid ${hue}`,
                outlineColor: "var(--cv-blue)",
                boxShadow: selectedId === p.node.id
                  ? "0 0 0 2px var(--cv-blue), 0 12px 40px rgba(0,0,0,.5)"
                  : p.isBottleneck
                    ? `0 0 0 1px ${hue}, 0 12px 40px rgba(0,0,0,.5)`
                    : isTarget
                      ? "0 0 0 1px var(--cv-blue), 0 12px 40px rgba(0,0,0,.5)"
                      : undefined,
                transition: reduced ? "none" : "box-shadow 200ms ease",
              }}
            >
              <div className="flex h-full flex-col p-3">
                <div className="flex items-start gap-2">
                  <span aria-hidden className="text-[15px] leading-none">{p.node.icon}</span>
                  <span className="min-w-0 flex-1 line-clamp-2 text-[13px] font-semibold leading-tight" style={{ color: "var(--cv-ink)" }}>
                    {p.node.name}
                  </span>
                  {p.node.is_spof && (
                    <span
                      className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                      style={{ background: "rgba(251,191,36,.16)", color: "var(--cv-amber)" }}
                      title="Only one of these, with no backup — if it fails, everything that depends on it goes down with it. Engineers call this a single point of failure (SPOF)."
                    >
                      NO BACKUP
                    </span>
                  )}
                </div>

                <p className="mt-1 line-clamp-2 flex-1 text-[11px] leading-snug" style={{ color: "var(--cv-muted)" }}>
                  {p.node.role}
                </p>

                <div className="mt-1 flex items-baseline justify-between text-[11px] tabular-nums" style={{ color: "var(--cv-muted)" }}>
                  <span style={{ color: "var(--cv-ink)" }}>{fmtRps(p.arrival_rps)} requests/sec</span>
                  <span>{Number.isFinite(p.utilization) ? `${pct(p.utilization)} full` : pct(p.utilization)}</span>
                </div>
                <div className="mt-1 h-[3px] w-full overflow-hidden rounded-full" style={{ background: "rgba(150,170,235,.16)" }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${barPct}%`,
                      background: hue,
                      transition: reduced ? "none" : "width 420ms cubic-bezier(.2,.7,.3,1)",
                    }}
                  />
                </div>
                <div className="mt-1.5 truncate text-[10.5px] font-semibold" style={{ color: hue }}>
                  {p.status === "ok" ? "\u2713 " : "\u25B2 "}
                  {STATUS_WORD[p.status]}
                  {p.isBottleneck && <span style={{ color: "var(--cv-muted)" }}> · runs out first</span>}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* ── the design's own header: what this is, and how far to trust it ── */}
      <div className="cv-panel absolute left-4 top-4 max-w-[380px] p-3">
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 text-[14px] font-semibold leading-tight" style={{ color: "var(--cv-ink)" }}>
            {arch.meta.title}
          </p>
          <button
            onClick={() => setShowHeader((v) => !v)}
            aria-expanded={showHeader}
            aria-label={showHeader ? "Collapse design summary" : "Expand design summary"}
            className="shrink-0 rounded px-1.5 text-[11px] transition-colors hover:bg-white/10 focus-visible:outline focus-visible:outline-2"
            style={{ color: "var(--cv-muted)", outlineColor: "var(--cv-blue)" }}
          >
            {showHeader ? "▾" : "▸"}
          </button>
        </div>
        {showHeader && (<>
        <p className="mt-1 text-[10.5px] leading-snug" style={{ color: "var(--cv-muted)" }}>
          Architecture map · every number here comes from the simulator, never from the AI — and only holds at the traffic level shown
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="rounded px-1.5 py-0.5 text-[9.5px] font-semibold" style={{ background: "rgba(150,170,235,.16)", color: "var(--cv-muted)" }}>
            {arch.meta.accuracy_level} · a ballpark, not checked against a real system
          </span>
          <span className="rounded px-1.5 py-0.5 text-[9.5px] font-semibold tabular-nums" style={{ background: "rgba(150,170,235,.16)", color: "var(--cv-muted)" }}>
            {fmtRps(frame?.load_rps ?? arch.meta.offered_load_rps)} requests/sec coming in
          </span>
          {arch.meta.high_stakes && (
            <span className="rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wider" style={{ background: "rgba(251,191,36,.16)", color: "var(--cv-amber)" }}>
              high stakes — have an expert review this before you build
            </span>
          )}
        </div>
        <p className="mt-1.5 text-[9.5px] leading-snug" style={{ color: "var(--cv-amber)" }}>
          how far to trust these numbers: {arch.meta.confidence}
        </p>
        </>)}
      </div>

      {/* ── zoom controls ── */}
      <div className="absolute bottom-4 right-4 flex items-center gap-1 rounded-lg p-1" style={{ background: "var(--cv-panel)", border: "1px solid var(--cv-line)" }}>
        {/* Written out rather than mapped over a config array: the react-hooks/refs rule treats a
            closure array built during render as reading the ref at render time. */}
        <button
          onClick={() => { setAutoFit(true); fit(); }}
          className={ZOOM_BTN}
          style={{ color: "var(--cv-ink)", outlineColor: "var(--cv-blue)" }}
        >
          Fit to screen
        </button>
        <button
          onClick={() => zoom(-0.15)}
          aria-label="Zoom out"
          className={ZOOM_BTN}
          style={{ color: "var(--cv-ink)", outlineColor: "var(--cv-blue)" }}
        >
          −
        </button>
        <button
          onClick={() => zoom(0.15)}
          aria-label="Zoom in"
          className={ZOOM_BTN}
          style={{ color: "var(--cv-ink)", outlineColor: "var(--cv-blue)" }}
        >
          +
        </button>
        <span className="px-1.5 text-[10px] tabular-nums" style={{ color: "var(--cv-muted)" }}>
          zoom {Math.round(scale * 100)}%
        </span>
      </div>
      {/* RIGHT-CLICK SIZER. Fixed-position so it is never clipped by the canvas viewport, and it
          sits outside the transformed layer so panning or zooming cannot drag it off the pointer. */}
      {sizer && (
        <div
          role="menu"
          aria-label={`Resize ${sizer.node.name}`}
          onClick={(e) => e.stopPropagation()}
          className="cv-panel fixed z-50 w-64 p-2 shadow-2xl"
          style={{
            left: Math.min(sizer.x, (typeof window !== "undefined" ? window.innerWidth : 1200) - 270),
            top: Math.min(sizer.y, (typeof window !== "undefined" ? window.innerHeight : 800) - 210),
          }}
        >
          <p className="px-2 text-[12.5px] font-semibold" style={{ color: "var(--cv-ink)" }}>
            {sizer.node.name}
          </p>
          <p className="px-2 pb-2 mb-1.5 text-[11px] border-b" style={{ color: "var(--cv-muted)", borderColor: "var(--cv-line)" }}>
            running {sizer.node.instances}
            {sizer.node.utilization != null && ` — ${Math.round(sizer.node.utilization * 100)}% full`}
          </p>
          {([
            ["Add one more", 1, "see what it costs and what it fixes"],
            ["Add five", 5, "for a tier that is badly under-provisioned"],
            ["Remove one", -1, "is this over-provisioned?"],
          ] as const).map(([label, delta, hint]) => {
            const next = (sizer.node.instances ?? 1) + delta;
            // One is the floor: removing the last instance is a component that does not exist,
            // which is hard_node_failure — explicitly UNMODELLED by this engine.
            const blocked = next < 1;
            return (
              <button
                key={label}
                type="button"
                disabled={blocked}
                title={blocked ? "Only one left — removing it is a total failure, which this engine does not model." : undefined}
                onClick={() => { setSizer(null); onResizeNode?.(sizer.node, next); }}
                className="block w-full text-left px-2 py-1.5 rounded text-[12.5px] disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[var(--cv-panel)]"
                style={{ color: "var(--cv-ink)" }}
              >
                {label}
                <span className="block text-[10.5px]" style={{ color: "var(--cv-muted)" }}>{hint}</span>
              </button>
            );
          })}
          {onAutosize && (
            <button
              type="button"
              onClick={() => { setSizer(null); onAutosize(); }}
              className="block w-full text-left px-2 py-1.5 mt-1 rounded text-[12.5px] border-t hover:bg-[var(--cv-panel)]"
              style={{ color: "var(--cv-blue)", borderColor: "var(--cv-line)" }}
            >
              Fix the whole design for me
              <span className="block text-[10.5px]" style={{ color: "var(--cv-muted)" }}>
                size every tier for today&apos;s load, then re-check it
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
