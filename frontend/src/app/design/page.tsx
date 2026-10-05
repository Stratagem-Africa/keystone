import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { IntentEntry } from "@/components/IntentEntry";

export const metadata: Metadata = {
  title: "keystone · full design",
  description: "Describe what you're building — AI architects design it and justify every decision; the engine computes every number.",
};

// Route: /design — the FULL pipeline (#204): describe → AI ingests it into a model → the council
// writes the design decisions → the engine simulates → a report + the interactive map. A plain Server
// Component (keeps `metadata` working); which pipeline runs (local, no sign-in, or your account) is
// decided client-side in IntentEntry.
export default function DesignPage() {
  return (
    <>
      <Nav />
      <main className="flex-1 bg-paper text-slate-ink px-6 py-16">
        <div className="max-w-4xl mx-auto flex flex-col gap-8">

          <div className="flex flex-col gap-3">
            <p className="font-mono text-provenance text-ink-muted-strong uppercase tracking-widest">
              intent → reasoned, simulated design
            </p>
            <h1 className="font-sans text-h2 font-semibold tracking-tight">
              The full design, with its reasons.
            </h1>
            <p className="font-serif text-body max-w-[62ch]">
              A panel of AI architects turns your description into a design and writes down why each choice was
              made. The engine — never the AI — then works out every number: capacity, latency, cost, and where it
              breaks. Where an input is a guess, the report says so.
            </p>
          </div>

          <IntentEntry />

        </div>
      </main>
    </>
  );
}
