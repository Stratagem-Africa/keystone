-- 0004_model_store_save_rpc.sql
--
-- Issue #21 Milestones 4+5 — save_model()'s atomic "insert new version + move head" pair
-- (ADR-005 §2: "the (INSERT system_model …; UPDATE project SET head_model_version …) pair
-- runs in one transaction"). Race-safe version numbers are already built (0001's
-- keystone_assign_system_model_version trigger + the (project_id, version) PK) — the one
-- remaining piece is application code atomically doing both statements, which only Postgres
-- itself can guarantee through PostgREST (supabase-py's client is one-REST-call-per-
-- statement, no client-side multi-statement transaction). A single function call IS one
-- implicit transaction, so this function is that atomic unit — called via SupabaseModelStore
-- through `.rpc("keystone_save_system_model", ...)`.
--
-- SECURITY DEFINER, not INVOKER (changed after review on issue #21, ruled by Bifola
-- 2026-09-10 — see that thread for the full reasoning): this function is now the ONLY way
-- to write system_model/component/flow/flow_step/assumption at all — `authenticated`'s
-- direct insert/update/delete on those tables is REVOKED below. That only works if this
-- function runs with MORE privilege than the caller has, i.e. SECURITY DEFINER (as the
-- function's owner, not the calling role). `search_path` is explicitly pinned
-- (`public, pg_temp`) — the classic SECURITY DEFINER footgun is an unqualified name inside
-- the function resolving against a schema the CALLER controls (e.g. a hostile
-- `create schema evil; set search_path = evil, public;` before calling this), letting an
-- attacker's own same-named object run with this function's elevated rights. Pinning
-- search_path closes that off entirely — `pg_catalog` is always implicitly searched first
-- by Postgres regardless of this setting, so built-in functions/operators can't be
-- shadowed this way either.
--
-- Because SECURITY DEFINER functions typically run as a role with BYPASSRLS (whoever owns
-- them, usually the migration-applying admin role), RLS can NOT be relied on inside this
-- function's body the way every SECURITY INVOKER function/trigger in 0001/0002 relies on
-- it — this function must do its OWN explicit tenant check instead (see below), reading
-- the tenant straight from the caller's JWT claim (`keystone_current_tenant()`, 0001) —
-- never a client-supplied value, since nothing in this function's parameter list accepts
-- one — rather than trusting an implicit RLS-filtered row visibility that no longer applies
-- once this runs as an elevated role.
--
-- Depends on: 0001 (all the tables + triggers this inserts into/relies on). Apply after it
-- (and after 0002/0003, which this doesn't depend on but follows in sequence).

begin;

-- Preserve SystemModel.flows / .assumptions list ORDER. Dataclass equality on both is
-- order-sensitive (they're plain Python lists), but 0001 had no column for either — only
-- flow_step.step_order existed, preserving order WITHIN one flow's path, not the flows list
-- itself. Without this, a round-trip through Postgres could silently reorder either list and
-- still "look" correct by content while failing strict equality — exactly the kind of gap
-- ADR-005 §6a's round-trip requirement exists to catch.
alter table flow       add column flow_order       int not null default 0;
alter table assumption add column assumption_order int not null default 0;

-- Backfill for pre-existing rows (saved under 0001-0003, before this column existed): a
-- flat DEFAULT 0 alone would leave every flow/assumption in a given (project_id,
-- model_version) snapshot TIED at 0, so a subsequent `ORDER BY flow_order` has no stable
-- tiebreak and could silently reorder them differently on every reload — reintroducing,
-- for old data, the exact bug this migration exists to fix. There is no way to recover the
-- TRUE original insertion order retroactively (nothing tracked it before now), but
-- row_number() over a stable, always-unique key (id) at least makes the backfilled order
-- deterministic and reload-stable, which is strictly better than an unbroken tie. New rows
-- going forward get their real order stamped by keystone_save_system_model's loop counter
-- below, not this default.
update flow set flow_order = sub.rn - 1
from (select id, row_number() over (partition by project_id, model_version order by id) as rn from flow) sub
where flow.id = sub.id;

update assumption set assumption_order = sub.rn - 1
from (select id, row_number() over (partition by project_id, model_version order by id) as rn from assumption) sub
where assumption.id = sub.id;

create or replace function keystone_save_system_model(
  p_project_id uuid,
  p_name text,
  p_domain_flags text[],
  p_system_rps double precision,
  p_workload_description text,
  p_egress_micro_usd_per_gb bigint,
  p_storage_micro_usd_per_gb_month bigint,
  p_request_micro_usd_per_thousand bigint,
  p_llm_input_micro_usd_per_1k_tokens bigint,
  p_llm_output_micro_usd_per_1k_tokens bigint,
  p_compute_pricing text,
  p_pricing_groundings jsonb,
  -- Each element shaped like Component's 13 fields (model.py:40-73), serialized by
  -- SupabaseModelStore — see that module for the exact key names.
  p_components jsonb,
  -- Each element: {name, share, path: [{component_id, visit_prob}, ...]} (Flow/FlowStep,
  -- model.py:142-152).
  p_flows jsonb,
  -- Each element shaped like Assumption's fields (model.py:161-167).
  p_assumptions jsonb
)
returns int
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_caller_tenant_id uuid;
  v_parent_version   int;
  v_tenant_id        uuid;
  v_version          int;
  v_share_total      double precision;
  v_component_ids    text[];
  v_referenced_ids   text[];
  v_component        jsonb;
  v_flow             jsonb;
  v_flow_id          uuid;
  v_flow_idx         int := 0;
  v_step             jsonb;
  v_step_order       int;
  v_assumption       jsonb;
  v_assumption_idx   int := 0;
begin
  -- The tenant check RLS would have given us for free under SECURITY INVOKER — now done
  -- explicitly, since SECURITY DEFINER runs as an elevated role RLS typically doesn't bind.
  -- keystone_current_tenant() (0001) reads the caller's JWT claim via a SESSION-level GUC
  -- (request.jwt.claims), which is unaffected by SECURITY DEFINER's role change — GUCs are
  -- session state, not privilege state — so this still reflects the ACTUAL calling client,
  -- never something this function's own elevated identity could spoof.
  v_caller_tenant_id := keystone_current_tenant();

  -- Lock the project row for the rest of this transaction: serializes concurrent
  -- save_model calls on the SAME project (a single-row lock — does not serialize across
  -- different projects) so two racing saves can't both read the same head_model_version
  -- and stomp each other's update at the end. The `and tenant_id = v_caller_tenant_id`
  -- filter is now THIS function's own tenant check (see the header comment) — STRICT
  -- (not a plain select): a project that doesn't exist, or exists but belongs to a
  -- different tenant than the caller's own claim, gives a clean, well-understood
  -- NO_DATA_FOUND — the same fail-closed pattern already established by every SECURITY
  -- INVOKER derivation trigger in 0001, just enforced explicitly here instead of via RLS.
  select head_model_version
    into strict v_parent_version
    from project
    where id = p_project_id and tenant_id = v_caller_tenant_id
    for update;
  v_tenant_id := v_caller_tenant_id;

  -- Structural validation moved IN from Python's validate_model() (ingestion.py), now that
  -- this function is the SOLE write path (Bifola's ruling, issue #21, 2026-09-10) — these
  -- are exactly the "cannot be a column constraint" cross-row invariants ADR-005 §6 already
  -- named (empty checks, flow-shares-sum-to-~1, orphan components). SupabaseModelStore.
  -- save_model() still calls Python's validate_model() first too, for a cleaner/earlier
  -- error on the common path — this is defense in depth, not a replacement: a caller that
  -- reaches this function directly (raw SQL, a future client, a bug in the Python wrapper)
  -- still cannot get a structurally invalid model past it.
  if jsonb_array_length(p_components) = 0 then
    raise exception 'model has no components';
  end if;
  if jsonb_array_length(p_flows) = 0 then
    raise exception 'model has no flows -- the engine has no path to simulate';
  end if;

  select coalesce(sum((f ->> 'share')::double precision), 0)
    into v_share_total
    from jsonb_array_elements(p_flows) f;
  if v_share_total < 0.9 or v_share_total > 1.1 then
    raise exception 'flow shares sum to %, expected ~1.0', v_share_total;
  end if;

  for v_flow in select * from jsonb_array_elements(p_flows) loop
    -- `v_flow -> 'path'` is SQL NULL when the 'path' key is ABSENT (not merely an empty
    -- array) — and jsonb_array_length(NULL) is itself NULL, which an IF treats as false,
    -- so the check below would silently never fire for a flow missing 'path' entirely
    -- (verified against real Postgres by independent review — the flow was inserted with
    -- zero flow_steps and no exception at all). The explicit `is null` check closes that;
    -- a 'path' key present but holding a JSON `null` still fails, just with an uglier
    -- "cannot get array length of a scalar" error instead of this clean message.
    if v_flow -> 'path' is null or jsonb_array_length(v_flow -> 'path') = 0 then
      raise exception 'flow % has an empty path', v_flow ->> 'name';
    end if;
  end loop;

  select array_agg(c ->> 'id') into v_component_ids from jsonb_array_elements(p_components) c;
  -- `where ... is not null` excludes any flow_step missing component_id from the
  -- aggregate up front: in SQL, comparing anything against an array CONTAINING a NULL
  -- element (`cid <> all ('{app,NULL}')`) evaluates to NULL, not true/false — silently
  -- disabling the orphan check below for EVERY component, not just one related to the
  -- malformed row (verified against real Postgres by independent review). Filtering NULL
  -- out here, rather than coalescing the whole array afterward, is what actually fixes it.
  select array_agg(distinct s ->> 'component_id')
    into v_referenced_ids
    from jsonb_array_elements(p_flows) f, jsonb_array_elements(f -> 'path') s
    where s ->> 'component_id' is not null;

  if exists (
    select 1 from unnest(v_component_ids) cid
    where cid <> all (coalesce(v_referenced_ids, array[]::text[]))
  ) then
    raise exception 'component(s) on no flow -- wire each into a flow, or remove it';
  end if;

  -- The reverse check (ADR-002/ingestion.py:402-404's validate_model() performs this):
  -- every component_id a flow_step references must actually exist among p_components.
  -- Without this, a typo'd id only surfaced later as a raw ForeignKeyViolation on the
  -- flow_step insert further down — still correctly fails closed, but a worse error than
  -- this clean message, and asymmetric with the orphan check just above it.
  if exists (
    select 1 from unnest(v_referenced_ids) rid
    where rid <> all (coalesce(v_component_ids, array[]::text[]))
  ) then
    raise exception 'a flow references a component id not present in this model';
  end if;

  insert into system_model (
    project_id, parent_version, tenant_id, name, domain_flags, system_rps,
    workload_description, egress_micro_usd_per_gb, storage_micro_usd_per_gb_month,
    request_micro_usd_per_thousand, llm_input_micro_usd_per_1k_tokens,
    llm_output_micro_usd_per_1k_tokens, compute_pricing, pricing_groundings
  ) values (
    p_project_id, v_parent_version, v_tenant_id, p_name, p_domain_flags, p_system_rps,
    p_workload_description, p_egress_micro_usd_per_gb, p_storage_micro_usd_per_gb_month,
    p_request_micro_usd_per_thousand, p_llm_input_micro_usd_per_1k_tokens,
    p_llm_output_micro_usd_per_1k_tokens, p_compute_pricing, p_pricing_groundings
  )
  returning version into v_version;   -- trigger-assigned (0001), race-free per project

  -- Components first: flow_step's composite FK needs them to already exist before any
  -- flow referencing them is inserted.
  for v_component in select * from jsonb_array_elements(p_components) loop
    insert into component (
      id, project_id, model_version, kind, name, per_instance_rps, instances,
      base_latency_ms, monthly_cost_per_instance, egress_gb_per_month, storage_gb,
      requests_per_month, llm_input_tokens_per_month, llm_output_tokens_per_month,
      provenance, groundings, match_context
    ) values (
      v_component ->> 'id', p_project_id, v_version, (v_component ->> 'kind')::component_kind,
      v_component ->> 'name', (v_component ->> 'per_instance_rps')::double precision,
      (v_component ->> 'instances')::int, (v_component ->> 'base_latency_ms')::double precision,
      (v_component ->> 'monthly_cost_per_instance')::bigint,
      (v_component ->> 'egress_gb_per_month')::bigint, (v_component ->> 'storage_gb')::bigint,
      (v_component ->> 'requests_per_month')::bigint,
      (v_component ->> 'llm_input_tokens_per_month')::bigint,
      (v_component ->> 'llm_output_tokens_per_month')::bigint,
      v_component ->> 'provenance',
      coalesce(v_component -> 'groundings', '{}'::jsonb),
      coalesce(v_component -> 'match_context', '{}'::jsonb)
    );
  end loop;

  for v_flow in select * from jsonb_array_elements(p_flows) loop
    insert into flow (project_id, model_version, name, share, flow_order)
    values (p_project_id, v_version, v_flow ->> 'name', (v_flow ->> 'share')::double precision, v_flow_idx)
    returning id into v_flow_id;

    v_step_order := 0;
    for v_step in select * from jsonb_array_elements(v_flow -> 'path') loop
      insert into flow_step (flow_id, component_id, step_order, visit_prob)
      values (v_flow_id, v_step ->> 'component_id', v_step_order,
              (v_step ->> 'visit_prob')::double precision);
      v_step_order := v_step_order + 1;
    end loop;
    v_flow_idx := v_flow_idx + 1;
  end loop;

  for v_assumption in select * from jsonb_array_elements(p_assumptions) loop
    insert into assumption (
      project_id, model_version, subject, statement, confidence, source, provenance,
      assumption_order
    ) values (
      p_project_id, v_version, v_assumption ->> 'subject', v_assumption ->> 'statement',
      v_assumption ->> 'confidence', v_assumption ->> 'source', v_assumption ->> 'provenance',
      v_assumption_idx
    );
    v_assumption_idx := v_assumption_idx + 1;
  end loop;

  update project set head_model_version = v_version where id = p_project_id;

  return v_version;
end;
$$;

-- Same "REVOKE ALL then explicit GRANT" hygiene 0001's grants section established (a
-- GRANT-only block can't prove the resulting privilege set is minimal, regardless of
-- whatever a project's default function privileges happen to be).
revoke execute on function keystone_save_system_model(
  uuid, text, text[], double precision, text, bigint, bigint, bigint, bigint, bigint, text,
  jsonb, jsonb, jsonb, jsonb
) from public, anon, service_role;
grant execute on function keystone_save_system_model(
  uuid, text, text[], double precision, text, bigint, bigint, bigint, bigint, bigint, text,
  jsonb, jsonb, jsonb, jsonb
) to authenticated;

-- CLOSES THE GAP (Bifola's ruling on issue #21, 2026-09-10 — the earlier draft of this
-- migration left this open, flagged, and asked; his answer was option (b), close it now):
-- `authenticated` had direct `insert` on system_model/component/flow/flow_step/assumption
-- from 0001 (lines 612-614), which meant a client could store a structurally-invalid model
-- as a runnable version by skipping this RPC entirely — RLS stopped cross-tenant writes,
-- but did nothing to stop an INVALID write inside a caller's own tenant, which is exactly
-- what ADR-005 §6 ("an invalid model can never be stored as a runnable version") promises.
-- With this function now SECURITY DEFINER (it runs with more privilege than `authenticated`
-- has, regardless of what's revoked here), it remains the only way these tables get
-- written; `select` is untouched, so ordinary reads are unaffected.
--
-- NOTE, deliberately NOT closed here, and meaningfully smaller than the gap above: authenticated
-- still has full CRUD on `project` (0001 line 610), including `head_model_version`. But
-- with the snapshot tables now locked to this RPC alone, the worst that grant can do is let
-- a caller point their OWN project's head at a DIFFERENT ALREADY-VALID version of their own
-- data (every system_model row that exists was created through this validated RPC) or at a
-- nonexistent version number (self-inflicted breakage of their own get_model("head") call —
-- no invalid data is ever exposed either way). That's a different, much lower-stakes
-- question ("should a user be able to manually repoint their own head outside save_model()")
-- than the one Bifola's ruling answered (can a client store an INVALID model as runnable) —
-- not addressed here, flagged so it isn't silently treated as already settled.
revoke insert, update, delete on system_model, component, flow, flow_step, assumption
  from authenticated;

commit;
