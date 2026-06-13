# Keystone — Roadmap

**Doc:** 06 · **Status:** Draft v0.1 · **Date:** 13 June 2026
Phased plan. Each phase names its **accuracy level** (Doc 03) and its **tier** (Doc 00). Dates are `ASSUMPTION` — sequence is firmer than timing.

---

## Phase 0 — Spike *(now → ~2 weeks)*  ·  Tier-0  ·  Accuracy L0

**Goal:** prove the loop end-to-end on one real input.

- Ingest a single concept note (the **Election OS** note as first test input).
- Claude → canonical model (Component/Edge/Workload) with visible assumptions.
- Minimal council (single-model, 4–5 personas, blind review, chairman synthesis) → ADRs with dissent + confidence.
- Analytical simulation of the single-region core → bottleneck + breakpoint + latency + rough cost, each with a confidence band.
- Markdown report out, including the "where this is wrong" section.
- **Exit gate:** the loop runs on the Election OS note and a second, simpler note (URL shortener) and the output is something *you* would trust as directional. Calibration-record schema in place (capture from day one).

## Phase 1 — Private beta *(~2 weeks → ~3 months)*  ·  Tier-1 controls on  ·  Accuracy L0→L1

- Multi-document ingestion + the **reconciliation report** (the differentiator).
- Voice and pasted-diagram input.
- What-if interrogation.
- Tenant isolation, upload confidentiality, secret-scanning (harm floor + `SEC-H*`).
- **Eval harness** (simulation + council + reconciliation evals) — *gate before any external traffic.*
- Seed **Knowledge Base** (reference architectures + component benchmarks) → grounds the council; moves component models toward L1 (benchmark-grounded).
- **5 design-partner users** from P1/P2; validate the 3 open PRD questions.
- **Exit gate:** ≥ 60% activation with design partners; published per-component error envelopes (L1).

## Phase 2 — Public launch *(~3 → ~9 months)*  ·  Tier-1  ·  Accuracy L1→L2

- Web UI polish; shareable designs (spec + seed); starter blueprint library.
- **Calibration UI** — users report actuals; aggregated deltas tighten models → **L2 (field-calibrated)**; begin publishing "within X% on workloads like yours."
- Content/SEO engine (learn hub) for the learner funnel — distribution.
- Pricing: free tier (learner funnel) + paid (founders/teams). Money path triggers the **fintech harm-floor** (integer minor units) and tier re-declaration.
- **Exit gate:** measured L2 accuracy on the top component classes; first retained paying cohort.

## Phase 3 — Depth & defensibility *(~9 → ~18 months)*  ·  Tier-1  ·  Accuracy L2

- **Discrete-event simulation engine** (the v2 fidelity upgrade) for async/streaming/mesh topologies.
- Multi-region + chaos/failure-injection simulation.
- Repo & cloud import (infer architecture from code/IaC; later, drift detection vs reality).
- Community reference-architecture library (network effect).
- Visual canvas (deferred input ergonomics).

## Phase 4 — Enterprise track *(18 months+)*  ·  Tier-1+  ·  Accuracy L2→L3

- External accuracy audit; per-domain accuracy SLAs; reproducibility guarantees.
- SOC2-adjacent controls, SSO, on-prem/VPC option.
- **L3 (enterprise-grade)** — the Fortune-500 correctness bar, *earned* via the calibration record, not claimed at launch.

---

## The throughline

Every phase advances **one rung of the accuracy ladder by capturing more reality**, and every phase keeps the same trust contract (LLM reasons, engine computes; no bare numbers; honest provenance). The product's value and its defensibility rise together — which is the only way a focused team out-competes both SysSimulator (below, on the design layer) and the funded AI-design startups (beside, on the calibration moat).

## Immediate next action

Build **Phase 0** against the Election OS note. Stack recommendation pending ratification (Doc 02 §5). On "go," scaffold the repo and implement the loop.
