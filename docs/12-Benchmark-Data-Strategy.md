# Keystone — Benchmark-Data Strategy

**Doc:** 12 · **Status:** Proposal (open to revision) · **Date:** 2026-06-20 · **Owner:** Keystone A (Bifola)
**Relates to:** ADR-006 (KB seam + honesty contract), `docs/03` (Accuracy & Trust Charter — the L0→L1 climb), `docs/05` + ADR-005 (model store — a possible v2 home), `docs/11` (engine scoring), CLAUDE.md (prime directive; harm floor; $0 cost rule).
**Scope:** how Keystone curates, structures, uses, and quality-gates benchmark data to move from **L0 (Directional)** to **L1 (Calibrated)** — honestly, at $0, behind the existing stub-gated KB seam. Verified against the code (file:line references throughout).

---

## 1. Goal & principles

**Goal.** Move specific component capacities from `ASSUMPTION` → `GROUNDED` by attaching resolvable evidence to the three input facts the engine consumes — `per_instance_rps`, `base_latency_ms`, `monthly_cost_per_instance` (`GROUNDABLE_METRICS`, `knowledge_base.py:28`) — so the Charter's L0→L1 climb is **earned, not asserted**. Today **nothing is GROUNDED**: all 192 capacity entries across the reference corpus are tagged `"ASSUMPTION"` — the correct, honest L0 state. The KB is the only lever that changes that.

**Non-negotiable honesty rules (bind every datapoint, forever):**

1. **No `GROUNDED` without a resolvable citation + a confidence band.** Structurally enforced (`Grounding`/`Citation` constructors). The type can't check that a reference *resolves* — so **independent curation review is the gate** (ADR-006 §2).
2. **Inputs only, never a derived metric.** The KB may ground only the three `GROUNDABLE_METRICS`; asking it for utilisation/bottleneck/breakpoint/latency/cost-estimate **raises** at the seam. The engine stays the sole producer of numbers (prime directive).
3. **Absence of evidence stays `ASSUMPTION`.** No match → `None` → caller keeps `ASSUMPTION` (the safe direction). A false `GROUNDED` is the only unrecoverable failure; we always fail toward honest silence.
4. **No bare numbers, no false precision.** Every grounded value ships with its band, unit, source, and measurement context. A tight band must be *earned* by evidence.
5. **Cost is integer minor units.** The cost unit is `usd_minor_per_month` (harm floor forbids float dollars).

> The corpus is **not** a race to "100% grounded." It is a race to *truthfully labelled* coverage.

---

## 2. How we USE it — Grounding → engine → report

- **The seam (additive, inert today).** A consumer (the reference-model scorer, later ingestion) calls `kb.ground(comp.kind, metric, context=…)`. On a hit it sets the input and flips provenance to `GROUNDED`; on `None` it leaves `ASSUMPTION`. The default stub grounds nothing, so behaviour is unchanged until the `curated` provider is activated (Bifola's trigger).
- **The engine is — and must stay — provenance-blind.** `simulate()` reads only capacity + latency, never `provenance` (`simulation.py:92–100`). The same math runs whether an input is grounded or assumed. Grounding changes the *number* (which can move the bottleneck/breakpoint); it must never change the *math*. Coupling the engine to provenance would re-import trust into the computation — forbidden.
- **Two confidence axes — keep them separate.** Engine-stability confidence (`_confidence(rho_max)`, utilisation-driven, `simulation.py:73–81`) and input-provenance confidence are *different things*. Never blend them into one misleading scalar.
- **Partial grounding is the normal case — and the most honest output we have.** Real designs are mixed (gateway grounded to vendor docs; app tier still an assumption because it depends on the user's code; DB cost grounded to a pricing page). The report's job is to make that legible so the user knows **exactly where to spend their load-testing budget**.
- **Confidence rollup (the rule).** Do **not** invent a blended percentage. Report `N grounded / M assumption` inputs and — load-bearing — **whether the bottleneck component is grounded.** If the bottleneck is an assumption, the absolute numbers are soft and the report must say so; if grounded, state its band. (Bottleneck *identity* is robust to ±20% capacity error; absolute latency/cost is not — that asymmetry is already in the caveats.)
- **⚠ Pre-work blocker (must build before any real grounding ships).** Today the per-component report table shows **no** provenance, and `Component` (`model.py:36–45`) has **no field to carry citations** — provenance is one string and the evidence chain is dropped after `ground()` returns. **Before grounding goes live we must:** (1) extend `Component` (or a parallel per-capacity ledger) to persist `(provenance, band, citations)` per metric; (2) add a Provenance + Confidence-band column to the report's component table + a ledger row (with clickable `source`/`reference`) per grounded capacity; (3) change the standing "all ASSUMPTION" caveat to the real mix.

---

## 3. What we COLLECT & in what order

**Source tiers (set the floor on band width):**

| Tier | Source | Accept rule | Min band |
|---|---|---|---|
| **T1** | Vendor spec/benchmark, version-pinned + methodology disclosed (AWS instance docs, `redis-benchmark`, RDS perf guide); peer-reviewed paper with raw data; **our own** reproducible load test | may ground solo if version-pinned + methodology stated | ±10–15% |
| **T2** | Reputable engineering blog/postmortem (Stripe, Discord, Uber); community aggregate (DB-Engines, Phoronix) | **≥2 independent** sources | ±15–30% |
| **T3** | Vendor datasheet w/o methodology; single secondary claim | **≥3** sources, else mark `GAP` | ±30–60% |
| **Banned** | **LLM-generated numbers** (circular — violates the prime directive); vendor marketing w/o methodology; unattributed/forum claims; any source that itself cites nothing | never `GROUNDED` | — |

A vendor's *own* benchmark is honest-but-optimistic → quarantine to a **wider band** until independently corroborated. Synthetic benchmarks (`pgbench`, `redis-benchmark`) measure a lab workload, not the user's → tag `synthetic` and let the report prompt a load test.

**Collection order (highest leverage first — each grounding compounds across 10–20 models):**
1. **APP_SERVER** `per_instance_rps` + `base_latency_ms` — most frequent kind; highest variance → collect *several* context-keyed datapoints.
2. **CACHE (Redis)** `per_instance_rps` — high bottleneck impact; `redis-benchmark` is a clean T1 source.
3. **SQL_DB** `per_instance_rps` + `monthly_cost_per_instance` — bottleneck in write-heavy systems; RDS pricing is a stable T1 cost source.
4. **LOAD_BALANCER / API_GATEWAY** `per_instance_rps` — abundant vendor docs; cheap to ground.
5. **OBJECT_STORE / QUEUE / EXTERNAL_API** — fill as the corpus demands.

**First milestone:** 10–15 cited groundings across the top 3–5 kinds — enough to take a handful of reference models from 100% `ASSUMPTION` to majority-`GROUNDED` and prove the pipeline end-to-end.

---

## 4. How we STRUCTURE it

**The context-match problem (why a flat table is wrong).** The same `(kind, metric)` has radically different true values by context: an app server doing stateless ID generation sustains ~15k rps; one doing I/O-bound geo-matching ~3k rps — both correct *in context*. A flat `(kind, metric) → value` lookup would misapply one. So a datapoint must carry **the context it was measured under**, and the matcher must **refuse (return `None` → stay `ASSUMPTION`) on a poor match** rather than force a number.

**Where it lives.** v1.5: a hand-curated, git-tracked **JSONL** file (`prototype/keystone/benchmarks/corpus.jsonl`), loaded by a new `CuratedKnowledgeBase` behind `KB_PROVIDER=curated` (the slot ADR-006 already reserves — today it raises `NotImplementedError`). One datapoint per line = clean diffs, human review, $0, stdlib `json`. v2 (own ADR): the same rows in Postgres + pgvector for semantic retrieval (ADR-005 store, tenant-isolated).

**The `BenchmarkDatapoint` schema** (distinct from the runtime `Grounding`; carries match-context + metadata that `ground()` strips to a `Grounding` on a hit):

| Field | Purpose |
|---|---|
| `component_kind`, `metric` | lookup key; `metric ∈ GROUNDABLE_METRICS` (enforced) |
| `instance_type`, `workload_shape`, `region` | **match context** (e.g. `r7g.large`, `read_heavy`, `us-east-1`) |
| `config_notes`, `concurrency_model` | tuning the result depends on |
| `value`, `unit` | the fact; `unit ∈ {rps, ms, usd_minor_per_month}` (cost in integer minor units) |
| `confidence_low` / `confidence_high` | the band; `low ≤ value ≤ high`, width ≥ the tier floor |
| `citations[]` | `{source, reference, note}`, ≥1, each resolvable; **`note` mandatory** — records the benchmark's constraints (hardware, query shape, payload, concurrency); this is what defuses context-mismatch |
| `methodology` | `vendor_datasheet` / `load_test_synthetic` / `load_test_realistic` / `production_metric` / `paper` |
| `measured_date` | ISO date → freshness/staleness signal |
| `source_tier` | T1/T2/T3 → audited vs corroboration count + band width |

**Example (an honest, context-keyed datapoint):**

```jsonl
{"component_kind":"cache","metric":"per_instance_rps","instance_type":"r7g.medium",
 "workload_shape":"read_heavy","region":"us-east-1",
 "config_notes":"Redis 7.0, single-threaded, atomic INCR + TTL","concurrency_model":"open_queue",
 "value":80000,"unit":"rps","confidence_low":68000,"confidence_high":92000,
 "citations":[{"source":"Redis 7.0 redis-benchmark (GET/INCR throughput)",
   "reference":"https://redis.io/docs/.../benchmarks/ (retrieved 2026-06-15)",
   "note":"single r7g.medium, 100 concurrent clients, 1KB values, synthetic; single-node only — cluster sharding NOT modelled; band widened for that extrapolation"}],
 "methodology":"load_test_synthetic","measured_date":"2026-06-15","source_tier":"T1"}
```

**The matcher** (in `CuratedKnowledgeBase.ground`): filter by `(kind, metric)`, then by supplied context dims; exact match → return the `Grounding` (tightest band wins ties); only a relaxed match → return it with a **widened band** *or* `None`; no match → `None`. Never fabricate. This keeps "absence of evidence → `ASSUMPTION`" structural.

---

## 5. Quality assurance — the gates a datapoint must pass

**Five-layer defence (each catches what the previous can't):**
1. **Structural (free, automatic).** The `Grounding`/`Citation` constructors already reject no-citation, non-bracketing band, non-finite/negative value, multi-line/empty evidence text. "GROUNDED without a citation" is impossible.
2. **Curator self-check (pre-commit).** A `validate_corpus` script asserts: `metric ∈ GROUNDABLE_METRICS`; band width ≥ tier floor (≥10% always); corroboration count ≥ tier requirement; `note` non-empty + records constraints; `measured_date` present; unit allowed.
3. **Independent review (the load-bearing human gate).** A second reviewer opens **every** citation, confirms it **resolves and contains the claim**, checks version-pinning, band-vs-tier, and context applicability. Any failure → request changes, or mark **`GAP`** (not `ASSUMPTION`) with a tracked issue so the shortfall is *visible*. The type can't verify resolution; a human must.
4. **Merge gate.** Lands through the normal review→merge flow; the corpus validator runs in `scripts/check.sh` (red gate blocks merge). **AI proposes datapoints; a human ratifies; never self-applied.**
5. **Staleness watch.** `measured_date` drives re-validation: <12 mo fresh; 12–24 mo → flag "may be stale," re-corroborate; >24 mo or superseded hardware/major version → auto-downgrade to `GAP`. (All checks run at curation/CI — **no network at runtime**, preserving the offline/$0/deterministic engine.)

**Workflow:** curator drafts → self-check script → small PR → reviewer opens every citation + fills the grounding checklist → corpus validator green → human ratify → merge → activation still gated on Bifola's trigger.

---

## 6. Phased rollout

- **Phase 0 — now (done).** Seam + contract + stub. Grounds nothing; honest L0.
- **Phase 1 — bootstrap (1–2 wks, $0).** Build `CuratedKnowledgeBase` (JSONL loader) + the corpus validator + contract tests; curate **10–15 T1/T2 groundings** for the top 3–5 kinds; **extend `Component` to persist `(provenance, band, citations)` per metric** (the report blocker). Deliverable: a few reference models run majority-`GROUNDED`, citations visible in the report. Still stub-default; activation is Bifola's trigger.
- **Phase 2 — corpus calibration (3–4 wks).** Wire grounding into the reference-model scorer (`docs/11`); ground the hand-built models across the in-scope corpus, each capacity grounded as far as honest evidence allows, the rest `ASSUMPTION`/`GAP` with a TODO citation. Ship the report's provenance column + per-capacity ledger.
- **Phase 3 — domain depth + field calibration (month 2+, gated).** Curate high-stakes domains (payments, wallet — already `domain_flags`'d) with expert review; begin the Charter's field-calibration loop (users report production actuals → a **separate** user-calibrated track, never overwriting the frozen curated corpus). pgvector/RAG retrieval becomes its own ADR once the corpus is large enough to be worth retrieving over.

Scaling is additive: new context dims are new fields + new rows; the JSONL → Postgres move is a storage swap behind the same `ground()` seam.

---

## 7. Top 3 risks + guardrails

1. **Curation-discipline collapse — pressure to "look complete."** The temptation: accept a marginal citation, narrow a band, or mark `GROUNDED` to drive the assumption-count to zero. This single failure turns the effort into theatre. **Guardrails:** the type floor (no citation → can't construct); an explicit **banned-source list**; independent reviewer opens *every* link; a **published curation log** (what was considered/rejected and why); a **quarterly 10% audit** — if any audited citation doesn't resolve, the `curated` provider is downgraded to `GAP` until re-vetted. Failing direction is always `ASSUMPTION`/`GAP`, never a false `GROUNDED`.
2. **The confidence-band illusion — a user reads an ensemble band as their-workload certainty.** "80k ± 15%" is uncertainty *across deployments*; the user's skewed workload may sit outside it. **Guardrails:** mandatory `note` records the measured context; `synthetic` methodology triggers a "validate on your traffic" prompt; the rollup states bands are directional until the user load-tests their own stack, and flags when the **bottleneck itself is an assumption**.
3. **Feedback loop learning the wrong thing / provenance-coupling creep.** (a) Field actuals from a misconfigured deployment narrow a band around a broken number; (b) someone "improves" the engine to read provenance. **Guardrails:** field actuals carry workload/hardware/version metadata and are match-filtered before touching a band; >2σ outliers quarantined ("typical or edge case?"); the curated corpus stays **frozen** while user calibration updates a *separate* track. Standing invariant, enforced as a test: **the engine never inspects `provenance`** — grounding changes inputs, never the math.

---

*This is a proposal — revise freely. Nothing here activates anything: the KB stays stub-default (grounds nothing, $0) until a `curated` provider is built and Bifola triggers it.*
