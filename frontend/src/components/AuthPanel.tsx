"use client";

import { useAuth } from "@/lib/auth-context";
import { AuthForm } from "@/components/AuthForm";
import { supabase } from "@/lib/supabase";

// Switches between "show the form" and "already signed in" based on the shared
// session state from AuthProvider — this is why /auth/page.tsx doesn't need to
// be a Client Component itself (it can stay a plain Server Component with
// `metadata`, and just render this as a child).
export function AuthPanel() {
  const { user, loading } = useAuth();

  if (loading) {
    // First-paint check for a restored session — brief and not a metric, so a
    // plain neutral placeholder (no confidence band applies here).
    return <p className="font-sans text-label text-ink-muted">Loading…</p>;
  }

  if (user) {
    return (
      <div className="flex flex-col gap-4">
        <p className="font-sans text-body text-slate-ink">
          Signed in as <span className="font-medium">{user.email}</span>
        </p>
        <button
          onClick={() => supabase.auth.signOut()}
          className="self-start font-sans text-label font-medium px-6 py-3 rounded-full border border-steel text-slate-ink transition-all ease-settle duration-ui hover:bg-mist"
        >
          Sign out
        </button>
      </div>
    );
  }

  return <AuthForm />;
}
