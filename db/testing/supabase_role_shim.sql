-- supabase_role_shim.sql
--
-- NOT a migration. NEVER run against a real Supabase project — it already has every role,
-- schema, and function created below (Supabase provisions them itself). This exists purely
-- so a plain local Postgres 17+ can stand in for Supabase Postgres well enough to apply
-- db/migrations/0001 and 0002 and exercise their RLS policies, grants, and the tenant-claim
-- auth hook under a real `authenticated`/`supabase_auth_admin` role and a shimmed
-- auth.uid()/auth.jwt() — for prototype/tests/db_test_*.py only.
--
-- Lives in db/testing/, a sibling of db/migrations/, specifically so no "apply everything
-- under db/migrations/ in order" tooling ever picks this up by accident.
--
-- Apply BEFORE 0001: 0001 references auth.users(id) (the membership FK) and auth.uid() (the
-- own_memberships policy), and grants/revokes privileges on anon/authenticated/service_role —
-- all of those must already exist.
--
-- Idempotent: safe to re-run against a cluster that already has these objects.

create schema if not exists auth;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    -- bypassrls, matching real Supabase: this is what makes service_role's own tenant
    -- isolation an application-layer contract (SupabaseModelStore), not a DB-layer one —
    -- see db_test_tenant_isolation.py's explicit scope note on simulation_run.
    create role service_role nologin noinherit bypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    create role supabase_auth_admin nologin noinherit;
  end if;
end
$$;

-- Minimal stand-in for Supabase's real auth.users — only what 0001's FK and the test
-- fixtures need (id + a human-readable email for debugging failures).
create table if not exists auth.users (
  id    uuid primary key default gen_random_uuid(),
  email text
);

grant usage  on schema auth   to anon, authenticated, service_role, supabase_auth_admin;
grant select on auth.users    to authenticated, service_role, supabase_auth_admin;
grant usage  on schema public to anon, authenticated, service_role;

-- auth.uid() / auth.jwt(): read the session-local GUC PostgREST/Supabase actually use
-- (`request.jwt.claims`, a JSON string), set per-test via
-- `select set_config('request.jwt.claims', <json>, true)` — the `true` third argument makes
-- it SET LOCAL scoped, so it reverts automatically at transaction end, same as a real
-- per-request GUC. `stable`, not `immutable`: this reads session state, matching 0001's own
-- keystone_current_tenant() precedent (also `stable`, also reads auth.jwt()).
create or replace function auth.uid() returns uuid
language sql stable
as $$
  -- LANGUAGE SQL functions require the final query's result type to exactly match (or be
  -- binary-coercible to) the declared return type -- unlike PL/pgSQL's RETURN, no general
  -- assignment-cast coercion applies. `->>` always yields text, so the explicit ::uuid cast
  -- below is required, not decorative (omitting it fails at CREATE FUNCTION time with
  -- "return type mismatch ... Actual return type is text").
  select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid;
$$;

create or replace function auth.jwt() returns jsonb
language sql stable
as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb, '{}'::jsonb);
$$;
