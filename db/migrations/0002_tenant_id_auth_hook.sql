-- 0002_tenant_id_auth_hook.sql
--
-- Issue #21 / ADR-005 §1 — the Supabase custom-access-token auth hook that injects the
-- `tenant_id` claim every RLS policy in 0001 depends on. A (Bifola) owns auth/tenant-isolation;
-- this is the piece ADR-005's build-plan bundles with the migration and #144 correctly deferred.
--
-- WHY THIS EXISTS (ADR-005 §1, verbatim): "The `tenant_id` claim is not populated by Supabase by
-- default (a custom claim). It MUST be injected at token generation by a Supabase
-- custom-access-token auth hook that reads the user's tenant_id from the membership table ...
-- Without it the predicate `auth.jwt() ->> 'tenant_id'` is null and every policy denies every row."
-- 0001's policies read `keystone_current_tenant()` = `(auth.jwt() ->> 'tenant_id')::uuid`; this hook
-- is what puts a real value there. Until it is registered (see REGISTRATION below), the store is
-- fail-closed (deny-all), not broken.
--
-- Depends on: 0001_canonical_model_store.sql (needs `membership`). Apply after it.
--
-- REGISTRATION (a migration CANNOT do this — it is Supabase Auth project config, Bifola's step):
--   • Dashboard: Authentication → Hooks → "Customize Access Token (JWT) Claims" →
--     enable, function = `public.keystone_access_token_hook`.
--   • Or supabase/config.toml:
--       [auth.hook.custom_access_token]
--       enabled = true
--       uri = "pg-functions://postgres/public/keystone_access_token_hook"
--   The hook only takes effect on tokens minted AFTER it is enabled (existing sessions keep their
--   old claims until they refresh) — so enable it BEFORE onboarding any real tenant.

begin;

-- The hook. Supabase Auth calls this (as role `supabase_auth_admin`) while minting a token, passing
--   event = {"user_id": <uuid>, "claims": {<the JWT payload so far>}, "authentication_method": ...}
-- and expects the same shape back with `claims` modified. We look up the user's tenant from
-- `membership` and set a TOP-LEVEL `tenant_id` claim (top-level, not nested under app_metadata, so it
-- matches 0001's `auth.jwt() ->> 'tenant_id'` predicate exactly). SECURITY INVOKER (default): the
-- function runs as the CALLING role (supabase_auth_admin), which is why the read below needs the
-- explicit grant + policy further down — least privilege, per Supabase's documented hook pattern
-- (no SECURITY DEFINER, so the function can never read more than supabase_auth_admin is allowed to).
create or replace function public.keystone_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
as $$
declare
  claims    jsonb;
  v_tenant  uuid;
begin
  -- v1 is one-tenant-per-user (ADR-005 §1). If a user ever has multiple memberships, this picks the
  -- earliest deterministically; acting-as a different tenant is a future "active tenant" mechanism,
  -- NOT a silent multi-tenant grant. `order by created_at, tenant_id` keeps it total/deterministic.
  select tenant_id into v_tenant
  from public.membership
  where user_id = (event ->> 'user_id')::uuid
  order by created_at, tenant_id
  limit 1;

  claims := coalesce(event -> 'claims', '{}'::jsonb);

  if v_tenant is not null then
    claims := jsonb_set(claims, '{tenant_id}', to_jsonb(v_tenant::text));
  else
    -- No membership → NO tenant_id claim. Every 0001 policy then denies every row (designed
    -- fail-closed: a user with no tenant sees nothing, rather than erroring or leaking). Strip any
    -- pre-existing value so a stale/forged claim on the inbound event can never survive.
    claims := claims - 'tenant_id';
  end if;

  return jsonb_set(event, '{claims}', claims);
end;
$$;

-- Only Supabase Auth may run the hook; no client-facing role can (it reads every tenant's membership,
-- so it must never be user-invocable). REVOKE from public first — grants on new functions default to
-- PUBLIC EXECUTE, which would otherwise let `authenticated` call it and enumerate memberships.
revoke execute on function public.keystone_access_token_hook(jsonb) from public;
revoke execute on function public.keystone_access_token_hook(jsonb) from anon, authenticated;
grant  execute on function public.keystone_access_token_hook(jsonb) to supabase_auth_admin;

-- The hook runs as supabase_auth_admin, which does NOT carry BYPASSRLS — so 0001's ENABLE+FORCE RLS
-- on `membership` applies to it too, and its only policy (`own_memberships`, user_id = auth.uid())
-- matches nothing during token mint (there is no auth.uid() yet — that's what we're minting). Give it
-- exactly the read it needs and no more: schema usage + SELECT grant + a SELECT-only policy scoped to
-- this one role. This is additive to 0001's grants and does not widen any client role's access.
grant usage  on schema public       to supabase_auth_admin;
grant select on public.membership    to supabase_auth_admin;

create policy membership_auth_admin_read on public.membership
  as permissive for select
  to supabase_auth_admin
  using (true);

commit;
