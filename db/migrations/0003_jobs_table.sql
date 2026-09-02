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
-- Scope, deliberately narrow: this makes the table EXIST and be safely reachable — it does
-- NOT add per-user/tenant ownership. jobs.py itself already carries a
-- `TODO(tenant-isolation, #21)` on its insert, and #87 is the tracked follow-up for real
-- job-state robustness (including who can read/update a given job_id). Building that properly
-- means a user_id/tenant_id column, an RLS policy, AND threading the caller's JWT through the
-- Supabase client jobs.py uses (right now it's one static client built once at import time,
-- not a per-request client carrying the caller's identity) — real scope, not a one-line add,
-- and per CLAUDE.md, auth/tenant-isolation changes get their own adversarial
-- Review -> Verify -> Adjudicate pass, not a rider on a schema-existence fix.
--
-- Safe default in the meantime, same pattern `simulation_run` already uses in
-- 0001_canonical_model_store.sql (engine/pipeline-written data, no direct end-user RLS story
-- yet): enable + FORCE row-level security with NO policy at all (deny-by-default — the same
-- "no policy means zero rows readable or writable" rule 0001 documents), then grant CRUD only
-- to `service_role`. `anon`/`authenticated` get nothing, so no key that could ever reach a
-- browser can read or write any tenant's job data. Consequently jobs.py must use
-- SUPABASE_SERVICE_ROLE_KEY, not SUPABASE_ANON_KEY, to reach this table (companion code change
-- in the same PR).

begin;

-- =====================================================================================
-- jobs — one row per /intent submission (prototype/api/jobs.py's `Job` dataclass). Columns
-- match exactly what jobs.py reads/writes today; nothing speculative added.
-- =====================================================================================
create table jobs (
  -- Supplied by the app (uuid4 generated in Python, jobs.py:44) — no DB-side default,
  -- since the caller always provides one.
  job_id         uuid primary key,
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

-- Keeps updated_at honest on every UPDATE (status/result/error changes) without relying on
-- the app to remember to set it — same "derive it, don't trust the caller" spirit as 0001's
-- tenant-derivation triggers, just for a timestamp instead of a tenant_id.
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

-- Deny-by-default (0001's own rule: "no policy at all means zero rows readable or writable
-- until the policy below exists") — there IS no policy below, on purpose. Nobody using the
-- anon or authenticated role can read or write this table at all, regardless of grants.
alter table jobs enable row level security;
alter table jobs force row level security;

-- REVOKE ALL first (not just GRANT-additive) for the same reason 0001 does it: a Supabase
-- project's default table privileges vary by project history, so this forces every role down
-- to an explicit, guaranteed-zero baseline before the one intentional grant below.
revoke all on jobs from anon, authenticated, service_role;

grant select, insert, update, delete on jobs to service_role;

commit;
