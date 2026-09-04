-- 0004_jobs_arch_map.sql
--
-- Issue #183: wire keystone.arch_map.build_arch_map() into the /intent result instead of only
-- storing the markdown report. Adds a column to hold the engine-driven architecture-map JSON
-- alongside the existing markdown `result`. No RLS/policy change needed -- 0003's `own_jobs`
-- policy already scopes the whole row (every column) to `user_id = auth.uid()`.

begin;

alter table jobs add column arch_map jsonb;

commit;
