# Keystone — Canonical Data Model

**Doc:** 05 · **Status:** Draft v0.1 · **Date:** 13 June 2026
**Playbook:** Pillar F (`DAT-F*`), Pillar B. The canonical model is the **single source of truth** — every front door (docs, voice, text, diagram) normalises into it; every output (diagram, ADRs, simulation, export) is derived from it. It is the design-as-code artifact.
**Provenance:** `ASSUMPTION` — schema sketch for review, not a migration.

---

## 1. Design rules

- **One source of truth `MUST`** — UI, simulation, exports all read this model; none holds parallel state.
- **Versioned & diff-able `MUST`** — every change produces a new immutable version; designs are compared as diffs (the "design-as-code" promise).
- **Assumptions are data, not prose `MUST`** — each inferred value links to an `Assumption` record.
- **Wire-safe `MUST`** (Playbook) — IDs as strings; money as decimal strings; timestamps ISO-8601; enums as typed unions.
- **Append-only where it matters `SHOULD`** — ADRs and calibration records are append-only; corrections are new records, not overwrites.

## 2. Core entities

```
Project
  id, owner_id, tenant_id, name, created_at, status
  → SourceDocument[]   (the uploaded corpus)
  → SystemModel        (current canonical version)
  → ReconciliationReport
  → ADR[]
  → SimulationRun[]
  → CalibrationRecord[]

SourceDocument
  id, project_id, type{requirement|functional|ideation|diagram|voice|text},
  uri, checksum, extracted_model_ref, assumption_ledger_ref, scanned_ok

SystemModel  (versioned, immutable per version)
  id, project_id, version, parent_version, created_at, seed
  → Component[]
  → Edge[]            (communication links)
  → WorkloadProfile
  → Assumption[]

Component
  id, kind{load_balancer|app_server|sql_db|replica|cache|queue|object_store|
           api_gateway|cdn|external_api|client|...},
  name, params{throughput_limit, latency_dist, replica_count, capacity, ...},
  provenance{inferred|user_set}, assumption_refs[]

Edge
  id, from_component, to_component, protocol{rest|grpc|graphql|event|ws},
  sync{sync|async}, payload_size, provenance

WorkloadProfile
  archetype, dau, peak_rps, read_write_ratio, payload_size_bytes,
  peak_window, growth_assumption, provenance, assumption_refs[]

Assumption
  id, subject_ref, statement, value, confidence{low|med|high},
  source{llm_inferred|benchmark|user}, editable=true, provenance_tag{GROUNDED|GAP|ASSUMPTION}

ReconciliationReport
  id, project_id, conflicts[]{a_ref,b_ref,severity,status{open|resolved}},
  gaps[]{statement, proposed_value, status}, duplications[]

ADR   (append-only)
  id, project_id, model_version, decision_area, decision,
  rationale, dissent[]{persona, position}, confidence, kill_criteria[],
  status{proposed|ratified}, ratified_by, ratified_at

SimulationRun  (deterministic, reproducible)
  id, model_version, seed, engine_version,
  results{ bottleneck, breakpoint_rps,
           latency{p50,p95,p99},
           spofs[], headroom, cost_estimate{by_cloud} },
  per_metric[]{ value, model_used, confidence_band, assumptions_ref[] },
  caveats[]   (the mandatory "where this is wrong" section)

CalibrationRecord  (append-only — the moat dataset)
  id, project_id, sim_run_ref, component_kind,
  predicted_value, actual_value, actual_source{load_test|production|user_report},
  reported_at, delta, used_in_model_version
```

## 3. Why this shape

- **Component + Edge + WorkloadProfile** is exactly what the deterministic engine needs to compute — and exactly what the LLM produces from prose. The model is the typed boundary in NFR-3 (LLM fills it; engine reads it).
- **Assumption as a first-class entity** is what makes NFR-1 (no bare numbers) and the Accuracy Charter enforceable — every value can show its basis and be edited.
- **SimulationRun.per_metric carrying model + confidence** bakes the trust pillars into the data, not the UI.
- **CalibrationRecord** is the moat in schema form: predicted vs actual, feeding the next model version.

## 4. Export format

The `SystemModel` (+ its `Assumption[]`, `Edge[]`, `WorkloadProfile`) serialises to a single human-readable, version-controllable spec file (YAML/JSON) — the artifact a user commits to their repo. Re-importing it reproduces the design; pairing it with the `seed` reproduces the simulation.

## 5. Gaps

- Streaming/mesh/multi-region component kinds are intentionally absent at v1 (`GAP` → v2).
- No PII in this model by design; if enterprise features later store org/user PII, the F-pillar retention/RLS rules apply and the tier re-declares.
