# Keystone — Accuracy & Trust Charter

**Doc:** 03 · **Status:** Draft v0.1 · **Date:** 13 June 2026
**This is the differentiating document.** It defines what "correct" means for Keystone, how correctness is measured and bounded, and how it climbs toward enterprise-grade — honestly. It governs Overlay G (LLM product) obligations.

---

## 1. The honest premise

No architecture tool predicts a real distributed system with **pristine accuracy** — reality carries too many variables (traffic shape, data skew, GC pauses, a mis-set connection pool). Even a true discrete-event engine is, by its authors' own admission, *directional and benchmark-grounded, not certified.* **Claiming perfection is how you lose the trust of skeptical (especially Fortune-500) buyers. Measuring, bounding, and improving correctness is how you earn it.**

Therefore Keystone's correctness standard is not "pristine." It is **calibrated, transparent, confidence-bounded, and improving** — and that standard is *stronger*, because it is defensible.

## 2. The four pillars of trust

1. **Separation — the LLM reasons, the engine computes (`MUST`).** No metric ever originates from the language model. Numbers come only from the deterministic engine; the model parameterises and explains. A reviewer can always trace a number to a formula, not a generation.
2. **Transparency — no bare numbers (`MUST`).** Every quantitative output ships with: the **model/formula** used, the **assumptions** it rests on (each editable), and a **confidence band**. Every report carries an explicit "where this is wrong" section — **Keystone's own discipline, not borrowed.** Peer design simulators (SysSimulator and look-alike tools) surface confident numbers without disclosing how those numbers were derived, their data sources, or their accuracy (verified 2026-06 against SysSimulator's public site + its author's own write-up). So this transparency is a deliberate **differentiator**, not a copy. The engine also emits a generated **"how these numbers were computed" derivation** — its own deterministic steps, never prose — so provenance is *shown*, not asserted (`docs/13`, ADOPT-NOW; prior art: Genesys's execution trace).
3. **Provenance — honesty by tag (`MUST`).** Per the Playbook, every claim is `GROUNDED` (a benchmark or calibrated datum proves it), `GAP` (right standard, not yet met — states the shortfall), or `ASSUMPTION` (unverified). The product **never** renders an `ASSUMPTION` as `GROUNDED`.
4. **Calibration — earned, not asserted (`MUST` over time).** Accuracy improves only by comparing predictions to reality and tightening the model. This is the moat and the path to enterprise-grade.

## 3. The accuracy ladder (the trajectory to "elite correctness")

| Level | Name | What it means | Gate to advance |
|---|---|---|---|
| L0 | **Directional** (v1 launch) | Queueing-theory estimates from component benchmarks; right order of magnitude; bottleneck identification reliable; absolute latency/cost approximate. | Honest confidence bands shipped on every output. |
| L1 | **Benchmark-grounded** | Component models calibrated to published, version-pinned benchmarks; documented error envelope per component type. | Curated benchmark corpus + per-component error envelopes. |
| L2 | **Field-calibrated** | Predictions corrected by aggregated real-world actuals reported by users (the calibration loop). Published accuracy: "within X% on workloads like yours." | ≥ N reported actuals per component class; measured error ≤ target. |
| L3 | **Enterprise-grade** | Field-calibrated **and** independently auditable; accuracy SLAs per domain; reproducible; SOC2-adjacent controls. The Fortune-500 bar. | External audit + sustained measured accuracy + security posture. |

**v1 ships at L0 and says so.** "Elite correctness" is **L3 — a destination reached through L1→L2, not a launch claim.** Marketing that skips levels is prohibited by NFR-2.

> **On confidence bands (the mechanism).** v1's band is a utilisation-derived *heuristic*, not a statistical interval. The **earned** band comes later — from the v2 DES engine's **replications** (a t-interval across runs) and from field calibration (L2) — and never from an LLM. The engine **fails closed** (no fake zero band on insufficient data) rather than imply false precision. Both mechanisms are corroborated by prior art (Genesys's DES + statistics layer, `docs/13`).

## 4. How accuracy is measured (the eval harness — `MUST` before external traffic)

- **Simulation eval.** A fixed library of reference systems with known/benchmarked behaviour; the engine's predictions are scored against them; per-component error envelopes are published and regression-tested (deterministic, seeded — Playbook `QUA-EN`). The published envelope is a **per-(reference-system × metric) error table** under an explicit metric (e.g. MAPE) — never a single headline accuracy number — and **scoped to a stated support matrix** (the configurations it was validated on). *Worked reference (prior art):* Alibaba's [Tair KVCache HiSim](https://github.com/alibaba/tair-kvcache) predicts LLM-inference latency/throughput from trace replay and reports a per-(model × cache-tier × metric) MAPE table with errors <5%, explicitly bounded to *SGLang v0.5.6.post2 / Qwen3 / H20* — the exact shape to copy when this harness is built (a deeper study of its design is deferred to that point).
- **Council eval.** A graded set of design problems with expert-reviewed "good answers"; the council's recommendations are scored for soundness, and — critically — for **calibration of its own confidence** (does stated confidence match hit rate?). Blind peer review is used to reduce sycophancy/herding.
- **Reconciliation eval.** Document sets with planted conflicts; measured on whether Keystone surfaces every conflict (recall) without inventing false ones (precision).
- **Hallucination guard (Overlay G).** Any council claim citing a benchmark/precedent that does not resolve in the Knowledge Base is dropped and the dependent recommendation re-derived (`AIE-K4-01`: a citation that doesn't resolve is *invented*).

**External precedent for the error-envelope discipline (prior art).** Harvard's [gem5-Aladdin](https://github.com/harvard-acc/gem5-aladdin) earns trust for a *pre-build* (model-before-build) performance/power/area estimate by publishing a **per-(workload × metric) error envelope validated against RTL**, bounded to a stated support matrix — a second peer-reviewed anchor for the per-component-error-envelope shape above (the first being Tair KVCache HiSim). It produces zero numbers for Keystone; the targets here stay `ASSUMPTION` until Keystone's own harness runs (§7).

## 5. The calibration loop (the moat mechanism)

1. Keystone records every prediction with its assumptions and confidence.
2. Users (incentivised) report real-world actuals — a load test, a production metric.
3. Aggregated deltas correct the component models and tighten confidence bands.
4. Published accuracy improves; new users inherit a sharper model. The dataset compounds and **cannot be bought** by an incumbent.

> **Calibration must stay inspectable, and must not breach the prime directive.** Corrections are **explicit, auditable factors** (per component/metric), not an opaque re-fit — a reviewer can see *why* a number moved. Prior art: HiSim corrects predictions with named `prefill/decode_scale_factor` calibration constants that adjust predicted latency, with real-world request **traces** as the actuals source. The invariant: calibration only adjusts the engine's **inputs / correction factors**, never the math — the deterministic engine stays the sole producer of numbers (§2 pillar 1).

## 6. Trust guardrails (what Keystone refuses to do)

- **Never certify.** Keystone produces decision support, not certification — explicit on every report.
- **Always flag high-stakes domains.** Election, payments, health, safety-critical: emit a mandatory "requires expert/legal/security review" block; **refuse to imply the design is production-safe.**
- **Never hide dissent.** The council's minority positions are shown, not synthesised away.
- **Fail closed on confidence.** If the engine cannot bound an estimate, it returns "insufficient model — out of scope," not a guess.

## 7. Provenance of this charter

The accuracy-ladder targets (X%, N) are `ASSUMPTION` until the eval harness produces real numbers. The separation principle and transparency obligations are design `MUST`s enforceable from the first line of code.
