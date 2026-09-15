-- 0005_pin_search_path_and_allow_fanout.sql
--
-- Two fixes to 0001-0003, both found while reviewing PR #198 (issue #21 M4/M5), both in the
-- trust-critical core rather than the delivery layer — so Bifola's lane, not Jem's. Neither is a
-- defect she introduced; her PR is what made them visible.
--
-- ============================================================================================
-- PART 1 — PIN search_path ON EVERY FUNCTION THAT LACKS IT
-- ============================================================================================
--
-- 0004 pinned `search_path` on its new SECURITY DEFINER function and explained exactly why: an
-- unqualified name inside a function resolves against the CALLER's search_path, so a hostile
-- `create temp table project (...); set local search_path = pg_temp, public;` before the call makes
-- the function read the attacker's object instead of the real one.
--
-- Every other function in 0001-0003 has NO pin. Nine of them. Reproduced on Postgres 17 during the
-- #198 review: as tenant A, a pg_temp `project` table holding (B's project_id -> A's tenant_id),
-- then an INSERT of a `source_document` for B's project, returns a row tagged with A's tenant —
-- defeating the by-construction invariant 0001:180-182 claims ("tenant_id can never disagree with
-- its parent's tenant, by construction, not by discipline").
--
-- HOW BAD IS IT, HONESTLY: this is an INTEGRITY break, not a confidentiality one. The planted row
-- is tagged with the attacker's own tenant, so RLS still hides it from the victim and the attacker
-- learns nothing about the victim's data. And it is currently UNREACHABLE through the shipped
-- architecture, because PostgREST gives a client no way to run CREATE TEMP TABLE or SET
-- search_path — it is reachable only by something holding a raw SQL connection as `authenticated`.
-- So this is not an emergency. It is a latent hole that costs one line per function to close, and
-- leaving it means the invariant the schema advertises is true by luck rather than by construction.
--
-- ALTER FUNCTION, not CREATE OR REPLACE. The review suggested re-declaring each function with a
-- SET clause. That would mean restating nine bodies here, and every restatement is a chance to
-- silently drift from the original — a body that changes in 0001 later would leave two versions
-- disagreeing with no test to catch it. `alter function ... set search_path` attaches the pin to
-- the existing definition and touches nothing else, so the bodies stay in exactly one place.
--
-- `pg_catalog` is always searched first by Postgres regardless of this setting, so built-in
-- functions and operators cannot be shadowed this way either.

begin;

-- 0001 — the tenant/scope derivation triggers and the version assigner. `keystone_current_tenant`
-- matters most of the three: 0004's entire explicit tenant check calls it, so an unpinned one would
-- undermine the very function that was carefully pinned.
alter function keystone_assign_system_model_version()      set search_path = public, pg_temp;
alter function keystone_derive_tenant_from_project()       set search_path = public, pg_temp;
alter function keystone_derive_tenant_from_system_model()  set search_path = public, pg_temp;
alter function keystone_params_has_forbidden_key(jsonb)    set search_path = public, pg_temp;
alter function keystone_derive_flow_step_scope()           set search_path = public, pg_temp;
alter function keystone_current_tenant()                   set search_path = public, pg_temp;

-- 0002 — the auth hook runs as a Supabase-invoked function on every token mint.
alter function public.keystone_access_token_hook(jsonb)    set search_path = public, pg_temp;

-- 0003 — the jobs triggers. `keystone_derive_job_owner` is the one that stamps ownership, so it is
-- the same class of target as the tenant derivations above.
alter function keystone_derive_job_owner()                 set search_path = public, pg_temp;
alter function keystone_touch_job_updated_at()             set search_path = public, pg_temp;

-- ============================================================================================
-- PART 2 — ALLOW FAN-OUT: visit_prob > 1
-- ============================================================================================
--
-- `flow_step.visit_prob` is capped at 1 by 0001:348 (`check (visit_prob >= 0 and visit_prob <= 1)`).
-- That was correct when written: nothing on main used a value above 1, and the name reads like a
-- probability.
--
-- It is not a probability. The ENGINE treats it as the EXPECTED NUMBER OF VISITS per request
-- (`simulation.py`: `arr[step.component_id] += flow_rps * step.visit_prob`), and values above 1 are
-- load-bearing: a YouTube upload fans out to 6 rendition tasks, so the queue and the transcode
-- fleet are visited 6 times per upload. The reference library now carries 17 distinct values above
-- 1, up to 200. Under the old cap NONE of those designs could be saved — they simulate correctly
-- and then fail at persistence, which is the worst possible place to discover a modelling limit.
--
-- WHY AN UPPER BOUND AT ALL, and why 1000. Unbounded is not safe: arrival rate is multiplied by
-- this, so a single huge value silently inflates every downstream figure and could make one save
-- produce an arbitrarily expensive simulate(). 1000 is five times the largest value any real design
-- uses (200) with room to grow, and still finite.
--
-- KEEP IT TWO-SIDED. `NaN > 0` is TRUE in Postgres (NaN sorts above every float), so a one-sided
-- check cannot reject NaN — but `NaN <= 1000` is false, so the two-sided form does. That is the
-- same reasoning that already protects `share` at 0001:317, and it is why this relaxes the ceiling
-- rather than removing the check.
--
-- COORDINATION NOTE FOR #198: `model_store._validate_for_persistence()` enforces
-- `0 <= visit_prob <= 1` in Python, correctly mirroring the OLD constraint. That bound needs to
-- move with this one or fan-out designs still cannot be saved — the Python gate would simply reject
-- them earlier. Flagged on the PR; the Python side is Jem's to change, not mine to push onto her
-- branch.

alter table flow_step drop constraint if exists flow_step_visit_prob_check;
alter table flow_step add constraint flow_step_visit_prob_check
  check (visit_prob >= 0 and visit_prob <= 1000);

comment on column flow_step.visit_prob is
  'EXPECTED VISITS per request, not a probability. Below 1 models a conditional hop (a cache miss); '
  'above 1 models fan-out (one upload producing 6 transcode tasks). The engine multiplies arrival '
  'rate by it. Bounded at 1000 so one value cannot silently inflate every downstream figure; '
  'two-sided so NaN is rejected.';

commit;

-- RATIFICATION: this touches schema and tenant isolation, which CLAUDE.md puts behind
-- "adversarial Review -> Verify -> Adjudicate before code; a human ratifies". The review is done
-- (six lenses, #198). Bifola ratifies before this is applied to any live database.
