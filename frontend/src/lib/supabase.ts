import { createClient } from "@supabase/supabase-js";

// One shared client for the whole app — talks directly to Supabase's Auth API,
// not our own FastAPI backend (issue #19 has no dependency on #10 for this reason).
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // Fail loud in dev rather than letting every auth call fail with a cryptic
  // network error against an empty URL — see frontend/.env.local.
  throw new Error(
    "Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY — set them in frontend/.env.local"
  );
}

// The anon key is safe to ship to the browser (docs/08 issue #19): it identifies
// the Supabase project, not a user. Real access control is per-user JWT + RLS.
export const supabase = createClient(url, anonKey);
