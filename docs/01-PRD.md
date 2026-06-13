# Keystone — Product Requirements Document (PRD)

**Doc:** 01 · **Status:** Draft v0.1 · **Date:** 13 June 2026 · **Owner:** Adam Bifola Raji
**Provenance note:** All requirements below are `ASSUMPTION` until validated with the first 5 design-partner users. Obligation tags (`MUST`/`SHOULD`/`NICE`) express *intended* v1 binding, not met gates.

---

## 1. Problem

Most people who build software can *code* but cannot *architect for scale*. Existing tools assume the opposite: diagramming tools (Eraser, IcePanel, draw.io) and simulators (SysSimulator) start from a blank canvas the user must fill. There is no tool that takes a builder from **intent → validated design**. The result: teams commit to architectures on intuition, discover the bottleneck in production, and rebuild. **[D]**

## 2. Users & personas

- **P1 — The capable-but-unseasoned developer (primary).** Can build; has never designed for scale; has no principal engineer to learn from. Junior/mid, bootcamp grad, self-taught.
- **P2 — The technical founder (secondary).** Shipping a product without a senior architect on the team; needs a defensible design and a cost read before committing.
- **P3 — The learner / interview-prepper (distribution funnel).** Reachable, vocal, cheap to acquire; seeds top-of-funnel.
- **Non-user:** the literally non-technical. Excluded — they do not design distributed systems.
- **North-star buyer (not v1):** Fortune 500 architecture teams. They define the *correctness bar* Keystone climbs toward; they are not the launch customer.

## 3. Jobs to be done

1. "I have requirement/functional docs — tell me what to build and why." (design)
2. "Pressure-test my design before I commit — where does it break, what does it cost?" (validate)
3. "Give me a defensible, auditable decision record I can show my team/CTO." (justify)
4. "Teach me *why* the architecture is shaped this way." (learn)

## 4. Functional requirements (v1)

- **FR-1 `MUST`** — Accept **multiple documents at once** (requirement docs, functional specs, ideation notes) plus free-text and voice, normalised into one canonical system model. *(See FR-2.)*
- **FR-2 `MUST`** — **Cross-document reconciliation:** detect and surface conflicts, gaps, and duplications *across* the uploaded set; never silently merge contradictory requirements — flag them for resolution.
- **FR-3 `MUST`** — Derive a candidate architecture (components, communication, API style, data/cache/queue choices) with every inferred **assumption visible and editable**.
- **FR-4 `MUST`** — Run the architecture through the **consensus council** (independent design → blind peer review → chairman synthesis) and emit an **ADR per decision with recorded dissent, confidence, and kill criteria**.
- **FR-5 `MUST`** — **Deterministic simulation** of the single-region core tier: bottleneck, breakpoint, p50/p95/p99, SPOFs, headroom, rough multi-cloud cost — each output carrying its model + confidence.
- **FR-6 `MUST`** — **What-if interrogation:** change traffic/components and re-simulate, showing the delta.
- **FR-7 `MUST`** — Emit outputs: architecture diagram, **versionable canonical spec file**, ADR decision log, stress-test report, and a flagged **"needs expert/legal review"** list for high-stakes domains.
- **FR-8 `SHOULD`** — Stack / cloud / DevOps / security-layering recommendations with rationale and alternatives.
- **FR-9 `SHOULD`** — Capture **calibration data** (predicted vs later-reported actuals) from launch, even before the calibration UI exists.
- **FR-10 `NICE`** — Starter blueprints / reference architectures to seed onboarding.

## 5. Non-functional requirements

- **NFR-1 Correctness `MUST`** — Every quantitative output states its **assumptions, confidence band, and the model that produced it.** No bare numbers. (See Doc 03.) This is the load-bearing NFR; violating it is the false-precision failure mode.
- **NFR-2 Honesty `MUST`** — The product never presents an `ASSUMPTION` as `GROUNDED`. A claim with no model behind it is labelled, not asserted. (Playbook evidence-as-required-field, `AIE-K4-01`.)
- **NFR-3 Separation `MUST`** — **The LLM reasons; the deterministic engine computes the numbers.** The council never invents a throughput figure. (See Doc 02 §4.)
- **NFR-4 Confidentiality `MUST`** — Uploaded documents are tenant-isolated and never exposed across users; local-first/export options offered. (`SEC-H*`.)
- **NFR-5 Latency `SHOULD`** — A first design + simulation in **< 3 minutes** for a typical web-app spec. **[ASSUMPTION]**
- **NFR-6 Cost `SHOULD`** — v1 infra + AI run-cost buildable and operable within a hobby budget; council runs single-model-multi-persona to control inference spend.
- **NFR-7 Reproducibility `SHOULD`** — Same input + seed → same simulation result (borrowed from SysSimulator's determinism); designs are shareable as spec + seed.

## 6. Scope

**In (v1):** multi-doc + voice ingestion → canonical model; council + ADRs; single-region web-stack simulation; what-if; stack/cloud/security advice; exports; calibration capture.

**Out (v2+):** interactive visual canvas; streaming/microservice-mesh + multi-region/chaos simulation; repo & cloud import; full predicted-vs-actual calibration UI; community reference-architecture library; enterprise SSO/SOC2/on-prem.

## 7. Success metrics

- **Activation:** % of new users who reach a completed design + simulation in first session. Target **≥ 60%**. **[ASSUMPTION]**
- **Trust:** % of simulation reports where the user accepts the design without overriding > 2 assumptions. **[proxy for perceived correctness]**
- **Retention:** repeat designs per user / month.
- **Calibration coverage (leading moat metric):** count of designs with at least one real-world actual reported back. This is the metric that compounds into the moat.

## 8. Red-team (strongest case against)

- *The council is commoditised* (the entire LLM-Council ecosystem) → the council is table stakes; the moat is the simulation + calibration loop, not the debate.
- *Confidently-wrong advice kills trust* → NFR-1/2/3 exist precisely to make honesty structural, not optional.
- *Fortune-500 correctness from a room is fantasy* → correct; v1 targets P1/P2, and enterprise-grade is a measured trajectory (Doc 03), not a launch claim.

## 9. Open questions

1. Do P1 users trust a design they didn't draw? (validate with design partners)
2. Is single-model-multi-persona council quality sufficient, or is multi-provider diversity needed sooner than planned?
3. What is the minimum simulation fidelity that P1/P2 will accept as credible?
