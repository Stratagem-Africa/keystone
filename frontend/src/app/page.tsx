import { Metric } from "@/components/Metric";

export default function Home() {
  return (
    <>
      {/* Nav */}
      <nav className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 bg-slate-ink border-b border-steel">
        {/* Wordmark — grotesque/sans, lowercase per docs/09 §2.1 */}
        <span className="font-sans font-semibold tracking-tight text-paper">
          keystone
        </span>
        {/* Accuracy-ladder badge — docs/09 §3.6 */}
        <span className="font-mono text-provenance text-ink-muted border border-steel rounded px-2 py-px">
          L0 · Directional
        </span>
      </nav>

      {/* Hero — slate-ink, the "instrument panel" surface */}
      <section className="flex-1 flex flex-col items-center justify-center bg-slate-ink text-paper px-6 py-24 text-center gap-8">
        <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
          scaffold · no real data yet
        </p>

        {/* Primary headline — grotesque signals chrome/UI (docs/09 §2.5) */}
        <h1 className="font-sans text-h1 font-semibold tracking-tight max-w-2xl">
          Show your work.
        </h1>

        {/* Sub-copy — serif signals model-reasoned prose */}
        <p className="font-serif text-body max-w-xl">
          The model reasons. The engine computes. Every number ships with its
          assumptions, a confidence band, and a{" "}
          <span className="text-assumption-amber">&ldquo;where this is wrong&rdquo;</span>{" "}
          section.
        </p>

        {/* Demo Metric — shows what a real metric will look like */}
        <div className="mt-4 p-6 bg-graphite border border-steel rounded-lg text-left">
          <p className="font-mono text-provenance text-ink-muted mb-4 uppercase tracking-wider">
            example metric
          </p>
          <Metric
            value={86}
            unit="ms"
            low={72}
            high={104}
            provenance="ASSUMPTION"
            model="placeholder — wire to API"
          />
        </div>

        <p className="font-mono text-provenance text-ink-muted">
          We&apos;ll tell you when we&apos;re guessing.
        </p>
      </section>

      {/* Reasoning → Computation seam — docs/09 §3.2 */}
      <section className="grid grid-cols-1 md:grid-cols-2">
        {/* Warm zone — serif, paper ground — model-reasoned prose */}
        <div className="bg-paper text-slate-ink px-8 py-12 flex flex-col gap-4">
          <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
            reasoning zone · model
          </p>
          <div className="w-8 h-px bg-mist" />
          {/* Serif = the model reasoned this */}
          <p className="font-serif text-body">
            The council of AI architects deliberates on your system design,
            proposes ADRs, and records dissent. Serif typeface signals the source:
            a language model reasoned this — not the engine.
          </p>
          <p className="font-serif text-body text-ink-muted italic">
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

      {/* Footer */}
      <footer className="bg-slate-ink border-t border-steel px-6 py-8 text-center">
        <p className="font-mono text-provenance text-ink-muted">
          keystone · every number ships with its doubts · &copy; 2026
        </p>
      </footer>
    </>
  );
}
