import Link from "next/link";
import { Nav } from "@/components/Nav";
import { Metric } from "@/components/Metric";
import { LivingSim } from "@/components/LivingSim";

export default function Home() {
  return (
    <>
      <Nav />

      {/* Hero — slate-ink "instrument panel". Competence BEFORE confession (docs/09 §4.1 Act 1,
          §11.5): the headline + the living-sim demonstrating a real breakpoint land first; the
          honest caveats come later (the flaws section, below the fold), so honesty reads as
          mastery, not weakness. */}
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
            A panel of AI architects designs your system and gives a reason for every choice. A separate maths engine — never the AI — works out the numbers, and gets the same answer every time. Where an input rests on a published measurement we cite it; where we&apos;re guessing, we say so.
          </p>

          {/* Living sim (docs/09 §4.1 Act 1) — a real LB→App→Cache→DB stack. "Push it to 10×" floods
              the load and the engine reveals where it breaks; "reseed" replays byte-identical. Every
              number is the engine's, not the model's (prime directive). CSS/React-state, no WebGL,
              reduced-motion + JS-off safe. */}
          <LivingSim />

          {/* Gentle scroll affordance — not a conversion CTA (that waits until after the flaws). */}
          <a
            href="#flaws"
            className="font-sans text-label text-architect-blue hover:text-paper transition-colors ease-settle duration-ui rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-ink"
          >
            See how — and where it&apos;s wrong ↓
          </a>

          {/* Stub honesty, demoted to a small note (docs/09 §11 stub-honesty). The sim above is real
              engine output; the full council/ingestion pipeline is still scaffold. */}
          <p className="font-mono text-provenance text-ink-muted/70">
            one real worked example · the rest of the tool is still being built
          </p>
        </div>
      </section>

      {/* Reasoning → Computation seam — docs/09 §3.2 */}
      <section className="grid grid-cols-1 md:grid-cols-2">
        {/* Warm zone — serif, paper ground — model-reasoned prose */}
        <div className="bg-paper text-slate-ink px-8 py-12 flex flex-col gap-4">
          <p className="font-mono text-provenance text-ink-muted-strong uppercase tracking-widest">
            the thinking · done by AI
          </p>
          <div className="w-8 h-px bg-mist" />
          {/* Serif = the model reasoned this. Bounded to a comfortable reading measure (docs/09 §8). */}
          <p className="font-serif text-body max-w-[60ch]">
            The AI architects argue out your design, write down each decision with the reason behind it (an ADR — an architecture decision record, which you&apos;ll meet in real engineering teams), and keep any objection they couldn&apos;t settle. Text in this typeface always means an AI wrote it — not the maths engine.
          </p>
          <p className="font-serif text-body text-ink-muted-strong italic max-w-[60ch]">
            &ldquo;Keeping a copy of the popular data in a cache means most reads never travel to the database, so they come back faster. The trade-off: that copy can be a moment out of date, so a reader may briefly see an old value…&rdquo;
          </p>
        </div>

        {/* Cool zone — mono, slate-ink ground — engine-computed numbers */}
        <div className="bg-slate-ink text-paper px-8 py-12 flex flex-col gap-4">
          <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
            the numbers · done by the maths engine
          </p>
          <div className="w-8 h-px bg-steel" />
          <p className="font-mono text-provenance text-ink-muted">
            your design → maths engine → a number
          </p>
          {/* Mono = the engine computed these */}
          <div className="flex flex-col gap-6 mt-2">
            <Metric
              value={4200}
              unit=" requests/sec"
              low={2800}
              high={6000}
              provenance="ASSUMPTION"
              model="an example number — not from your system"
            />
            <Metric
              value={94}
              unit="%"
              low={91}
              high={97}
              provenance="GROUNDED"
              model="an example number — not from your system"
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
              These numbers are <span className="font-mono text-mono-data">L0 · Directional</span> — a rough first estimate, worked out from the design you described and <span className="italic">never yet checked against</span> a system of yours that&apos;s actually running. They point in the right direction; they are not measurements.
            </li>
            <li className="font-serif text-body max-w-[62ch]">
              Every number comes with a confidence band — a bar showing how sure we are. A <span className="text-assumption-amber">wide amber band</span>{" "}means we guessed the inputs. When we can point to a published measurement instead, the bar gets narrower and turns green.
            </li>
            <li className="font-serif text-body max-w-[62ch]">
              The AI does the <span className="italic">thinking</span>; it never produces a number — the maths engine works those out, and gets the same answer every time. Thinking can still be wrong, so we show you the reasoning and keep any objection the architects couldn&apos;t settle.
            </li>
          </ul>
        </div>
      </section>

      {/* Primary CTA lockup — AFTER the flaws (docs/09 §11.4: flaws above the CTA). One door: describe
          what you're building and you land on a deep, editable architecture with the engine's verdict. */}
      <section className="bg-slate-ink text-paper px-6 py-20 flex flex-col items-center text-center gap-5">
        <Link
          href="/studio"
          className="font-sans text-label font-medium px-6 py-3 rounded-full bg-paper text-slate-ink transition-all ease-settle duration-ui hover:bg-mist active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-ink"
        >
          Describe it. See it built. →
        </Link>
        <p className="font-mono text-provenance text-ink-muted">
          We&apos;ll tell you when we&apos;re guessing.
        </p>
      </section>

      {/* Footer */}
      <footer className="bg-slate-ink border-t border-steel px-6 py-8 text-center">
        <p className="font-mono text-provenance text-ink-muted">
          keystone · every number comes with its doubts · &copy; 2026
        </p>
      </footer>
    </>
  );
}
