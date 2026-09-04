import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { ArchStudio } from "@/components/ArchStudio";

export const metadata: Metadata = {
  title: "keystone · architecture studio",
  description: "Type an intent — get a deep, interactive architecture, simulated by the engine.",
};

// Route: /studio — the interactive generation surface. Type an intent → a deep, layered architecture
// rendered on the SAMS-style canvas + the engine's verdict. Dark ground (bg-slate-ink) frames the dark
// map. Public: /generate is stateless + not auth-gated, so no sign-in is required to try it.
export default function StudioPage() {
  return (
    <>
      <Nav />
      <main className="flex-1 bg-slate-ink text-paper px-6 py-16">
        <div className="max-w-6xl mx-auto flex flex-col gap-8">

          <div className="flex flex-col gap-3">
            <p className="font-mono text-provenance text-ink-muted uppercase tracking-widest">
              intent → validated design
            </p>
            <h1 className="font-sans text-h2 font-semibold tracking-tight">
              Describe it. See it built.
            </h1>
            <p className="font-serif text-body text-ink-muted max-w-[62ch]">
              Type what you want to build. Keystone designs a deep, layered architecture, simulates it on
              the deterministic engine, and shows you the structure, the cost, the capacity — and exactly
              where it breaks. Every number is the engine&apos;s; every input stays an assumption until grounded.
            </p>
          </div>

          <ArchStudio />

        </div>
      </main>
    </>
  );
}
