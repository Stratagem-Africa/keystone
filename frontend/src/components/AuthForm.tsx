"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";

type Mode = "sign-in" | "sign-up";

// NOTE on color: this form does NOT use assumption-amber for its inputs.
// Amber is reserved exclusively for engine-input/confidence semantics (docs/09
// §2.4 — "load-bearing, not palette"), e.g. IntentForm's brief text, which
// becomes an ASSUMPTION the engine will ground. Email/password aren't a system
// model input — they carry no confidence meaning — so this form stays neutral
// (steel/mist/architect-blue), with signal-red reserved for real auth failures.
export function AuthForm() {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setMessage(null);

    if (mode === "sign-up") {
      const { data, error } = await supabase.auth.signUp({ email, password });
      if (error) {
        setError(error.message);
      } else if (!data.session) {
        // Supabase's default project config requires email confirmation before
        // issuing a session — signUp() succeeds but logs no one in yet.
        setMessage("Check your email to confirm your account, then sign in.");
      }
      // If data.session IS set (email confirmation off), AuthProvider's
      // onAuthStateChange listener picks it up automatically — nothing more to do.
    } else {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) setError(error.message);
      // On success, onAuthStateChange updates the shared session — no redirect
      // logic needed here; the page reading useAuth() reacts on its own.
    }

    setLoading(false);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6 w-full max-w-sm">

      {/* Mode toggle — architect-blue signals "interactive", never confidence */}
      <div className="flex gap-4 font-sans text-label">
        <button
          type="button"
          onClick={() => { setMode("sign-in"); setError(null); setMessage(null); }}
          className={`pb-1 border-b-2 rounded-sm transition-colors ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue ${mode === "sign-in" ? "text-slate-ink font-semibold border-architect-blue" : "text-ink-muted border-transparent hover:text-slate-ink"}`}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => { setMode("sign-up"); setError(null); setMessage(null); }}
          className={`pb-1 border-b-2 rounded-sm transition-colors ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue ${mode === "sign-up" ? "text-slate-ink font-semibold border-architect-blue" : "text-ink-muted border-transparent hover:text-slate-ink"}`}
        >
          Create account
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="email" className="font-sans text-label uppercase tracking-widest text-ink-muted">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="w-full rounded-lg border border-steel bg-paper text-slate-ink font-sans text-body px-4 py-3 transition-all ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue hover:border-ink-muted"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="password" className="font-sans text-label uppercase tracking-widest text-ink-muted">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          className="w-full rounded-lg border border-steel bg-paper text-slate-ink font-sans text-body px-4 py-3 transition-all ease-settle duration-ui focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue hover:border-ink-muted"
        />
      </div>

      {/* Real failure — signal-red is exactly what this color is for */}
      {error && (
        <p className="font-sans text-label text-signal-red">{error}</p>
      )}

      {/* Neutral instruction, not a confidence signal — no amber */}
      {message && (
        <p className="font-sans text-label text-ink-muted">{message}</p>
      )}

      <button
        type="submit"
        disabled={loading}
        className="self-start font-sans text-label font-medium px-6 py-3 rounded-full bg-slate-ink text-paper transition-all ease-settle duration-ui hover:bg-graphite hover:shadow-sm active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-architect-blue focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
      >
        {loading ? "Working…" : mode === "sign-in" ? "Sign in" : "Create account"}
      </button>

    </form>
  );
}
