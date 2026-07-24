"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";

type AuthContextValue = {
  session: Session | null;
  user: User | null;
  loading: boolean; // true until we've checked for an existing session once
};

// undefined (not null) as the "no provider" sentinel — lets useAuth() tell the
// difference between "not wrapped in a provider" (bug) and "no user" (valid state).
const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // On first mount: ask supabase-js for whatever session it already restored
    // from localStorage (e.g. the user was logged in on a previous visit).
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

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
    <AuthContext.Provider value={{ session, user: session?.user ?? null, loading }}>
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
