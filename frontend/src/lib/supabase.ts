// Full @supabase/supabase-js (not the slimmer @supabase/auth-js) even though we
// only use .auth today — Storage is on the roadmap (docs/08 Epic 5), so the
// umbrella package's DX outweighs the unused postgrest/realtime/functions weight.
import { createClient } from "@supabase/supabase-js";

// One shared client for the whole app — talks directly to Supabase's Auth API,
// not our own FastAPI backend (issue #19 has no dependency on #10 for this reason).
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Missing config used to `throw` HERE, at module load. That looked like a helpful dev-time guard
// and was actually the single biggest barrier to anyone seeing Keystone at all: `app/layout.tsx`
// (the ROOT layout) imports AuthProvider, which imports this file — so the throw took down every
// route in the app, including the PUBLIC /studio page that needs no account whatsoever. A stranger
// who cloned the repo had to go and provision a third-party Supabase project before they could see
// a single architecture render.
//
// Absent config is now a STATE the app reports, not a crash. `supabase` is null and
// `isAuthConfigured` is false; the sign-in UI says so plainly instead of erroring.
//
// THIS IS FAIL-CLOSED, and that property is the whole reason it is safe: with no client there is no
// session, so `user` is null, so everything gated on a user stays gated. Absent auth infrastructure
// can only ever REMOVE access here, never grant it. Anything that must be protected must check the
// user — never merely assume the provider exists.
export const isAuthConfigured = Boolean(url && anonKey);

export const supabase = isAuthConfigured ? createClient(url!, anonKey!) : null;
