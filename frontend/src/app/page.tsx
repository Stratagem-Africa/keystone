import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Metric } from "@/components/Metric";
import { Network, Server, Zap, Database, type LucideIcon } from "lucide-react";

// A node in the living-sim stack, keyed by a recognizable icon (LB=network, app=server, cache=lightning,
// db=cylinder). Fixed 40px box so all connectors stay equal width → every packet moves at the same speed.
// The bottleneck pulses coral — "this is where it saturates" (docs/09 §4.1 Act 1). Hover OR click (focus)
// reveals an info popover — no client JS (group-hover / group-focus-within, like the Metric x-ray). The
// label floats absolutely so it never shifts the row alignment.
function SimNode({
  label, Icon, name, what, tech, bottleneck = false,
}: {
  label: string; Icon: LucideIcon; name: string; what: string; tech: string; bottleneck?: boolean;
}) {
  return (
    <span
      tabIndex={0}
      aria-label={`${name}. ${what}`}
      className="group relative z-10 shrink-0 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue"
    >
      <span className={`relative grid place-items-center h-10 w-10 rounded-lg border bg-slate-ink cursor-pointer transition-colors ease-settle duration-ui ${bottleneck ? "border-signal-red text-signal-red" : "border-steel text-ink-muted group-hover:border-ink-muted group-hover:text-paper"}`}>
        <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
        {bottleneck && (
          <span className="pointer-events-none absolute inset-0 rounded-lg border border-signal-red animate-ping" aria-hidden="true" />
        )}
      </span>
      <span className="absolute top-full left-1/2 -translate-x-1/2 mt-1.5 font-mono text-[10px] uppercase tracking-wider text-ink-muted whitespace-nowrap">
        {label}
      </span>

      {/* Info popover — opens ABOVE the stack (clear of the metric below); hover to peek, click to pin. */}
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
          <span className="font-mono text-[10px] uppercase tracking-wider text-signal-red">◂ the bottleneck at this load</span>
        )}
      </span>
    </span>
  );
}

// A connector between two tiers. Hover OR click (focus) reveals what travels the wire — no client JS.
// The request/response packets are rendered once at the row level (below), so it reads as ONE request
// moving through, not one packet per wire. A tall transparent hit-area makes the thin line easy to hover.
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

export default function Home() {
  return (
    <>
      <Nav />

      {/* Hero — slate-ink "instrument panel". Competence BEFORE confession (docs/09 §4.1 Act 1,
          §11.5): the headline + a number settling through its band land first; the honest caveats
          come later (the flaws section, below the fold), so honesty reads as mastery, not weakness. */}
      <section className="relative flex-1 flex flex-col items-center justify-center bg-slate-ink text-paper px-6 py-24 text-center">
        {/* Faint instrument substrate — the living-sim's grid, static (docs/09 §4.1 Act 1). */}
        <div className="pointer-events-none absolute inset-0 hero-substrate" aria-hidden="true" />
        {/* Content settles in on load (reduced-motion path stills it to the final state). */}
        <div className="relative z-10 flex flex-col items-center gap-8 animate-hero-rise">
        {/* Primary headline — Display scale, grotesque signals chrome/UI (docs/09 §2.5) */}
        <h1 className="font-sans text-display font-semibold tracking-tight max-w-3xl">
          Show your work.
        </h1>

        {/* Sub-copy — serif signals model-reasoned prose. Competence framing. */}
        <p className="font-serif text-body max-w-[52ch]">
          A grounded consensus of AI architects designs your system, justifies every
          decision, and validates it with a deterministic engine.
        </p>

        {/* Living sim (docs/09 §4.1 Act 1) — a real LB→App→Cache→DB stack with requests flowing
            through it; the App tier pulses coral as the bottleneck. CSS-only (no WebGL),
            reduced-motion-safe. The number below is the ENGINE's, inside its band — hover to x-ray. */}
        <div className="mt-2 w-full max-w-md p-6 bg-graphite border border-steel rounded-lg text-left">
          <p className="font-mono text-provenance text-ink-muted mb-4 uppercase tracking-wider">
            a real stack · simulated
          </p>
          <div className="relative isolate flex items-center gap-2 mb-8">
            {/* ONE request glides across the whole chain (above the stack, always visible); the response
                returns behind it, hollow. Rendered once here = a single request/response cycle. */}
            <span className="pointer-events-none absolute z-20 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-architect-blue shadow-[0_0_6px_1px_var(--color-architect-blue)] animate-req" aria-hidden="true" />
            <span className="pointer-events-none absolute z-20 top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full border-2 border-architect-blue bg-slate-ink animate-res" aria-hidden="true" />
            <SimNode
              label="LB" Icon={Network}
              name="Application Load Balancer"
              what="Spreads incoming requests across the app instances so none is overwhelmed, health-checks them, and routes around failures."
              tech="L7 · AWS ALB / NGINX / Envoy · a single instance is a SPOF — run it multi-AZ"
            />
            <Track name="HTTP request" detail="The load balancer forwards the client's request to a chosen app instance." />
            <SimNode
              label="App" Icon={Server} bottleneck
              name="App tier (compute)"
              what="Runs your request-handling code. Scales horizontally behind the load balancer; usually the first tier to saturate, so its instance count sets your safe throughput."
              tech="stateless · autoscaling group · CPU / latency-bound"
            />
            <Track name="Cache lookup" detail="The app checks Redis first — a hit returns in under a millisecond and never touches the database." />
            <SimNode
              label="Cache" Icon={Zap}
              name="Cache (Redis)"
              what="An in-memory store in front of the database. Absorbs hot reads — at a 90% hit rate only 1 in 10 reads reaches Postgres — with sub-millisecond lookups."
              tech="Redis / Memcached · LRU eviction · a cold cache sends every read to the DB (a classic stampede)"
            />
            <Track name="DB query (on miss)" detail="Only the reads the cache misses reach Postgres — the fewer, the healthier. Writes always land here." />
            <SimNode
              label="DB" Icon={Database}
              name="PostgreSQL (primary)"
              what="The durable source of truth, with ACID guarantees. Cache-shielded for reads; every write lands here. The hardest tier to scale out."
              tech="primary + read replicas · connection-pooled · disk / IO-bound on writes"
            />
          </div>
          {/* Legend for the two packets so filled-vs-hollow reads clearly. */}
          <div className="flex items-center gap-4 -mt-3 mb-4 font-mono text-provenance text-ink-muted">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-architect-blue" /> request →</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full border-2 border-architect-blue" /> ← response</span>
          </div>
          <Metric
            value={86}
            unit="ms"
            low={72}
            high={104}
            provenance="ASSUMPTION"
            model="M/M/1 sojourn — placeholder"
          />
          <p className="font-mono text-provenance text-ink-muted mt-3">
            hover the number to x-ray how it was made
          </p>
        </div>

        {/* Gentle scroll affordance — not a conversion CTA (that waits until after the flaws). */}
        <a
          href="#flaws"
          className="font-sans text-label text-architect-blue hover:text-paper transition-colors ease-settle duration-ui rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-ink"
        >
          See how — and where it&apos;s wrong ↓
        </a>

        {/* Stub honesty, demoted to a small note (docs/09 §11 stub-honesty, no longer the first line). */}
        <p className="font-mono text-provenance text-ink-muted/70">
          scaffold · no live data yet
        </p>
        </div>
      </section>

      {/* Reasoning → Computation seam — docs/09 §3.2 */}
      <section className="grid grid-cols-1 md:grid-cols-2">
        {/* Warm zone — serif, paper ground — model-reasoned prose */}
        <div className="bg-paper text-slate-ink px-8 py-12 flex flex-col gap-4">
          <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
            reasoning zone · model
          </p>
          <div className="w-8 h-px bg-mist" />
          {/* Serif = the model reasoned this. Bounded to a comfortable reading measure (docs/09 §8). */}
          <p className="font-serif text-body max-w-[60ch]">
            The council of AI architects deliberates on your system design,
            proposes ADRs, and records dissent. Serif typeface signals the source:
            a language model reasoned this — not the engine.
          </p>
          <p className="font-serif text-body text-ink-muted italic max-w-[60ch]">
            &ldquo;A cache here reduces read latency by avoiding repeated DB
            round-trips, at the cost of eventual consistency…&rdquo;
          </p>
        </div>

        {/* Cool zone — mono, slate-ink ground — engine-computed numbers */}
        <div className="bg-slate-ink text-paper px-8 py-12 flex flex-col gap-4">
          <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
            computation zone · engine
          </p>
          <div className="w-8 h-px bg-steel" />
          <p className="font-mono text-provenance text-ink-muted">
            parameters → engine → metric
          </p>
          {/* Mono = the engine computed these */}
          <div className="flex flex-col gap-6 mt-2">
            <Metric
              value={4200}
              unit="req/s"
              low={2800}
              high={6000}
              provenance="ASSUMPTION"
              model="placeholder"
            />
            <Metric
              value={94}
              unit="%"
              low={91}
              high={97}
              provenance="GROUNDED"
              model="placeholder"
            />
          </div>
        </div>
      </section>

      {/* Where this is wrong — the flaws LEAD, above the CTA (docs/09 §3.4, §4.1 Act 5, §11.4).
          Non-dismissable; amber left-rule; serif caveats. This is the flex, not a footnote. */}
      <section id="flaws" className="bg-paper text-slate-ink px-6 md:px-12 py-16 flex justify-center">
        <div className="w-full max-w-2xl flex flex-col gap-4 border-l-4 border-assumption-amber pl-6">
          <p className="font-mono text-provenance uppercase tracking-widest text-assumption-amber">
            Read before trusting a number
          </p>
          <h2 className="font-sans text-h1 font-semibold tracking-tight">Where this is wrong</h2>
          <ul className="flex flex-col gap-4 mt-1">
            <li className="font-serif text-body max-w-[62ch]">
              This is <span className="font-mono text-mono-data">L0 · Directional</span> — every number is
              modelled from your design, <span className="italic">not yet calibrated</span> to your real stack.
            </li>
            <li className="font-serif text-body max-w-[62ch]">
              Each figure ships with a confidence band. A <span className="text-assumption-amber">wide amber band</span>{" "}
              means we are guessing; grounded evidence narrows it toward green.
            </li>
            <li className="font-serif text-body max-w-[62ch]">
              The AI council <span className="italic">reasons</span>; it never produces a number — the
              deterministic engine does. But reasoning can still be wrong, so we show it and record dissent.
            </li>
          </ul>
        </div>
      </section>

      {/* Primary CTA lockup — AFTER the flaws (docs/09 §11.4: flaws above the CTA). */}
      <section className="bg-slate-ink text-paper px-6 py-20 flex flex-col items-center text-center gap-5">
        <Link
          href="/design"
          className="font-sans text-label font-medium px-6 py-3 rounded-full bg-paper text-slate-ink transition-all ease-settle duration-ui hover:bg-mist active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-ink"
        >
          Describe what you&apos;re building →
        </Link>
        <p className="font-mono text-provenance text-ink-muted">
          We&apos;ll tell you when we&apos;re guessing.
        </p>
      </section>

      {/* Footer */}
      <footer className="bg-slate-ink border-t border-steel px-6 py-8 text-center">
        <p className="font-mono text-provenance text-ink-muted">
          keystone · every number ships with its doubts · &copy; 2026
        </p>
      </footer>
    </>
  );
}
