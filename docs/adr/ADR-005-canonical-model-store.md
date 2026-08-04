# ADR-005 — Canonical Model Store (versioned, tenant-isolated persistence)

**Status:** **Accepted** · **Ratified-by:** Bifola, 2026-06-19 (schema + tenant-isolation = the "a human ratifies before code" gate — satisfied)
**Date:** 2026-06-19 · **Owner:** Keystone A (Bifola) · **Migration owner:** Jem (delivery layer)
**Relates to:** `docs/05` (canonical data model — this turns its entity sketch into a storage spec), `docs/02` §6 (security MUSTs), `docs/03` §2 (prime directive) + pillars (provenance), ADR-002 (ingestion — which **explicitly defers** the tenant-isolation/no-retention MUST to this task), ADR-003 (Supabase + Fly topology), CLAUDE.md (harm floor; Tier-1; "Next" item)
**Implements:** GitHub issue **#21** (A designs spec → Jem migration). Blocks: real multi-tenant upload (ADR-002 kill-criterion) and the diff-able "design-as-code" promise.

---

## Context

Everything today is **in-memory**: `prototype/keystone/model.py` holds the canonical `SystemModel`, ingestion (ADR-002) targets it, and nothing is persisted. Two promises can't be kept without a store:

1. **Versioned, diff-able designs** (`docs/05` MUST — the "design-as-code" promise). A design must produce an immutable version on every change so two designs compare as a diff.
2. **Tenant-isolated, confidential storage** (`docs/02` §6 — a **Tier-1 day-one MUST**: tenant-isolated storage, no cross-tenant retrieval, encryption at rest/in transit, a no-retention mode). ADR-002 §4 deferred this *here* on the record: *"This MUST belongs to the canonical model-store task … and must land with it before any real multi-tenant upload."*

Three forces constrain the design:

- **The prime directive must survive persistence.** The store must not become a place where a derived metric (utilisation, bottleneck, breakpoint, latency, cost) can be written/edited as if it were an input. ADR-002's **input-vs-derived boundary** has to be expressed *in the schema*, not just in code.
- **Harm floor binds from first external traffic.** No cross-tenant read, no leaked credentials, no corrupted money, fail-closed. On a multi-tenant Postgres this means **deny-by-default row-level security**, not application-layer filtering we can forget to apply.
- **Free-tier / single-source-of-truth.** Supabase Postgres (ADR-003); the engine stays pure-stdlib; the store sits behind a seam (like the council/ingestor) so the offline loop keeps running $0.

> **Reading note for the migration owner (Jem):** where this ADR and `docs/05` disagree, **ADR-005 is the v1 implementation target**; `docs/05` is the aspirational data model and will be reconciled to this in a follow-up docs PR (money → integer minor units; `Edge` vs `Flow`; `Assumption.source`).
>
> **⚠️ Reconciliation (2026-08-03):** §4 and §6 below were written before **ADR-008** (integer money) and **ADR-009** (usage-based cost) landed, so their literal field list ("eight typed fields") and the `float→minor-units` conversion note are **stale**. The §6 *principle* — *persist the runnable `model.py` shape, every field, nothing dropped; lossless `model.py ↔ rows ↔ model.py` round-trip* — is unchanged and governs. Where this ADR and current `model.py` disagree, **`model.py` is the target.** The current field-by-field spec is in **[§6a — Reconciliation to `model.py`](#6a--reconciliation-to-modelpy-2026-08-03)** at the end; that is what the migration builds to.

## Decision

### 1. Postgres on Supabase; tenant isolation via **deny-by-default Row-Level Security (RLS)**

Every domain table carries `tenant_id uuid not null` (and `owner_id uuid`). RLS is **enabled and forced on every table with no permissive policy by default** — so absent an explicit policy, *no row is readable or writable*. The single policy shape, applied per table:

```sql
alter table system_model enable row level security;
alter table system_model force  row level security;        -- applies even to the table owner
create policy tenant_isolation on system_model
  using      (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)   -- rows you may read/update/delete
  with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);  -- rows you may insert/update
```

- The API (FastAPI on Fly, ADR-003) talks to Postgres **as the end user** (Supabase JWT, `auth.uid()` + a `tenant_id` claim) so RLS is in force on every query.
- **The `tenant_id` claim is not populated by Supabase by default** (a custom claim). It **MUST** be injected at token generation by a **Supabase custom-access-token auth hook** that reads the user's `tenant_id` from the `membership(user_id, tenant_id, role)` table. This hook **must be configured and tested before any live traffic** (part of Jem's #20/#21 work). *Without it the predicate `auth.jwt() ->> 'tenant_id'` is null and every policy denies every row — a silent, accidental fail-closed, not a designed one.*
- v1 may be one-user-per-tenant, but `tenant_id`, `membership`, and the policy exist **day one** so multi-tenant is correct by construction, not retrofitted.

#### 1b. Service-role / engine writes (the one path that bypasses RLS)

The **service-role key bypasses RLS** and is used only for trusted server-side work (migrations; the engine writing `simulation_run`). It is **never shipped to the browser and never used to serve a user request without an explicit tenant scope.** Because the *single* user-JWT policy above would also let a user pass `with check` on `simulation_run`, the **engine-only-writes-derived-metrics** guarantee (§3) is enforced **at the application layer, named here**: `SupabaseModelStore` (and only it) performs `simulation_run` writes via the service role *after* asserting `project.tenant_id == caller.tenant_id` ("verified tenant context" = this explicit lookup-and-assert). The user JWT path is given **no INSERT/UPDATE grant on `simulation_run`** (DB privilege, not just RLS), so a user cannot write a derived-metric row even with a valid `tenant_id`.

- **Harm-floor isolation test (a required gate item, before any real upload):** signed in as tenant A, every table returns **zero** of tenant B's rows on **select / insert / update / delete** (INSERT must be rejected by `with check`).

### 2. Versioning = **immutable, append-only snapshots** (atomic, race-free)

`system_model` versions are immutable. A change creates a **new row** (`version` monotonic per project, `parent_version` pointer); `project.head_model_version` moves to the new version. Each version owns an immutable snapshot of its `component[]`, `flow[]` (+ `flow_step[]`), `workload_profile`, and `assumption[]`. Diffs are computed on read (snapshots are small). `adr`, `simulation_run`, and `calibration_record` are **append-only** — corrections are new rows, never overwrites (`docs/05` MUST).

- **Version assignment must be race-free:** `version` is `GENERATED ALWAYS AS IDENTITY` per project (or, if application-computed, `SELECT max(version) … INSERT` runs in one `SERIALIZABLE` transaction). Two concurrent saves must never collide on a version number.
- **Head update must be atomic with the snapshot insert:** the `(INSERT system_model … ; UPDATE project SET head_model_version …)` pair runs in **one transaction**; failure of either rolls both back, so `head` never points at a stale or missing version.

### 3. The prime directive, **enforced by schema** (input-vs-derived boundary)

Carried verbatim from ADR-002 §"input-vs-derived": **inputs and derived outputs live in separate tables, and there is no column on an input table that can hold a derived metric.**

- **Input tables (user/ingestion-writable):** `system_model`, `component` (`per_instance_rps`, `instances`, `base_latency_ms`, `monthly_cost_per_instance` — these are *capacities/params*, i.e. inputs), `flow`/`flow_step`, `workload_profile` (`system_rps`, ratios), `assumption`.
- **Derived table (engine-writable ONLY — see §1b for enforcement):** `simulation_run` carries `engine_version`, `seed`, the `model_version` it ran against, and the outputs (bottleneck, breakpoint, p50/p95/p99, spofs, headroom, cost estimate) in immutable rows. **Written only by the engine path; never user-editable.** A row is reproducible from `(model_version, seed, engine_version)`.
- Result: there is structurally **nowhere** for a hand-edited or LLM-emitted derived metric to live on an input row, and every stored number that *is* derived is stamped with the engine + seed that produced it.
- **Provenance (`docs/03`):** `assumption.source ∈ {llm_inferred, benchmark, user}` and `provenance_tag ∈ {GROUNDED, GAP, ASSUMPTION}` per `docs/05` §2 (line 56). v1 ingestion writes `source=llm_inferred` (`ingestion.py:306`). *Note: `model.py:84` defaults `source="assumption"`, which is **out-of-spec** vs the docs/05 enum — normalise it (in `model.py` and on write) so a stored value is always one of the three.*

### 4. Money as **integer minor units** (harm floor) — refines `docs/05`

`docs/05` §1 says "money as decimal strings." The harm floor (CLAUDE.md) is stricter and **universal**: **integer minor units only.** This ADR overrides docs/05: **every** persisted monetary value — the `component.monthly_cost_per_instance` *input* **and** the `simulation_run` cost-estimate *output* — is stored as `bigint` **minor units** + `currency char(3)`. Never float, never a parseable-as-float string, **including inside any JSON column.**

- **The in-memory prototype is float** (`model.py:44` `monthly_cost_per_instance: float`; `simulation.py:121` float `monthly_cost`) — fine for the stdlib dev loop. The **harm floor binds the persisted schema**, so **Jem's migration / `SupabaseModelStore` is the conversion boundary**: float → `round(value * 100)` minor units on write, `÷100` on read.
- **Deterministic rounding:** convert with a single documented rule (round-half-even at write) so the reproducible-result equality in §2/§3 holds (the same model+seed always serialises to the same integer). The cost estimate is a *directional L0 figure*, not a billed amount — integer minor units is hygiene + harm-floor alignment + float-drift safety.

### 5. No-retention mode, encryption, erasure (ADR-002's deferred MUST)

- **Encryption (honest scope).** *At rest:* Supabase Postgres + Storage provide AES-256 encryption at rest — a **vendor SLA** ([Supabase security docs](https://supabase.com/docs/guides/security)), not something we implement. *In transit:* TLS 1.2+. The migration **confirms the setting is enabled in project config** (a config check) — it cannot itself "verify" a vendor's crypto. No application-layer encryption in v1.
- **Untrusted uploads stay untrusted.** Raw `source_document` bytes (which may carry commercially-sensitive content) live in tenant-scoped Storage/R2 paths (`{tenant_id}/{project_id}/…`) under the same ownership; ADR-002's secret-scan still redacts secrets *before* the LLM/logs.
- **No-retention mode:** a per-project `retention_mode {retain | ephemeral}`. In `ephemeral`, raw source bytes are deleted **synchronously before `ingest()` returns**; if the Storage delete fails, ingest **fails closed** with `ephemeral-cleanup-error` (raw bytes must never silently persist). The ingest response carries an observable `ephemeral_purged: bool` (the test hook), and a periodic audit job sweeps for any orphaned ephemeral object as a safety net. A high-stakes/sensitive `domain_flag` defaults `retention_mode` → `ephemeral`.
- **Erasure:** deleting a project **hard-deletes** all its DB rows (`on delete cascade`). DB cascade does **not** reach Storage — so a project-delete also fires a cleanup function (Fly job / Supabase Edge Function) that **idempotently deletes every object under `{tenant_id}/{project_id}/*`, logging success/failure**, with a test asserting a deleted project leaves **zero** Storage objects. Append-only is *within* a project's life; a project delete purges it — no lingering cross-project retention.

### 6. Round-trips `model.py` exactly; validated, fail-closed, on write

The store persists the **runnable** shape the engine consumes so `ingest → store → load → simulate` is loss-less and the model stays the single source of truth. The `component` table mirrors the real `model.py:36–45` `Component` dataclass — **eight typed fields**: `id, kind, name, per_instance_rps, instances, base_latency_ms, monthly_cost_per_instance, provenance` (there is **no** `params` field today). A `params jsonb` column **may be added as a reserved, forward-compat bag for non-engine metadata only** — if added, a migration `CHECK` **rejects any key matching `(cost|capacity|latency|utiliz|throughput|breakpoint|bottleneck|rps)`** so a derived/engine field can never sneak in off the typed path (preserving §3). Likewise persist `flow.share`, `flow_step.visit_prob`, `workload` fields, the full `assumption[]`, and `system_model.domain_flags` — every `model.py` field, nothing dropped.

**Validation on write — which layer enforces what:**
- **DB-enforced (in the migration):** FK references (every `flow_step.component_id` → a real `component`); positive-value `CHECK`s (`per_instance_rps > 0`, `instances >= 1`, costs `>= 0`); `component.kind` as a Postgres enum / `CHECK` over the `ComponentKind` set (single-region scope freeze — out-of-scope kinds rejected, not coerced); `assumption.source`/`provenance_tag` enum.
- **Application-enforced (in `SupabaseModelStore`, before insert, fail-closed):** ADR-002's `validate_model` (`ingestion.py:331`, lines 343–357) — notably **flow shares ≈ 1.0** (cannot be a column constraint) and full structural soundness. **Invalid → not stored as a runnable version** (fail closed).

Wire-safe per `docs/05`: UUID ids, `timestamptz`, enums as above.

> *Authority note — `docs/05` says `Edge` (rest/grpc/event protocol topology); `model.py` uses `Flow`/`FlowStep` (what the engine actually computes on). **v1 persists Flow/FlowStep** (runnable truth); the richer `Edge` topology (for diagram export) is a `GAP` → later ADR, and does not disturb the Flow-based engine. ADR-005 is authoritative for v1.*

### 7. Behind a `ModelStore` seam — stub-default, like the council/ingestor

A small interface with an **in-memory `StubModelStore`** default so the offline loop runs $0/stdlib, and a `SupabaseModelStore` behind it (delivery layer, lazy import — the engine never pulls a DB driver):

- `save_model(project, model) -> int` — returns the **new integer version number**; full metadata (`created_at`, `parent_version`, snapshot) is fetched via `get_model`.
- `get_model(project, version="head") -> SystemModel` · `list_versions(project) -> list[VersionMeta]` · `diff(project, v1, v2) -> ModelDiff`.

Mirrors ADR-001/002. Merging the seam ≠ activating persistence; **real multi-tenant persistence stays gated on Bifola's trigger** + this ADR's ratification.

## Build plan (A spec → Jem migration, issue #21)

1. **A (this ADR):** the schema spec, RLS policy shape + JWT-claim hook requirement, the input-vs-derived/engine-write enforcement, money-conversion boundary, the invariants, the seam interface.
2. **Jem (#21/#20):** the Supabase migration (tables + enums + RLS `enable/force` + the `tenant_id` custom-access-token hook + integer-money columns + DB `CHECK`s + cascade); behind #20 (Supabase dev project). Required gate items: the **cross-tenant isolation test** (A-can't-see-B on select/insert/update/delete) and the **Storage-purge-on-project-delete test**.
3. **A or Jem:** the `SupabaseModelStore` behind the seam + a **loss-less round-trip test** (`model.py` ↔ rows ↔ `model.py`, including domain_flags / assumptions / visit_prob / share) + `validate_model` on write + the float→minor-units conversion.
4. **Adversarial Review→Verify before merge** (auth/PII/tenant-isolation/schema → the CLAUDE.md gate, independent/author-recused): can any query cross tenants (RLS off / permissive policy / service-role misuse / missing JWT hook)? can a derived metric reach an input row (incl. the `params` bag)? **is any cost stored as float or unscaled string in Postgres (including inside a JSON column)?** does a project-delete actually purge **Storage** (not just rows)? does `ephemeral` truly drop raw bytes (and fail closed if it can't)?

## Recorded dissent (kept, not smoothed)

- **YAGNI skeptic:** full RLS + versioning + no-retention for a likely-solo v1 is heavy. *Accepted:* tenant isolation is a Tier-1 **day-one** MUST and is far cheaper to build correctly now (empty tables) than to retrofit onto live tenant data; ADR-002 already deferred it here precisely so it lands *with* persistence.
- **Data engineer:** full snapshot per version duplicates unchanged components. *Accepted:* models are tiny (≤ ~12 components); snapshot is simpler, diff-able, and avoids delta-replay bugs. Revisit only if model size explodes (kill-criterion).
- **Pragmatist:** RLS via a JWT claim couples us to Supabase Auth specifics (and needs the custom-claim hook). *Accepted:* ADR-003 already commits to Supabase Auth; the policy is a thin, swappable predicate, deny-by-default is the point, and §1's hook requirement makes the coupling explicit.
- **docs/05 author:** this contradicts "money as decimal strings." *Accepted on purpose* — the harm floor (integer minor units) wins; docs/05 to be reconciled.

## Confidence

**High** on the trust posture (deny-by-default RLS, the named engine-write enforcement, input-vs-derived-by-schema, integer money with a stated conversion point, fail-closed validation) and the round-trip with `model.py`. **Lower** on free-tier ergonomics at scale (Supabase connection caps / idle-pause — ADR-003 kill-criteria) and on the eventual `docs/05` `Edge`/topology richness (deferred `GAP`).

## Kill criteria (revisit this ADR if…)

- A cross-tenant **read / insert / update / delete** is ever possible (RLS disabled, a permissive policy, the JWT `tenant_id` hook missing/mis-set, or the service role serving a user request unscoped) → harm-floor breach; block all real upload until closed.
- A **derived** metric (utilisation/bottleneck/breakpoint/latency/cost) becomes writable on an input table or the `params` bag, or a stored number isn't attributable to an engine_version+seed → prime-directive breach by schema.
- A monetary value is stored as float / unscaled string anywhere (including a JSON column) → harm-floor (money) breach.
- A project delete leaves orphaned DB rows **or Storage objects**, or `ephemeral` retains raw source bytes → confidentiality/retention breach.
- Model size or version count outgrows full-snapshot storage → move to deltas.
- Multi-region / streaming model kinds enter scope → v2, new ADR.

## Consequences

Ratifying this unblocks issue **#21** (Jem's migration) and the diff-able design-as-code promise, and **discharges ADR-002's deferred tenant-isolation/no-retention MUST** — the precondition for any real multi-tenant upload. Ingestion's `IngestResult` migrates onto the store (ADR-002 consequence). The engine stays pure-stdlib behind the `ModelStore` seam; persistence stays **stub-default** until Bifola activates it. `docs/05` gets a follow-up reconciliation (money → integer minor units; `Edge` vs `Flow`; `Assumption.source` enum).

---

## §6a — Reconciliation to `model.py` (2026-08-03)

§6's "**eight typed fields**" enumeration and §4's "`model.py:44 monthly_cost_per_instance: float` … float→minor-units conversion boundary" were accurate when this ADR was ratified (2026-06-19) but were **superseded by two later, already-ratified changes**: **ADR-008** made all `model.py` money `int` minor units, and **ADR-009** added usage-based cost inputs (Tier 1) + a `PricingRates` value-object (Tier 2). This section reconciles the schema spec to **current `model.py`** so the migration builds to code, not to a stale list. **The §6 principle is unchanged** — *persist every `model.py` field, nothing dropped; the Milestone-5 gate is a lossless `model.py ↔ rows ↔ model.py` round-trip of the **whole** object.* Only the enumeration changes. The storage rule stays: **engine-read or money → typed column; evidence the engine never reads → `jsonb`.** (Adjudicated on #21, [issue-comment 5172095817](https://github.com/Stratagem-Africa/keystone/issues/21#issuecomment-5172095817).)

**`component` table — the current `Component` (`model.py:40-73`), 13 fields, nothing dropped:**

- The original 8 typed columns stand: `id, kind, name, per_instance_rps, instances, base_latency_ms, monthly_cost_per_instance, provenance`.
- **+5 usage-billing columns (ADR-009 Tier 1), typed integers** — they are money-driving (`model.py:107-114` validates them as non-negative `int` under the harm floor), so they get the same treatment as `monthly_cost_per_instance`: `egress_gb_per_month`, `storage_gb`, `requests_per_month`, `llm_input_tokens_per_month`, `llm_output_tokens_per_month`, each `bigint NOT NULL DEFAULT 0 CHECK (… >= 0)`. **Not** `jsonb`.
- **+2 evidence columns → `jsonb`:** `groundings` (`dict[str, Grounding]`) and `match_context` (`dict[str, str]`). The engine **NEVER** reads these (prime directive — grounding is evidence-only), so they need no typed/queryable columns; persist each as its **own** `jsonb` column, read back whole. **They must NOT go in the reserved `params jsonb` bag:** that bag's key-`CHECK` (`cost|capacity|latency|utiliz|throughput|breakpoint|bottleneck|rps`) exists to stop derived *numbers* reaching an input row (§3), but `groundings` is **keyed by metric name** (e.g. `"per_instance_rps"`) and would trip it — citations/bands are evidence *about* a metric, not a derived value on the typed path.

**`system_model.pricing` (`PricingRates`, `model.py:187-208`) — money, so typed columns (NOT `jsonb`):**

- The 5 rate fields are integer **micro-USD** per unit (`model.py:195-201`; 1 cent = 10_000 micro-USD). §4 + the money kill-criterion forbid float/unscaled money *"anywhere, including inside a JSON column,"* and typed columns make the invariant DB-enforceable: `bigint NOT NULL CHECK (… >= 0)` each. **Unit is micro-USD, not cents** — label the columns so nobody stores cents; the engine rounds the usage *total* to integer cents in `simulation_run`, but the **rates** stay micro-USD for sub-cent precision.
- `compute_pricing`: `text NOT NULL CHECK (compute_pricing IN ('on_demand','reserved_1yr','reserved_3yr','spot'))` — mirror `COMPUTE_PRICING_RETAINED_BP` (`model.py:178`) so a bad value fails closed at the DB too.
- `PricingRates.groundings`: `jsonb` (same evidence treatment as `component.groundings`).
- **Shape latitude:** 5 rate columns + `compute_pricing` + a `pricing_groundings jsonb` may live **on `system_model`** (1:1, no join — recommended) **or** in a 1:1 `pricing_rates` table (migration owner's call). The invariants above are the MUSTs.

**§4 correction (money conversion):** there is **no float→minor-units conversion** to perform. `monthly_cost_per_instance` is already `int` cents in `model.py:47` (ADR-008), as are all `model.py` money fields post-ADR-008. Store `bigint` directly; §4's conversion-boundary language no longer applies to any current `model.py` money value.

**Round-trip note:** because `Grounding`/`PricingRates` (de)serialize through `jsonb`, the Milestone-5 round-trip test must confirm the save→load reconstructs the **identical** dataclass — including `int`-vs-`float` inside a `Grounding` band. Everything else in §1–§7 (deny-by-default RLS, `tenant_id` on every table + the custom-access-token claim hook, the engine-write enforcement, `params`-bag `CHECK`, Storage purge-on-delete, the cross-tenant gate test) is **unchanged and binding**.
