# Keystone — Documentation Suite

**Working name:** Keystone *(placeholder)*
**Owner:** Adam Bifola Raji · Stratagem Africa
**Status:** Internal — venture concept under active definition. Not client-facing.
**Date:** 13 June 2026
**Authority:** This suite is written under the **Stratagem Africa Engineering Playbook v1.0**. Standards are tagged by obligation (`MUST` / `SHOULD` / `NICE`) and provenance (`GROUNDED` / `GAP` / `ASSUMPTION`). At this stage almost everything is `ASSUMPTION` — nothing here is built yet.

---

## What Keystone is

*Describe what you're building in plain English — a grounded consensus of AI architects designs it, justifies every decision, and validates it with simulation, improving toward enterprise-grade correctness over time.*

Keystone takes one or more requirement and functional documents, designs a system architecture through an adversarial AI council, validates it with a deterministic capacity/bottleneck simulation, and emits an auditable design package — with every estimate shown with its assumptions, confidence, and model. It is **not** a diagramming tool (you don't start from a blank canvas) and **not** "a better simulator" (the simulation is one feature). It is the layer that takes a builder from **intent → validated design**.

## The documents

| # | Document | Purpose |
|---|---|---|
| 00 | **README** (this file) | Index, governance, tier declaration |
| 01 | **Product Requirements (PRD)** | Problem, users, jobs, functional + non-functional requirements, scope, success metrics |
| 02 | **System Architecture** | How Keystone itself is built — services, data flow, stack, tier, security |
| 03 | **Accuracy & Trust Charter** | How correctness is defined, measured, bounded, and improved — the differentiating doc |
| 04 | **Functional Specification** | Detailed behaviour of every v1 feature, including multi-document ingestion + reconciliation |
| 05 | **Canonical Data Model** | The schema that is the single source of truth — system model, ADRs, simulation, calibration |
| 06 | **Roadmap** | Phased plan v1 → v2 → v3, with the accuracy trajectory |

Companion: `../Keystone-Product-Definition-v0.1.md` (the one-page strategy brief this suite expands).

## Governance — tier declaration

Per the Playbook three-question picker:

1. Real money / regulated / PII data? — **Not at v1** (Keystone ingests users' *architecture* documents, which may be commercially sensitive but are not PII/money). Becomes **yes** at enterprise tier.
2. External users? — **Yes** (the product is shipped to developers outside the team).
3. Multi-tenant? — **Yes** (one deployment serves many users/orgs).

**Verdict: Tier-1 from first external traffic.** v1 prototype work may run Tier-0, but the **harm floor binds at every tier**: no committed credentials, no secret leakage, no loss of a user's uploaded documents, and (when billing is added) integer-minor-unit money only. Because Keystone ingests proprietary design documents, **tenant isolation and upload confidentiality (`SEC-H*`) are treated as Tier-1 obligations from day one.** **[ASSUMPTION — re-declare before first external traffic.]**

## Relevant Playbook surfaces

- **Overlay G (AI/ML & LLM product)** — Keystone *is* an LLM product: evals, guardrails, RAG grounding. This overlay governs the council and accuracy work.
- **Pillar B (Architecture & Design)** — C4, ADR discipline, API versioning.
- **Pillar H (Security & Compliance)** — tenant isolation, secrets, upload confidentiality.
- **Pillar E (Quality)** — the adversarial Review→Verify→Adjudicate gate; here it is *both* an internal engineering practice **and** the product's own consensus mechanism.
- **Pillar K (AI-Augmented Engineering)** — because Keystone is itself built largely by AI agents.
