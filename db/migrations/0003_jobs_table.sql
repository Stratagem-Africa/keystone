-- 0003_jobs_table.sql
--
-- Follow-up to #12/#87 ("Postgres job-state robustness") — prototype/api/jobs.py has always
-- had a Postgres-backed path (gated on SUPABASE_URL + a key being set), but no migration
-- anywhere in this repo ever created the `jobs` table it expects. Every write has been
-- silently falling back to the in-memory store (jobs.py's own graceful-degrade design), which
-- is why this went unnoticed until now — reported as PGRST205 "table not found in schema
-- cache" (PostgREST genuinely can't see a table that was never created, not a stale-cache
-- issue). This migration creates it.
--
-- Ownership design (revised after review — PR #161): a job belongs to whoever submitted it.
-- An EARLIER version of this migration took the deny-by-default / service_role-only shortcut
-- `simulation_run` uses in 0001 (no RLS policy, only the service_role key can touch the
-- table). Reviewer caught the real gap that created: the anon key's RLS lockout was the
-- ONLY defense, but jobs.py's actual endpoints (GET /jobs/:id, GET /jobs/:id/report) only
-- ever checked that the caller was SIGNED IN, never that the job was THEIRS. Once the table
-- was real and durable, switching to service_role (which bypasses RLS entirely) meant any
-- authenticated user holding another user's job UUID could read their full validated-design
-- report. This version closes that with REAL per-user RLS instead: `jobs` is scoped to
-- auth.uid(), the same shape 0001's own `own_memberships` policy uses (a user reads their
-- OWN rows) — NOT the same pattern as `simulation_run`, which has no policy at all; those
-- are opposite choices, not the same one. jobs.py goes back to the anon key, but a fresh
-- per-request client scoped to the caller's own JWT (`client.postgrest.auth(access_token)`
-- in jobs.py's `_client_for()`), so PostgREST's auth.uid() resolves to THAT user and this
-- policy only ever returns their rows — never a static, unscoped anon connection.

begin;

-- =====================================================================================
-- jobs — one row per /intent submission (prototype/api/jobs.py's `Job` dataclass). Columns
-- match exactly what jobs.py reads/writes today; nothing speculative added.
-- =====================================================================================
create table jobs (
  -- Supplied by the app (uuid4 generated in Python, jobs.py) — no DB-side default,
  -- since the caller always provides one.
  job_id         uuid primary key,
  -- Who submitted it. Derived by the trigger below from auth.uid(), never trusted from
  -- whatever the app sends — same "derive it, don't trust the caller" rule 0001 uses for
  -- tenant_id (a denormalised column an app could get wrong once, silently, so the DB
  -- fills it itself instead).
  user_id        uuid not null references auth.users(id) on delete cascade,
  status         text not null default 'queued'
                   check (status in ('queued', 'processing', 'done', 'error')),
  intent_text    text not null,
  -- Labels of secret patterns redacted on intake (ingestion.py's scan_and_redact_secrets),
  -- e.g. "openai-anthropic-key x1" — never the secret itself (harm floor).
  secrets_found  text[] not null default '{}',
  result         text,   -- markdown report, filled in once status = 'done'
  error          text,   -- redacted error message, filled in once status = 'error'
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- Same pattern as 0001's keystone_derive_tenant_from_* functions: `security invoker` so
-- the auth.uid() lookup runs as the CALLING role, not whoever owns the function — and
-- fires on UPDATE too, not just INSERT, so no write path (now or added later) can ever
-- reassign a job's ownership by including user_id in its payload.
create function keystone_derive_job_owner()
returns trigger
language plpgsql
security invoker
as $$
begin
  new.user_id = auth.uid();
  return new;
end;
$$;

create trigger trg_jobs_derive_owner
  before insert or update on jobs
  for each row
  execute function keystone_derive_job_owner();

-- Keeps updated_at honest on every UPDATE (status/result/error changes) without relying on
-- the app to remember to set it.
create function keystone_touch_job_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_jobs_touch_updated_at
  before update on jobs
  for each row
  execute function keystone_touch_job_updated_at();

-- Deny-by-default until the policy below exists (0001's own rule), then the one real
-- policy: a user can only ever see/write their OWN jobs — mirrors 0001's own_memberships
-- shape exactly (`using`/`with check` both keyed on the caller's own identity).
alter table jobs enable row level security;
alter table jobs force row level security;

create policy own_jobs on jobs
  using      (user_id = auth.uid())
  with check (user_id = auth.uid());

-- REVOKE ALL first (not just GRANT-additive) for the same reason 0001 does it: a Supabase
-- project's default table privileges vary by project history, so this forces every role
-- down to an explicit, guaranteed-zero baseline before the one intentional grant below.
-- No DELETE grant: nothing in the app deletes a job today — least privilege, not an
-- oversight; add it deliberately (with its own review) if a delete feature lands.
revoke all on jobs from anon, authenticated, service_role;
grant select, insert, update on jobs to authenticated;

commit;
