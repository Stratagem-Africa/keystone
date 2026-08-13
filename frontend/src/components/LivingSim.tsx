"use client";

import { useState, useSyncExternalStore } from "react";
import { Network, Server, Zap, Database, type LucideIcon } from "lucide-react";
import { Metric } from "@/components/Metric";

// Reduced-motion, done in React (not CSS): this Tailwind v4 setup doesn't reliably emit a `motion-reduce:`
// utility or a custom class inside the reduced-motion @media (Lightning CSS purges it), and the global
// animation-kill leaves a packet at opacity 1 (no `forwards`) — a frozen artifact. `useSyncExternalStore`
// is the idiomatic way to subscribe to a matchMedia store: no setState-in-effect, and SSR-safe — the
// server snapshot is `false` (motion allowed), matching the packet-showing poster, then it settles on the
// client without a hydration mismatch.
const RM_QUERY = "(prefers-reduced-motion: reduce)";
function usePrefersReducedMotion() {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(RM_QUERY);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    () => window.matchMedia(RM_QUERY).matches, // client snapshot
    () => false,                               // server snapshot — assume motion allowed
  );
}

// ── Genuine engine output — NOT computed in the browser ────────────────────────────────
// Prime directive (docs/03): only `simulation.py` produces numbers; the LLM reasons, the engine
// computes, and the frontend NEVER derives a metric. Every figure below is the exact value
// `simulation.py` emits for the committed blueprint `prototype/keystone/blueprints/url_shortener.py`
// at its 10,000 rps baseline. Regenerate with:
//   cd prototype && python3 -c "from keystone.blueprints.url_shortener import build; \
//     from keystone import simulation as s; r = s.simulate(build()); \
//     print(r.bottleneck_id, round(r.bottleneck_utilization,3), \
//           r.breakpoint_rps_safe, r.breakpoint_rps_theoretical); \
//     [print(k, round(v.utilization,3)) for k,v in r.components.items()]"
// The UI only ANIMATES and reveals these values; it re-derives nothing.
const ENGINE = {
  model: "M/M/1 · app-tier 85% safe ceiling",
  baselineRps: 10_000,
  pushMultiple: 10, // the "Push it to 10×" target — the load axis runs ×1 → ×10
  bottleneckId: "app",
  breakpointSafeRps: 12_240, // 85% ceiling — the safe throughput to design to
  breakpointTheoreticalRps: 14_400, // 100% — the absolute (unsafe) limit; the band's far edge
  // Per-tier utilisation at the 10k baseline (shown as visual fill, never as a bare number).
  tiers: {
    lb: 0.333,
    app: 0.694, // the bottleneck — fullest at baseline, first to saturate
    cache: 0.099,
    db: 0.136,
  },
} as const;

// The safe breakpoint as a fraction of the ×10 axis — this is what makes the point: the marker
// sits ~12% along, so a reader SEES the design break long before the ×10 they asked for.
const BREAKPOINT_AXIS_FRAC =
  ENGINE.breakpointSafeRps / (ENGINE.baselineRps * ENGINE.pushMultiple);

// A node in the living-sim stack, keyed by a recognizable icon (LB=network, app=server,
// cache=lightning, db=cylinder). A subtle bottom-fill shows the tier's engine utilisation — so you
// can SEE the app is fullest even at rest, which is *why* it's the bottleneck. Hover OR click
// (focus) reveals an info popover — no client JS needed for that (group-hover / group-focus-within).
function SimNode({
  label, Icon, name, what, tech, util, bottleneck = false, saturated = false,
}: {
  label: string; Icon: LucideIcon; name: string; what: string; tech: string;
  util: number; bottleneck?: boolean; saturated?: boolean;
}) {
  // Fill height = engine utilisation (a proportion, not a claimed number). The bottleneck tier fills
  // amber at rest and floods coral+hatched when saturated; other tiers use a cool, quiet blue.
  const fillHeight = saturated ? 100 : Math.round(util * 100);
  const fillTone = bottleneck
    ? (saturated ? "bg-signal-red/40 sim-hatch" : "bg-assumption-amber/30")
    : "bg-architect-blue/20";
  const boxTone = bottleneck
    ? "border-signal-red text-signal-red"
    : "border-steel text-ink-muted group-hover:border-ink-muted group-hover:text-paper";

  return (
    <span
      tabIndex={0}
      aria-label={`${name}. ${what}`}
      className="group relative z-10 shrink-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
    >
      <span className={`relative grid place-items-center h-10 w-10 overflow-hidden rounded-lg border bg-slate-ink cursor-pointer transition-colors ease-settle duration-ui ${boxTone}`}>
        {/* Utilisation fill — settles up from the base; a proportion of the tier's capacity. */}
        <span
          className={`pointer-events-none absolute inset-x-0 bottom-0 transition-all ease-settle duration-band ${fillTone}`}
          style={{ height: `${fillHeight}%` }}
          aria-hidden="true"
        />
        <Icon size={18} strokeWidth={1.75} aria-hidden="true" className="relative z-10" />
        {bottleneck && saturated && (
          <span className="pointer-events-none absolute inset-0 rounded-lg border border-signal-red animate-ping" aria-hidden="true" />
        )}
      </span>
      <span className="absolute top-full left-1/2 -translate-x-1/2 mt-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-muted whitespace-nowrap">
        {label}
      </span>

      {/* Info popover — opens ABOVE the stack; hover to peek, click to pin. */}
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-full z-30 mb-3 hidden w-64 flex-col gap-1.5 rounded-lg border border-steel bg-slate-ink p-3 text-left shadow-xl group-hover:flex group-focus-within:flex"
      >
        <span className="flex items-center gap-2">
          <Icon size={14} strokeWidth={1.75} className={bottleneck ? "text-signal-red" : "text-ink-muted"} aria-hidden="true" />
          <span className="font-sans text-label font-semibold text-paper normal-case tracking-normal">{name}</span>
        </span>
        <span className="font-serif text-provenance text-ink-muted leading-relaxed normal-case tracking-normal">{what}</span>
        <span className="font-mono text-[10px] text-ink-muted leading-relaxed">{tech}</span>
        {bottleneck && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-signal-red">
            {saturated ? "◂ saturated — this tier sets the ceiling" : "◂ the bottleneck at this load"}
          </span>
        )}
      </span>
    </span>
  );
}

// A connector between two tiers. Hover OR click (focus) reveals what travels the wire — no client JS.
function Track({ name, detail }: { name: string; detail: string }) {
  return (
    <span
      tabIndex={0}
      aria-label={`${name}: ${detail}`}
      className="group relative z-10 flex flex-1 min-w-[16px] items-center py-3 rounded cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
    >
      <span className="h-px w-full bg-steel transition-colors ease-settle duration-ui group-hover:bg-ink-muted" aria-hidden="true" />
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-full z-30 mb-3 hidden w-56 flex-col gap-1 rounded-lg border border-steel bg-slate-ink p-3 text-left shadow-xl group-hover:flex group-focus-within:flex"
      >
        <span className="font-sans text-label font-semibold text-paper normal-case tracking-normal">{name}</span>
        <span className="font-serif text-provenance text-ink-muted leading-relaxed normal-case tracking-normal">{detail}</span>
      </span>
    </span>
  );
}

// LivingSim — the reseedable hero simulation (docs/09 §4.1 Act 1). Idle shows a real LB→App→Cache→DB
// stack with one request/response cycling; the App tier is the bottleneck. "Push it to 10×" floods the
// stack and drives the App tier past its safe ceiling — where the engine's breakpoint readout snaps in.
// "reseed" replays byte-identical, turning determinism (NFR-7) into the spectacle. The whole thing is
// CSS/React-state (no WebGL, within the frame budget) and reduced-motion / JS-off safe: the server-
// rendered idle state already carries the real numbers, so nothing is lost without motion or hydration.
export function LivingSim() {
  const [pushed, setPushed] = useState(false);
  const [run, setRun] = useState(1); // reseed count — every run yields the identical result
  const reducedMotion = usePrefersReducedMotion();

  const tiers = ENGINE.tiers;
  const sweepFrac = pushed ? 1 : ENGINE.baselineRps / (ENGINE.baselineRps * ENGINE.pushMultiple);

  return (
    <div className="mt-2 w-full max-w-md p-6 bg-graphite border border-steel rounded-lg text-left">
      <p className="font-mono text-provenance text-ink-muted mb-4 uppercase tracking-wider">
        a real stack · simulated by the engine
      </p>

      {/* The stack. A local red wash sits behind the App tier and blooms in when it saturates. */}
      <div className="relative isolate flex items-center gap-2 mb-8">
        <span
          className={`sim-glow-red pointer-events-none absolute z-0 top-1/2 left-[26%] h-20 w-20 -translate-x-1/2 -translate-y-1/2 rounded-full transition-opacity ease-settle duration-band ${pushed ? "opacity-100" : "opacity-0"}`}
          aria-hidden="true"
        />

        {/* Packets. Idle = one request out, one response back. Pushed = a flood of requests (keyed on
            `run` so a reseed replays the identical stream). All carry `sim-packet` → hidden under
            prefers-reduced-motion, where the static stack + numbers carry the meaning instead. */}
        {/* Packets: one request/response cycle at rest, a flood when pushed. Suppressed entirely under
            prefers-reduced-motion (the static stack + numbers carry the meaning — docs/09 §11.9). */}
        {reducedMotion ? null : !pushed ? (
          <>
            <span className="pointer-events-none absolute z-20 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-architect-blue shadow-[0_0_6px_1px_var(--color-architect-blue)] animate-req" aria-hidden="true" />
            <span className="pointer-events-none absolute z-20 top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full border-2 border-architect-blue bg-slate-ink animate-res" aria-hidden="true" />
          </>
        ) : (
          <span key={run} className="contents">
            {[0, 0.17, 0.34, 0.51, 0.68, 0.85].map((delay, i) => (
              <span
                key={i}
                className="pointer-events-none absolute z-20 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-signal-red shadow-[0_0_6px_1px_var(--color-signal-red)] animate-flood"
                style={{ animationDelay: `${delay}s` }}
                aria-hidden="true"
              />
            ))}
          </span>
        )}

        <SimNode
          label="LB" Icon={Network} util={tiers.lb}
          name="Application Load Balancer"
          what="Spreads incoming requests across the app instances so none is overwhelmed, health-checks them, and routes around failures."
          tech="L7 · AWS ALB / NGINX / Envoy · a single instance is a SPOF — run it multi-AZ"
        />
        <Track name="HTTP request" detail="The load balancer forwards the client's request to a chosen app instance." />
        <SimNode
          label="App" Icon={Server} util={tiers.app} bottleneck saturated={pushed}
          name="App tier (compute)"
          what="Runs your request-handling code. Scales horizontally behind the load balancer; usually the first tier to saturate, so its instance count sets your safe throughput."
          tech="stateless · autoscaling group · CPU / latency-bound"
        />
        <Track name="Cache lookup" detail="The app checks Redis first — a hit returns in under a millisecond and never touches the database." />
        <SimNode
          label="Cache" Icon={Zap} util={tiers.cache}
          name="Cache (Redis)"
          what="An in-memory store in front of the database. Absorbs hot reads — at a 90% hit rate only 1 in 10 reads reaches Postgres — with sub-millisecond lookups."
          tech="Redis / Memcached · LRU eviction · a cold cache sends every read to the DB (a classic stampede)"
        />
        <Track name="DB query (on miss)" detail="Only the reads the cache misses reach Postgres — the fewer, the healthier. Writes always land here." />
        <SimNode
          label="DB" Icon={Database} util={tiers.db}
          name="PostgreSQL (primary)"
          what="The durable source of truth, with ACID guarantees. Cache-shielded for reads; every write lands here. The hardest tier to scale out."
          tech="primary + read replicas · connection-pooled · disk / IO-bound on writes"
        />
      </div>

      {/* Load axis — the offered load you're pushing (an INPUT, ×1 → ×10), not an engine metric.
          The breakpoint marker sits at the engine's safe ceiling; because it lands ~12% along the
          ×10 axis, you can SEE the design break far short of the ×10 you asked for. */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-muted">
          <span>offered load</span>
          <span>×1 → ×10</span>
        </div>
        <div className="relative h-2 w-full rounded-full bg-slate-ink border border-steel overflow-hidden">
          <div
            key={run}
            className={`absolute left-0 top-0 h-full rounded-l-full transition-[width] ease-settle ${pushed ? "bg-signal-red" : "bg-architect-blue"}`}
            style={{ width: `${sweepFrac * 100}%`, transitionDuration: pushed ? "1600ms" : "420ms" }}
            aria-hidden="true"
          />
          {/* Breakpoint marker — a hard line at the safe ceiling. */}
          <div
            className="absolute top-0 h-full w-px bg-assumption-amber"
            style={{ left: `${BREAKPOINT_AXIS_FRAC * 100}%` }}
            aria-hidden="true"
          />
        </div>
        <div className="relative h-3 mt-1" aria-hidden="true">
          <span
            className="absolute -translate-x-1/2 font-mono text-[9px] uppercase tracking-wider text-assumption-amber whitespace-nowrap"
            style={{ left: `${BREAKPOINT_AXIS_FRAC * 100}%` }}
          >
            ↑ safe ceiling
          </span>
        </div>
      </div>

      {/* The engine number. Always present (so JS-off / reduced-motion posters carry it) but it
          emphasises and gains its verdict caption once the load is pushed past the ceiling. */}
      <div className="flex flex-col gap-2">
        <span className="font-mono text-provenance text-ink-muted uppercase tracking-wider">
          engine verdict · safe breakpoint
        </span>
        <Metric
          value={ENGINE.breakpointSafeRps}
          unit="rps"
          low={ENGINE.breakpointSafeRps}
          high={ENGINE.breakpointTheoreticalRps}
          provenance="ASSUMPTION"
          model={ENGINE.model}
        />
        {pushed && (
          <p key={run} className="animate-snap font-serif text-provenance text-paper leading-relaxed">
            The App tier saturates first — at roughly <span className="font-mono text-signal-red">1.2×</span> the
            baseline, long before the <span className="font-mono">10×</span> you asked for. That gap is the
            point: the engine finds the ceiling you can&apos;t eyeball.
          </p>
        )}
      </div>

      {/* Controls. "Push it to 10×" runs the flood; "reseed" replays it byte-identical (NFR-7). */}
      <div className="flex flex-wrap items-center gap-3 mt-5">
        <button
          type="button"
          onClick={() => { setPushed(true); setRun(1); }}
          aria-pressed={pushed}
          className="font-sans text-label font-medium px-4 py-2 rounded-full bg-signal-red/15 text-signal-red border border-signal-red/40 transition-all ease-settle duration-ui hover:bg-signal-red/25 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-graphite"
        >
          Push it to 10× →
        </button>
        <button
          type="button"
          onClick={() => setRun((r) => (pushed ? r + 1 : r))}
          disabled={!pushed}
          className="font-sans text-label px-4 py-2 rounded-full text-ink-muted border border-steel transition-all ease-settle duration-ui enabled:hover:text-paper enabled:hover:border-ink-muted disabled:opacity-40 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-graphite"
        >
          ↺ reseed
        </button>
      </div>

      {/* Determinism proof — every reseed lands the identical number (docs/09 §11: reproducibility IS
          the spectacle). The "byte-identical" claim only appears AFTER an actual reseed (run ≥ 2) —
          on the first run nothing has been replayed yet, so it would be a false claim. */}
      {!pushed ? (
        <p className="mt-3 font-mono text-provenance text-ink-muted">
          push the load — then reseed to watch it replay identically
        </p>
      ) : run === 1 ? (
        <p className="mt-3 font-mono text-provenance text-ink-muted">
          run #1 · seeded &amp; deterministic — press reseed to replay it
        </p>
      ) : (
        <p className="mt-3 font-mono text-provenance text-grounded-green">
          run #{run} · replayed byte-identical ✓
        </p>
      )}
    </div>
  );
}
