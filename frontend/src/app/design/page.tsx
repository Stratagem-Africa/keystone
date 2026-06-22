import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { IntentForm } from "@/components/IntentForm";

export const metadata: Metadata = {
  title: "keystone · describe your system",
  description: "Describe what you're building. The council will deliberate.",
};

// Route: /design — the intent input step (Epic 4.2, docs/08).
// bg-paper: warm, light surface — the user is authoring, not reading a report.
export default function DesignPage() {
  return (
    <>
      <Nav />
      <main className="flex-1 bg-paper px-6 py-16">
        <div className="max-w-2xl mx-auto flex flex-col gap-8">

          {/* Step indicator */}
          <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
            step 1 of 4 · intent
          </p>

          {/* Heading — grotesque/sans (chrome) */}
          <div className="flex flex-col gap-3">
            <h1 className="font-sans text-h2 font-semibold tracking-tight text-slate-ink">
              Describe what you&apos;re building.
            </h1>
            {/* Explanation — serif signals this is model-reasoned context, not UI label */}
            <p className="font-serif text-body text-ink-muted">
              Write a plain-English brief. The ingestion layer will infer a
              canonical system model, surface every assumption it made in amber,
              and ask you to resolve contradictions before the council deliberates.
            </p>
          </div>

          <IntentForm />

        </div>
      </main>
    </>
  );
}
