# Keystone — Functional Specification

**Doc:** 04 · **Status:** Draft v0.1 · **Date:** 13 June 2026
Detailed v1 behaviour. Each feature maps to a PRD `FR-n`. Provenance: `ASSUMPTION`.

---

## F1 · Multi-document ingestion (`FR-1`)

**Input:** one or more files (PDF, DOCX, MD, TXT), pasted text, pasted Mermaid/diagram code, or a voice note (→ transcript). Multiple files in a single session are treated as **one project corpus**.

**Behaviour:**
1. Each source is scanned (secrets/malware) and stored tenant-isolated.
2. A Claude pass per source extracts a **partial system model** + an **assumption ledger** (every gap it had to fill).
3. Sources are labelled by type (requirement / functional / ideation / diagram) — inferred, user-correctable.

**Output:** a per-source extraction preview the user can correct before reconciliation.

**Edge cases:** unreadable file → flagged, not silently skipped; huge corpus → chunked; contradictory file types → still ingested, conflicts handled in F2.

## F2 · Cross-document reconciliation (`FR-2`) — *the differentiator most tools skip*

**Behaviour:** merges all partial models into one canonical model and produces a **Reconciliation Report**:
- **Conflicts** — requirement A contradicts requirement B (e.g. "must be offline-first" vs "real-time global consistency"). Shown side-by-side; **never auto-resolved.**
- **Gaps** — non-functional requirements implied but unstated (scale, peak window, consistency, security posture). Claude proposes; user confirms.
- **Duplications / overlaps** — same requirement expressed differently across docs.

**Rule (`MUST`):** Keystone halts at unresolved *hard* conflicts and asks the user to choose; it does not design on a contradiction.

## F3 · Workload modelling (`FR-3`)

Claude proposes a realistic workload profile from the corpus (archetype-aware: "social feed" → read-heavy, bursty). Every parameter (DAU, peak RPS, read/write ratio, payload size, peak window) is **visible and editable**; nothing is hidden.

## F4 · Consensus design + ADRs (`FR-4`)

**Three stages** (borrowed from the LLM-Council pattern, settled by simulation):
1. **Independent design** — each persona (backend, data, security, SRE, cloud/FinOps, AI, YAGNI-skeptic) proposes independently.
2. **Blind peer review** — personas critique each other's proposals anonymised (reduces herding).
3. **Chairman synthesis** — converges to a recommendation **per decision**, emitting an **ADR** with: decision, rationale, **named dissent**, **confidence**, and **kill criteria** (the schema borrowed from LLM-Council-Decide).

Decisions covered: language/framework/libraries, datastore, cache, pub/sub, component communication, API style, AI-infusion (incl. where *not* to use AI), cloud services, DevOps tooling, security layering.

## F5 · Simulation (`FR-5`)

Deterministic analytical run of the single-region core (LB, app servers, SQL + replicas, cache, queue, object store). Outputs, **each with model + confidence band**: bottleneck component, breakpoint (max sustainable load), p50/p95/p99 per path, SPOFs, headroom before re-architecture, rough multi-cloud monthly cost.

## F6 · What-if interrogation (`FR-6`)

User mutates inputs — "10× traffic", "kill Postgres", "add a read replica", "swap to a queue" — and Keystone re-simulates, showing the **delta** and which ADRs are affected. This is the retention feature; it must feel instant and playful.

## F7 · Outputs & export (`FR-7`)

- **Architecture diagram** (rendered from the canonical model).
- **Canonical spec file** — the versionable design-as-code artifact (Doc 05).
- **ADR decision log.**
- **Stress-test report** — with the mandatory "where this is wrong / confidence" section.
- **Needs-expert-review block** — for high-stakes domains (mandatory, non-removable).
- Formats: Markdown + JSON (spec) at v1; PDF later.

## F8 · Stack / cloud / security advice (`FR-8 SHOULD`)

Per-component recommendations with rationale + alternatives + the tradeoff each persona raised. AI-infusion guidance explicitly includes **anti-patterns** (e.g. "do not place a probabilistic model in a vote-tabulation or money path").

## F9 · Calibration capture (`FR-9 SHOULD`)

Every prediction is persisted with assumptions + confidence. A lightweight "report your actuals" path exists from launch (even before the comparison dashboard), so the moat dataset starts accruing immediately.

## F10 · Starter blueprints (`FR-10 NICE`)

A small seed library of reference architectures to remove the cold-start; each opens as an editable canonical model.

---

## Cross-cutting behaviours

- **Assumptions are first-class everywhere** — any number or choice the system inferred is visibly tagged and editable.
- **High-stakes detection** runs on every project; it cannot be disabled.
- **Determinism** — same corpus + seed → same result; designs shareable as spec + seed.
- **Tenant isolation** — no user's corpus is ever visible to another (`SEC-H*`).
