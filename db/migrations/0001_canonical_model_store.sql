-- 0001_canonical_model_store.sql
--
-- Issue #21 (docs/08 Epic 5.2) — the canonical model store: A (Bifola) designed the spec in
-- ADR-005 (docs/adr/ADR-005-canonical-model-store.md, ratified 2026-06-19; reconciled to
-- current model.py in §6a, 2026-08-03, adjudicated on issue #21); this file is J's (Jem's)
-- migration that turns that spec into tables.
--
-- Scope (matches Epic 5.2 / ADR-005 exactly — NOT the wider docs/05 sketch): the model store
-- itself — tenant, membership, project, system_model + its snapshot children (component, flow,
-- flow_step, assumption), source_document, and simulation_run. `adr`, `reconciliation_report`,
-- and `calibration_record` (docs/05 §2) are real future tables but ADR-005 never specifies them
-- and Epic 5.2's own scope line is "canonical-model-store schema" — building them now would be
-- guessing at an unratified shape. Left as a GAP for their own epic/ADR.
--
-- Two engineering rules govern every choice below (both from ADR-005, ratified):
--   1. Tenant isolation is deny-by-default Row-Level Security, not app-layer filtering we could
--      forget to apply (§1). Every table carries tenant_id; RLS is ENABLE + FORCE + one policy.
--   2. Every model.py field is persisted, nothing dropped (§6/§6a) — the storage rule is
--      "engine-read or money -> typed column; evidence the engine never reads -> jsonb".

begin;

-- =====================================================================================
-- 0. component_kind — a native enum mirroring keystone.model.ComponentKind exactly.
--    ADR-005 §6: "component.kind as a Postgres enum ... out-of-scope kinds rejected, not
--    coerced" (the v1 single-region scope freeze — CLAUDE.md "What NOT to do").
-- =====================================================================================
create type component_kind as enum (
  'client', 'cdn', 'load_balancer', 'api_gateway', 'app_server',
  'cache', 'sql_db', 'replica', 'queue', 'object_store', 'external_api'
);

-- =====================================================================================
-- 1. tenant — the thing tenant_id actually points at. Not named in ADR-005's decision
--    text (which assumes tenant_id exists); membership + RLS both need a real row to
--    reference, so this is the minimal table that gives them one. (Flagged as latitude
--    in the PR — ADR-005 doesn't rule on tenant's own shape.)
-- =====================================================================================
create table tenant (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_at timestamptz not null default now()
);

-- =====================================================================================
-- 2. membership — maps a Supabase-Auth user to a tenant + role. This is the table the
--    custom-access-token hook (ADR-005 §1, "MUST be injected ... by a Supabase
--    custom-access-token auth hook that reads the user's tenant_id from membership")
--    reads to populate the tenant_id JWT claim every other table's RLS policy depends on.
--
--    GAP (flagged on issue #21, not built here): ADR-005's build-plan bundles "the
--    tenant_id custom-access-token hook" into this same migration deliverable, but the
--    hook function itself is NOT included below — deferred, pending Bifola (auth +
--    tenant-isolation is his trust-critical lane, CLAUDE.md's Review->Verify->Adjudicate
--    gate). Consequence: until the hook exists and is registered (Auth -> Hooks in the
--    Supabase dashboard — not something a migration file can do), auth.jwt()->>'tenant_id'
--    is null for every request, so every RLS policy below denies every row to every user
--    (the accidental-fail-closed ADR-005 §1 warns about — not a bug, just incomplete).
--    This also means ADR-005's REQUIRED gate item — "signed in as tenant A, zero of B's
--    rows on select/insert/update/delete" — cannot be run yet either; it needs the hook
--    first. Tables + RLS + triggers below are otherwise complete and can be reviewed now.
-- =====================================================================================
create table membership (
  user_id    uuid not null references auth.users(id) on delete cascade,
  tenant_id  uuid not null references tenant(id) on delete cascade,
  -- Role values aren't specified in ADR-005 — minimal 2-value set, latitude, flagged in PR.
  role       text not null check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  primary key (user_id, tenant_id)
);

-- =====================================================================================
-- 3. project — the folder that owns a design's version history (system_model rows) plus
--    its uploaded source documents. head_model_version's real FK is added further down,
--    once system_model exists (see step 4b) — a plain circular-reference problem: project
--    needs to point at system_model, but system_model needs to point back at project.
-- =====================================================================================
create table project (
  id                  uuid primary key default gen_random_uuid(),
  tenant_id           uuid not null references tenant(id),
  owner_id            uuid not null references auth.users(id),
  name                text not null,
  status              text not null default 'active'
                        check (status in ('active', 'archived')),
  -- ADR-005 §5: per-project retention mode; ephemeral = raw source bytes deleted
  -- synchronously before ingest() returns. High-stakes domain_flags default here to
  -- 'ephemeral' at the APPLICATION layer (SystemModel.domain_flags doesn't exist until
  -- the first system_model row is saved, so the migration can't enforce that default).
  retention_mode      text not null default 'retain'
                        check (retention_mode in ('retain', 'ephemeral')),
  head_model_version  int,
  created_at          timestamptz not null default now()
);

-- =====================================================================================
-- 4. system_model — one immutable, append-only snapshot per version (ADR-005 §2).
--    Component/Flow/Workload/PricingRates all live inside this snapshot; workload and
--    pricing are inlined as columns (1:1 value objects, no join needed) rather than
--    given their own tables — ADR-005 §6a explicitly leaves this shape ("on system_model
--    (recommended) or its own table") to the migration owner for pricing; same latitude
--    call extended to workload here, flagged in the PR.
-- =====================================================================================
create table system_model (
  project_id          uuid not null references project(id) on delete cascade,
  version             int not null,
  parent_version      int,  -- null only for a project's first version
  tenant_id           uuid not null references tenant(id),
  name                text not null,
  -- SystemModel.domain_flags: list[str], e.g. "high_stakes:elections" (model.py:233).
  -- Not money, not engine-read as a number -> a typed array is enough, no jsonb needed.
  domain_flags        text[] not null default '{}',
  -- Workload (model.py:156-158), inlined:
  system_rps          double precision not null check (system_rps > 0),
  workload_description text not null default '',
  -- PricingRates (model.py:186-208) — money, so typed columns not jsonb (ADR-005 §6a
  -- ruling 3: "the money kill-criterion forbids float/unscaled money anywhere, including
  -- inside a JSON column" — a CHECK can guard a column; it can't cheaply guard a value
  -- buried three levels into a JSON blob). Unit is MICRO-USD, not cents — labelled below
  -- so nobody accidentally stores cents here (simulation_run.monthly_cost is cents; these
  -- rates stay micro-USD for sub-cent precision, per model.py:189-190).
  egress_micro_usd_per_gb              bigint not null check (egress_micro_usd_per_gb >= 0),
  storage_micro_usd_per_gb_month       bigint not null check (storage_micro_usd_per_gb_month >= 0),
  request_micro_usd_per_thousand       bigint not null check (request_micro_usd_per_thousand >= 0),
  llm_input_micro_usd_per_1k_tokens    bigint not null check (llm_input_micro_usd_per_1k_tokens >= 0),
  llm_output_micro_usd_per_1k_tokens   bigint not null check (llm_output_micro_usd_per_1k_tokens >= 0),
  -- Mirrors model.py's COMPUTE_PRICING_RETAINED_BP keys exactly (model.py:178-183) so a
  -- bad value fails closed at the DB, not just in Python.
  compute_pricing      text not null default 'on_demand'
                          check (compute_pricing in ('on_demand', 'reserved_1yr', 'reserved_3yr', 'spot')),
  -- PricingRates.groundings: evidence, engine never reads it -> jsonb (ADR-005 §6a ruling 2/3).
  pricing_groundings   jsonb not null default '{}',
  -- FIX (review 🟡 #6): ADR-005 §4 pairs every persisted money value with a currency code —
  -- these 5 rate columns are money and were missing it. Same USD-only-v1 default as component.
  currency             char(3) not null default 'USD',
  created_at           timestamptz not null default now(),
  -- The primary key below IS the race guard the version trigger relies on (a second,
  -- explicit UNIQUE on the same two columns would just build a redundant duplicate index).
  primary key (project_id, version),
  foreign key (project_id, parent_version) references system_model (project_id, version)
);

-- Version assignment (ADR-005 §2: "must be race-free ... two concurrent saves must never
-- collide on a version number"). Native Postgres IDENTITY can't auto-increment scoped
-- PER PROJECT (it's a whole-table sequence), so: a trigger computes MAX(version)+1 when
-- the app doesn't supply one, and the UNIQUE(project_id, version) constraint above is the
-- actual race guard — a genuine concurrent collision raises unique_violation (23505)
-- instead of silently duplicating a version, and the app (SupabaseModelStore) retries.
create function keystone_assign_system_model_version()
returns trigger
language plpgsql
security invoker
as $$
begin
  if new.version is null then
    select coalesce(max(version), 0) + 1 into new.version
    from system_model
    where project_id = new.project_id;
  end if;
  return new;
end;
$$;

create trigger trg_assign_system_model_version
  before insert on system_model
  for each row
  execute function keystone_assign_system_model_version();

-- 4b. Now that system_model exists, close the circular reference from project.
alter table project
  add constraint project_head_model_version_fkey
  foreign key (id, head_model_version) references system_model (project_id, version);

-- =====================================================================================
-- Tenant-derivation triggers (harm floor, going beyond ADR-005's literal text but in its
-- spirit — §1: "deny-by-default RLS ... not application-layer filtering we can forget to
-- apply"). Every child table below carries its own tenant_id column (ADR-005 §1: "every
-- domain table"), denormalised for fast RLS policy evaluation without a join. But a
-- denormalised column an app could set independently is exactly the kind of thing that
-- could drift or be gotten wrong once, silently, so instead of trusting the app to always
-- copy it correctly, a BEFORE INSERT/UPDATE trigger derives it from the parent row every
-- time and overwrites whatever the app sent. tenant_id can never disagree with its
-- parent's tenant, by construction, not by discipline.
-- =====================================================================================
-- `security invoker` made explicit on this and every other tenant/scope-derivation trigger
-- below (matches what the review already confirmed by running it: SECURITY INVOKER is what
-- makes a hidden cross-tenant parent fail closed — the lookup runs as the CALLING role,
-- subject to that role's own RLS, not as whoever owns the function).
create function keystone_derive_tenant_from_project()
returns trigger
language plpgsql
security invoker
as $$
begin
  select tenant_id into strict new.tenant_id from project where id = new.project_id;
  return new;
end;
$$;

create function keystone_derive_tenant_from_system_model()
returns trigger
language plpgsql
security invoker
as $$
begin
  select tenant_id into strict new.tenant_id
  from system_model
  where project_id = new.project_id and version = new.model_version;
  return new;
end;
$$;

-- =====================================================================================
-- 5. component — the real 13-field Component (model.py:40-73), reconciled in ADR-005
--    §6a (adjudicated on issue #21, not the ADR's original stale "eight typed fields").
-- =====================================================================================

-- The params jsonb bag's guard (ADR-005 §6/§6a): reject any key that LOOKS LIKE a
-- derived metric, so a hand-edited or LLM-emitted number can never sneak onto an input
-- row through the untyped path (prime directive, enforced by schema). A plain `?|` jsonb
-- operator only matches EXACT keys, but the ADR's intent is substring matching (e.g. an
-- "estimated_cost_usd" key should be rejected too) — and a CHECK constraint cannot itself
-- contain a subquery (Postgres: "CHECK expressions cannot contain subqueries"), so the
-- jsonb_object_keys() set-returning function has to be wrapped in an IMMUTABLE SQL
-- function first; the CHECK below just calls that function.
create function keystone_params_has_forbidden_key(p jsonb)
returns boolean
language sql
immutable
as $$
  -- FIX (review 🟡 #4): the original list (from ADR-005 §6 verbatim) missed several real
  -- SimulationResult field names (simulation.py:134-151) — p50_ms/p95_ms/p99_ms, spofs,
  -- confidence, headroom aren't caught by the original 8-term list, so a key like "p95"
  -- or "spof_count" could slip a derived value through. Bifola is widening ADR-005 §6 to
  -- match this list so the spec and the guard stay in lockstep.
  select exists (
    select 1 from jsonb_object_keys(p) as k
    where k ~* '(cost|capacity|latency|utiliz|throughput|breakpoint|bottleneck|rps|spof|headroom|confidence|p50|p95|p99|percentile|saturat)'
  );
$$;

-- FIX (review 🔴 #1+#2, both from the same root cause): Component.id is a Python str slug
-- (model.py:41 — real blueprints use "app"/"db"/"lb", not a UUID), so a bare `uuid` PK here
-- broke the lossless round-trip on the very first save. Making identity the FULL
-- (project_id, model_version, id) triple — not just `id` — does a second job too: it lets
-- flow_step's reference below be a COMPOSITE foreign key scoped to the same model snapshot,
-- which (via the tenant-derivation triggers already in place) means the same tenant, by
-- construction. A bare single-column FK to just `id` couldn't express that scoping — that
-- was the cross-tenant gap in #2. One shape change fixes both.
create table component (
  id             text not null,                 -- the Python str slug, e.g. "app" — NOT a uuid
  project_id     uuid not null,
  model_version  int not null,
  tenant_id      uuid not null references tenant(id),  -- derived by trigger below, not app-supplied
  kind           component_kind not null,
  name           text not null,
  per_instance_rps      double precision not null check (per_instance_rps > 0),
  instances             int not null default 1 check (instances >= 1),
  base_latency_ms       double precision not null default 1.0 check (base_latency_ms >= 0),
  -- Already int cents in model.py (ADR-008) — there is no float to convert (ADR-005 §6a
  -- ruling 4; the ADR's original §4 conversion-boundary note is stale, kept here as a
  -- pointer so nobody goes hunting for a conversion step that doesn't exist).
  monthly_cost_per_instance bigint not null default 0 check (monthly_cost_per_instance >= 0),
  -- FIX (review 🟡 #6): ADR-005 §4 pairs every persisted money value with a currency code —
  -- this migration originally omitted it. v1 is single-region/USD-only (CLAUDE.md scope
  -- freeze), so a fixed default closes the deviation without pretending we support
  -- multi-currency yet; a real multi-currency model is a GAP for a later ADR.
  currency                  char(3) not null default 'USD',
  -- +5 usage-billing fields (ADR-009 Tier 1, model.py:51-58) — money-driving ints
  -- (validated the same way as monthly_cost_per_instance at model.py:107-114), so they
  -- get the same typed-column + CHECK treatment, NOT jsonb (ADR-005 §6a ruling 1).
  egress_gb_per_month           bigint not null default 0 check (egress_gb_per_month >= 0),
  storage_gb                    bigint not null default 0 check (storage_gb >= 0),
  requests_per_month             bigint not null default 0 check (requests_per_month >= 0),
  llm_input_tokens_per_month     bigint not null default 0 check (llm_input_tokens_per_month >= 0),
  llm_output_tokens_per_month    bigint not null default 0 check (llm_output_tokens_per_month >= 0),
  -- Provenance enum per docs/03 (GROUNDED|GAP|ASSUMPTION, uppercase) — matches what every
  -- real blueprint (url_shortener.py, ticket_booking.py, payments.py) actually writes.
  -- FLAG (not yet Bifola-ruled, noted in the PR): model.py:59's dataclass default and a
  -- few ingestion.py call sites (lines 275, 416-418) use lowercase "assumption" instead —
  -- the same family of stale-default bug ADR-005 §3 already called out for
  -- Assumption.source, just on this field instead. Doesn't block this migration (no rows
  -- exist yet); it will bite whichever milestone first writes through those code paths.
  provenance     text not null default 'ASSUMPTION'
                   check (provenance in ('GROUNDED', 'GAP', 'ASSUMPTION')),
  -- +2 evidence fields (model.py:66,73) -> jsonb, own columns, deliberately kept OUT of
  -- params below: groundings is keyed by metric name (e.g. "per_instance_rps"), which
  -- would trip the params forbidden-key guard above even though it's evidence, not a
  -- derived value on the typed path (ADR-005 §6a ruling 2).
  groundings     jsonb not null default '{}',
  match_context  jsonb not null default '{}',
  -- Reserved forward-compat bag (ADR-005 §6) — empty today, nothing in Component maps
  -- here yet; exists so a future non-engine field doesn't need a migration to add.
  params         jsonb not null default '{}'
                   check (not keystone_params_has_forbidden_key(params)),
  -- FIX (review 🔴 #1+#2): identity is the whole snapshot-scoped triple, not just `id` —
  -- this IS the composite key flow_step's FK below relies on to stay inside one tenant.
  primary key (project_id, model_version, id),
  foreign key (project_id, model_version) references system_model (project_id, version) on delete cascade
);

create trigger trg_component_tenant
  before insert or update on component
  for each row
  execute function keystone_derive_tenant_from_system_model();

-- =====================================================================================
-- 6. flow — Flow.share (model.py:150-151). Sum-to-1 across a model's flows can't be a
--    column CHECK (it spans rows) — ADR-005 §6 explicitly assigns that to the
--    application layer's validate_model, before insert, fail-closed.
-- =====================================================================================
create table flow (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null,
  model_version  int not null,
  tenant_id      uuid not null references tenant(id),
  name           text not null,
  share          double precision not null check (share > 0 and share <= 1),
  foreign key (project_id, model_version) references system_model (project_id, version) on delete cascade
);

create trigger trg_flow_tenant
  before insert or update on flow
  for each row
  execute function keystone_derive_tenant_from_system_model();

-- =====================================================================================
-- 7. flow_step — Flow.path: list[FlowStep] (model.py:143-152). step_order preserves the
--    Python list's order, which a SQL table has no notion of on its own.
-- =====================================================================================
-- FIX (review 🔴 #2): component_id used to be a bare `uuid` FK straight to component(id).
-- FK checks bypass RLS (they run with elevated internal privilege), so that let a tenant-A
-- flow_step point at a tenant-B component: the insert only checked "does this UUID exist
-- ANYWHERE", never "does it belong to MY tenant/model" — a cross-tenant existence oracle,
-- and (via the old ON DELETE CASCADE) a way for tenant B deleting their own component to
-- silently delete tenant A's flow_step. project_id/model_version below (trigger-derived
-- from the parent flow, same pattern as tenant_id already used) let the FK further down be
-- scoped to "a component from THIS EXACT model snapshot" instead of "a component that
-- exists somewhere" — which is impossible to satisfy with another tenant's component,
-- because tenant_id is itself derived from (project_id, model_version) by construction.
create table flow_step (
  id            uuid primary key default gen_random_uuid(),
  flow_id       uuid not null references flow(id) on delete cascade,
  project_id    uuid not null,      -- derived by trigger below, from the parent flow
  model_version int not null,       -- derived by trigger below, from the parent flow
  component_id  text not null,      -- matches component.id's Python str slug, not a uuid
  tenant_id     uuid not null references tenant(id),  -- derived by trigger below
  step_order    int not null,
  visit_prob    double precision not null default 1.0 check (visit_prob >= 0 and visit_prob <= 1),
  -- THE fix: a composite FK, not a single-column one. component_id must belong to a
  -- component row with the SAME (project_id, model_version) as this flow_step — a
  -- cross-tenant/cross-model component_id can no longer satisfy this constraint at all,
  -- so the exploit in the comment above is now structurally impossible, not just
  -- RLS-checked.
  foreign key (project_id, model_version, component_id)
    references component (project_id, model_version, id) on delete cascade
);

-- Extended (review 🔴 #2) to derive project_id/model_version alongside tenant_id, all from
-- the same parent-flow lookup — one SELECT instead of three separate ones.
create function keystone_derive_flow_step_scope()
returns trigger
language plpgsql
security invoker
as $$
begin
  select tenant_id, project_id, model_version
    into strict new.tenant_id, new.project_id, new.model_version
  from flow
  where id = new.flow_id;
  return new;
end;
$$;

create trigger trg_flow_step_scope
  before insert or update on flow_step
  for each row
  execute function keystone_derive_flow_step_scope();

-- =====================================================================================
-- 8. assumption — Assumption (model.py:161-167).
-- =====================================================================================
create table assumption (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null,
  model_version  int not null,
  tenant_id      uuid not null references tenant(id),
  subject        text not null,
  statement      text not null,
  confidence     text not null default 'med' check (confidence in ('low', 'med', 'high')),
  -- Same stale-default family as component.provenance above: model.py:166 defaults
  -- source to "assumption", which is not a valid member of this enum (ADR-005 §3
  -- already flags this exact one). Default here is the DB's own safe fallback, not a
  -- statement that the stale value is acceptable — every real write must pass an
  -- explicit value.
  source         text not null default 'llm_inferred'
                   check (source in ('llm_inferred', 'benchmark', 'user')),
  provenance     text not null default 'ASSUMPTION'
                   check (provenance in ('GROUNDED', 'GAP', 'ASSUMPTION')),
  created_at     timestamptz not null default now(),
  foreign key (project_id, model_version) references system_model (project_id, version) on delete cascade
);

create trigger trg_assumption_tenant
  before insert or update on assumption
  for each row
  execute function keystone_derive_tenant_from_system_model();

-- =====================================================================================
-- 9. source_document — docs/05 §2; the ADR-002 no-retention/erasure MUST (ADR-005 §5)
--    binds the raw bytes in Storage/R2, not this row — this row is just the pointer +
--    the secret-scan result.
-- =====================================================================================
create table source_document (
  id                     uuid primary key default gen_random_uuid(),
  project_id             uuid not null references project(id) on delete cascade,
  tenant_id              uuid not null references tenant(id),  -- derived by trigger below
  type                   text not null
                           check (type in ('requirement', 'functional', 'ideation', 'diagram', 'voice', 'text')),
  -- Tenant-scoped Storage/R2 path, "{tenant_id}/{project_id}/..." (ADR-005 §5) — the raw
  -- bytes themselves live in Storage, never in Postgres.
  uri                    text not null,
  checksum               text not null,
  extracted_model_ref    int,   -- which system_model.version this document produced, if any
  assumption_ledger_ref  uuid,
  scanned_ok             boolean not null default false,  -- ADR-002 secret-scan, before LLM/logs
  created_at             timestamptz not null default now(),
  foreign key (project_id, extracted_model_ref) references system_model (project_id, version)
);

create trigger trg_source_document_tenant
  before insert or update on source_document
  for each row
  execute function keystone_derive_tenant_from_project();

-- =====================================================================================
-- 10. simulation_run — DERIVED, engine-only-writable (ADR-005 §1b/§3). This is the one
--     table the input-vs-derived boundary is enforced ON, not just described for:
--     no user JWT gets an INSERT/UPDATE grant here at all (see grants section below) —
--     only the service role, used exclusively by SupabaseModelStore after it asserts
--     project.tenant_id == caller.tenant_id (ADR-005 §1b's "verified tenant context").
--
--     ADR-005 names simulation_run's top-level fields but doesn't fully spec the nested
--     shape (components dict / flow_latencies / trace). FLAG (my own latitude call, not
--     yet Bifola-ruled, noted in the PR): headline scalars the report reads directly get
--     typed columns; everything nested/composite collapses into one `details` jsonb,
--     since none of it is re-read by the engine or needs a DB-level CHECK — it's already
--     the engine's own finished output, written once. Field names below match
--     simulation.py's SimulationResult exactly (simulation.py:134-151).
-- =====================================================================================
create table simulation_run (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null,
  model_version  int not null,
  tenant_id      uuid not null references tenant(id),
  engine_version text not null,
  seed           bigint not null,
  bottleneck_id           text not null,
  bottleneck_name         text not null,
  bottleneck_utilization  double precision not null check (bottleneck_utilization >= 0),
  breakpoint_rps_safe         double precision not null,
  breakpoint_rps_theoretical  double precision not null,
  mean_latency_ms  double precision not null,
  p50_ms           double precision not null,
  p95_ms           double precision not null,
  p99_ms           double precision not null,
  -- Integer cents (ADR-008) — the ENGINE'S money output, distinct unit from
  -- system_model's micro-USD RATES above (rates are per-unit; this is a rounded total).
  monthly_cost     bigint not null check (monthly_cost >= 0),
  -- FIX (review 🟡 #6): same ADR-005 §4 pairing, on the engine's own cost output this time.
  currency         char(3) not null default 'USD',
  spofs            text[] not null default '{}',
  confidence       text not null,
  -- components{} dict, flow_latencies[], caveats[], the computation trace — nested
  -- engine output, never re-read, never DB-validated; see the FLAG above.
  details          jsonb not null default '{}',
  created_at       timestamptz not null default now(),
  foreign key (project_id, model_version) references system_model (project_id, version) on delete cascade
);

create trigger trg_simulation_run_tenant
  before insert or update on simulation_run
  for each row
  execute function keystone_derive_tenant_from_system_model();

-- FIX (review 🟡 #5): (auth.jwt() ->> 'tenant_id')::uuid handles a MISSING claim fine (casts
-- NULL, every policy denies — correct fail-closed). But a PRESENT claim that isn't
-- UUID-shaped makes the ::uuid cast throw a hard Postgres error (22P02) instead of just
-- denying — "fail closed" should mean "cleanly no access", not "the query errors out".
-- This wraps that cast so any malformed claim degrades to NULL the same way a missing one
-- already does, instead of raising. `stable` (not `immutable`): auth.jwt() reads
-- session-local request state, so its result can differ between calls/sessions even
-- though it won't change twice within the same statement.
create function keystone_current_tenant()
returns uuid
language plpgsql
stable
as $$
begin
  return (auth.jwt() ->> 'tenant_id')::uuid;
exception
  when invalid_text_representation then
    return null;
end;
$$;

-- =====================================================================================
-- 11. Row-Level Security — deny-by-default on every table (ADR-005 §1). ENABLE + FORCE
--     binds the table OWNER to these policies too — but NOT roles carrying the BYPASSRLS
--     attribute (`postgres`, `service_role`): those skip row security entirely regardless
--     of FORCE (review nit #7 — my original comment here overstated this as "no
--     privileged-role bypass loophole", which isn't quite right). That's exactly why §1b's
--     service-role write path is guarded by an explicit application-layer tenant assertion
--     in SupabaseModelStore, not by RLS — RLS structurally cannot constrain that role.
--     No policy at all means zero rows readable or writable until the policy below exists.
--     One shape, repeated, EXCEPT tenant (predicate is its own id, not a tenant_id column)
--     and membership (a user reads their OWN memberships — that's how they discover which
--     tenant_id claim they should even have).
-- =====================================================================================

alter table tenant enable row level security;
alter table tenant force row level security;
create policy tenant_isolation on tenant
  using      (id = keystone_current_tenant())
  with check (id = keystone_current_tenant());

alter table membership enable row level security;
alter table membership force row level security;
create policy own_memberships on membership
  using      (user_id = auth.uid())
  with check (user_id = auth.uid());

alter table project enable row level security;
alter table project force row level security;
create policy tenant_isolation on project
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table system_model enable row level security;
alter table system_model force row level security;
create policy tenant_isolation on system_model
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table component enable row level security;
alter table component force row level security;
create policy tenant_isolation on component
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table flow enable row level security;
alter table flow force row level security;
create policy tenant_isolation on flow
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table flow_step enable row level security;
alter table flow_step force row level security;
create policy tenant_isolation on flow_step
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table assumption enable row level security;
alter table assumption force row level security;
create policy tenant_isolation on assumption
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table source_document enable row level security;
alter table source_document force row level security;
create policy tenant_isolation on source_document
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

alter table simulation_run enable row level security;
alter table simulation_run force row level security;
create policy tenant_isolation on simulation_run
  using      (tenant_id = keystone_current_tenant())
  with check (tenant_id = keystone_current_tenant());

-- =====================================================================================
-- 12. Grants — RLS decides which ROWS a role can see; grants decide which OPERATIONS a
--     role can attempt at all. tenant/membership are provisioned by an admin/signup flow
--     (out of this migration's scope), so `authenticated` only gets SELECT on those two.
--     system_model/component/flow/flow_step/assumption are the IMMUTABLE snapshot tables
--     (ADR-005 §2: "a change creates a new row"; corrections are new versions, never
--     edits) — `authenticated` gets SELECT + INSERT only, no UPDATE/DELETE, so that
--     guarantee is a DB privilege, not just an app-layer convention nobody violates yet.
--     project (mutable: name/status/retention_mode/head_model_version) and
--     source_document (an upload can be corrected or removed) keep full CRUD.
--     simulation_run is the one table where `authenticated` gets NO write grant
--     whatsoever (ADR-005 §1b: "a DB privilege, not just RLS") — only service_role, which
--     Supabase already exempts from RLS, can write it; SupabaseModelStore is the only
--     caller that uses that role, and only after asserting the tenant match itself.
-- =====================================================================================

-- FIX (review 🔴 #3): the block below used to be GRANT-only. GRANT is purely additive —
-- it can never take away a privilege a role already has from somewhere else (a Supabase
-- project's default table privileges vary by project history), so a GRANT-only block can
-- never actually PROVE the resulting privilege set is minimal. This REVOKE ALL first
-- forces every role in this migration down to an explicit, guaranteed-zero baseline, so
-- every GRANT below is provably the ENTIRE privilege set — not just an addition on top of
-- an unknown starting point.
revoke all on
  tenant, membership, project, system_model, component, flow, flow_step,
  assumption, source_document, simulation_run
  from anon, authenticated, service_role;

grant select on tenant, membership to authenticated;

grant select, insert, update, delete on project, source_document to authenticated;

grant select, insert on
  system_model, component, flow, flow_step, assumption
  to authenticated;

grant select on simulation_run to authenticated;
grant select, insert, update, delete on simulation_run to service_role;

-- FIX (review 🔴 #3, the missing half): trg_simulation_run_tenant runs AS whichever role
-- performs the insert, and its body SELECTs system_model to look up tenant_id (line ~197).
-- BYPASSRLS (which service_role carries) only skips ROW-level security — it does NOT skip
-- ordinary table-level GRANT checks. Without this explicit grant, the REVOKE ALL above
-- would leave that internal lookup with no privilege to run, breaking the one write path
-- that's supposed to work at all: the engine's own simulation_run insert. Also grants
-- SELECT on `project`, since SupabaseModelStore's §1b tenant assertion ("project.tenant_id
-- == caller.tenant_id", done before every service-role write) needs to read that column.
grant select on system_model, project to service_role;

commit;
