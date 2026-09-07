"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { isAuthConfigured, supabase } from "@/lib/supabase";

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  loading: boolean; // true until we've checked for an existing session once
  // False when NEXT_PUBLIC_SUPABASE_* are unset. Lets the UI say "sign-in isn't set up here"
  // instead of showing a sign-in button that cannot work. `user` is null either way, so nothing
  // gated on a user is reachable — this flag exists to EXPLAIN the state, never to bypass it.
  authConfigured: boolean;
};

// undefined (not null) as the "no provider" sentinel — lets useAuth() tell the
// difference between "not wrapped in a provider" (bug) and "no user" (valid state).
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  // Starts false when there is no client to ask: with auth unconfigured there is no session to
  // restore, so the app is not "loading" anything. Deriving it here rather than calling
  // setLoading(false) inside the effect also keeps the React Compiler's no-sync-setState rule
  // satisfied — the effect now only subscribes, which is what an effect is for.
  const [loading, setLoading] = useState(Boolean(supabase));

  useEffect(() => {
    if (!supabase) return;   // nothing to restore and nothing to subscribe to
    // On first mount: ask supabase-js for whatever session it already restored
    // from localStorage (e.g. the user was logged in on a previous visit).
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
    }).finally(() => setLoading(false));

    // Stay in sync after that: fires on sign-in, sign-out, token refresh, and
    // even sign-out triggered from another tab.
    const { data: listener } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
    });

    // This provider wraps the whole app so it never actually unmounts, but
    // React still requires effects to clean up their own subscriptions.
    return () => listener.subscription.unsubscribe();
  }, []);

  return (
    <AuthContext.Provider
      value={{ session, user: session?.user ?? null, loading, authConfigured: isAuthConfigured }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// The hook every component uses instead of touching AuthContext directly.
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (ctx === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
