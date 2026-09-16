-- 0006_project_deletion_rpc.sql
--
-- Issue #21 "Milestone 6" (ADR-005 §5, privacy + deletion) — the DB-row half of erasure.
--
-- The row-purge itself needs NO new schema: every project_id-scoped table already cascades
-- via `on delete cascade` (0001), verified directly against real Postgres before writing this
-- file (a plain `DELETE FROM project` as `authenticated`, own tenant, reaches system_model,
-- component, flow, flow_step, assumption, source_document, AND simulation_run down to zero
-- rows — even though `authenticated` holds no direct write grant on most of those tables
-- post-0004; FK ON DELETE CASCADE runs as an internal RI trigger, not ordinary DML the
-- caller's own table grants would need to cover).
--
-- What DOES need a function: `SupabaseModelStore.delete_project()` (Python) must read each
-- `source_document.uri` under a project BEFORE deleting it — the cascade removes those rows
-- too, so reading them after would find nothing to report as needing a Storage/R2 purge.
-- Through PostgREST, "SELECT the uris" and "DELETE the project" are two separate REST calls,
-- not one transaction (same reason 0004 needed an RPC for save_model: supabase-py's client is
-- one-REST-call-per-statement). Two separate calls leaves a real race: a source_document
-- inserted between them is cascade-deleted without ever being read, silently orphaning
-- whatever Storage/R2 object it pointed at with no record that it needed purging (found by
-- independent review of the two-round-trip Python-only version of this). A single function
-- call is one implicit transaction, closing that window the same way 0004 closed its own.
--
-- LOCKING: a plain SELECT-then-DELETE inside one function is NOT by itself enough to close
-- the race described above under READ COMMITTED (Postgres's default) — each STATEMENT takes
-- its own snapshot, so a concurrent INSERT into source_document that commits between our
-- SELECT and our DELETE would still be invisible to v_uris, yet still get cascade-deleted
-- (found by a second independent review, after the first version of this file shipped
-- without the lock below). The fix mirrors 0004's own technique exactly: `select ... for
-- update` on the project row BEFORE reading its children. Postgres's own FK enforcement
-- takes a `FOR KEY SHARE` lock on a referenced row for every INSERT that references it (to
-- stop the parent disappearing mid-check) — our stronger `FOR UPDATE` lock on that same row
-- forces any concurrent `insert into source_document (project_id, ...) values (p_project_id,
-- ...)` to block until we commit or roll back. By then the project row is either gone (that
-- INSERT then fails its own FK check, which is correct — you cannot attach a document to a
-- project that no longer exists) or it committed before we ever locked the row, in which
-- case our SELECT already saw it. Either way, no source_document can slip through uncounted.
--
-- ASSUMES READ COMMITTED (Postgres's own default, and Supabase's — flagged by a third
-- independent review, not fixed here): the lock-then-reread argument above only holds
-- because READ COMMITTED takes a FRESH snapshot per statement, so once `for update` unblocks
-- (the concurrent inserter has committed), the following `select ... from source_document`
-- sees that commit. Under REPEATABLE READ/SERIALIZABLE, the whole transaction's snapshot is
-- fixed at its first query, so that same select could still miss a row that committed after
-- this transaction started, even though the lock correctly waited for it. Not pinned inside
-- this function: `SET TRANSACTION ISOLATION LEVEL` is only legal before ANY query has run in
-- the transaction, and PostgREST (like this repo's own sign_in_as test harness) already runs
-- `SET LOCAL ROLE`/claims setup first — attempting it here risks a confusing runtime error
-- for a scenario nothing in this stack currently creates (Postgres/Supabase default to READ
-- COMMITTED; nothing here raises it). Documented instead of "fixed": if `authenticated`'s
-- default isolation is ever changed, this function's race-closure needs re-verifying then.
--
-- SECURITY INVOKER (the default — see 0001/0002/0003's functions, NOT 0004's exception):
-- unlike keystone_save_system_model, this function is NOT becoming the only way to write
-- `project`/`source_document` — `authenticated`'s existing direct grants there (0001) are
-- left as-is; this is an additional atomic path for the one specific operation (collect URIs
-- + delete) that needs one. Running as the caller means RLS applies exactly as it already
-- does for a direct `DELETE FROM project` or `SELECT FROM source_document`: a project outside
-- the caller's own tenant is invisible to both statements, so this function needs no explicit
-- tenant check of its own (contrast 0004, which bypasses RLS by necessity and therefore must
-- check the tenant itself).
--
-- Depends on: 0001 (project, source_document). Independent of 0002-0005.

begin;

create or replace function keystone_delete_project(p_project_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_uris          text[];
  v_deleted_count int;
begin
  -- Lock the project row FIRST (see LOCKING above) -- this is what actually closes the
  -- race, not just being "one function call." A no-op (0 rows) when the project doesn't
  -- exist or belongs to another tenant (RLS), same as every statement below.
  perform 1 from project where id = p_project_id for update;

  -- Read BEFORE delete, in the same transaction as the delete below — the whole point of
  -- this being one function call instead of two REST calls.
  select coalesce(array_agg(uri), array[]::text[])
    into v_uris
    from source_document
    where project_id = p_project_id;

  delete from project where id = p_project_id;
  get diagnostics v_deleted_count = row_count;

  return jsonb_build_object(
    'project_deleted', v_deleted_count > 0,
    'source_document_uris', to_jsonb(v_uris)
  );
end;
$$;

comment on function keystone_delete_project(uuid) is
  'ADR-005 §5 (issue #21 "Milestone 6"): atomically collects the source_document.uri values '
  'a project references and deletes the project row (which cascades to every project_id-'
  'scoped table, 0001) -- one function call = one transaction, closing the read-then-delete '
  'race a two-call Python implementation would have. SECURITY INVOKER: RLS applies exactly '
  'as it would to either statement run directly, so a cross-tenant project_id is silently '
  'invisible to both (project_deleted: false), same as any other RLS-scoped DML.';

revoke execute on function keystone_delete_project(uuid) from public, anon, service_role;
grant execute on function keystone_delete_project(uuid) to authenticated;

commit;
