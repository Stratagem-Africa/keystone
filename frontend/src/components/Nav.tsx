"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

// Shared top nav — appears on every page via direct import (not layout.tsx,
// so individual pages can opt into a bare full-screen view later if needed).
// Client Component (issue #19): needs useAuth() to show sign-in state.
export function Nav() {
  const { user, loading } = useAuth();

  return (
    <nav className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 bg-slate-ink border-b border-steel">
      <Link
        href="/"
        className="font-sans font-semibold tracking-tight text-paper transition-colors ease-settle duration-ui hover:text-ink-muted"
      >
        keystone
      </Link>

      <div className="flex items-center gap-4">
        {/* Accuracy-ladder badge — docs/09 §3.6 */}
        <span className="font-mono text-provenance text-ink-muted border border-steel rounded px-2 py-px">
          L0 · Directional
        </span>

        {/* Auth state — architect-blue for the interactive link, never amber/green
            (no confidence meaning here, docs/09 §2.4). */}
        {!loading && (
          user ? (
            <button
              onClick={async () => { const { error } = await supabase.auth.signOut(); if (error) console.error(error.message); }}
              className="font-sans text-label text-ink-muted hover:text-paper transition-colors ease-settle duration-ui"
            >
              Sign out
            </button>
          ) : (
            <Link
              href="/auth"
              className="font-sans text-label text-architect-blue hover:text-paper transition-colors ease-settle duration-ui"
            >
              Sign in
            </Link>
          )
        )}
      </div>
    </nav>
  );
}
