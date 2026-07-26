"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

// Shared top nav — appears on every page via direct import (not layout.tsx,
// so individual pages can opt into a bare full-screen view later if needed).
// Client Component (issue #19): needs useAuth() to show sign-in state.
export function Nav() {
  const { user, loading } = useAuth();

  // Chrome focus ring: architect-blue with a slate-ink offset (the nav's own ground). docs/09 §2.4.
  const navFocus =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-ink rounded-sm";

  return (
    <nav className="sticky top-0 z-20 flex items-center justify-between px-6 py-4 bg-slate-ink border-b border-steel">
      {/* Wordmark — lowercase `keystone` per docs/09 §2.1, with the Stratagem parent-brand
          attribution as a smaller, muted secondary mark (keystone stays the primary). */}
      <Link
        href="/"
        aria-label="Keystone by Stratagem — home"
        className={`group inline-flex items-baseline gap-1.5 ${navFocus}`}
      >
        <span className="font-sans font-semibold tracking-tight text-paper transition-colors ease-settle duration-ui group-hover:text-architect-blue">
          keystone
        </span>
        <span className="font-sans text-provenance text-ink-muted tracking-wide">by Stratagem</span>
      </Link>

      <div className="flex items-center gap-4">
        {/* Accuracy-ladder badge — climbable, honest status, not a trust-me seal (docs/09 §3.6).
            A native <details> disclosure: keyboard-accessible, no framework state. Neutral hues
            ONLY — green here would read as "certified" and break §11.4. */}
        <details className="relative">
          <summary className={`cursor-pointer list-none [&::-webkit-details-marker]:hidden font-mono text-provenance text-ink-muted border border-steel rounded px-2 py-px transition-colors ease-settle duration-ui hover:text-paper ${navFocus}`}>
            L0 · Directional
          </summary>
          <div className="absolute right-0 mt-2 w-72 z-30 flex flex-col gap-2 rounded-lg border border-steel bg-graphite p-4 shadow-lg">
            <p className="font-mono text-provenance uppercase tracking-widest text-ink-muted">
              accuracy ladder — where we honestly are
            </p>
            {[
              ["L0", "Directional", "current — modelled from your design, not yet field-calibrated", true],
              ["L1", "Calibrated", "not yet earned — needs observed field data", false],
              ["L2", "Validated", "not yet earned", false],
              ["L3", "Certified", "never claimed — Keystone does not certify", false],
            ].map(([lvl, name, note, here]) => (
              <div key={lvl as string} className="flex flex-col">
                <span className={`font-mono text-provenance ${here ? "text-paper" : "text-ink-muted"}`}>
                  <span className="font-semibold">{lvl}</span> · {name}
                  {here ? " ◂ you are here" : ""}
                </span>
                <span className="font-sans text-provenance text-ink-muted">{note}</span>
              </div>
            ))}
          </div>
        </details>

        {/* Auth state — architect-blue for the interactive link, never amber/green
            (no confidence meaning here, docs/09 §2.4). */}
        {!loading && (
          user ? (
            <button
              onClick={async () => { const { error } = await supabase.auth.signOut(); if (error) console.error(error.message); }}
              className={`font-sans text-label text-ink-muted hover:text-paper transition-colors ease-settle duration-ui ${navFocus}`}
            >
              Sign out
            </button>
          ) : (
            <Link
              href="/auth"
              className={`font-sans text-label text-architect-blue hover:text-paper transition-colors ease-settle duration-ui ${navFocus}`}
            >
              Sign in
            </Link>
          )
        )}
      </div>
    </nav>
  );
}
