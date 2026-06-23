# ADR-009 — Cost model v2: a usage-based ("per-use") layer + the cost taxonomy

**Status:** **Proposed** — awaiting Bifola's decision on **scope** (which tiers below to build). No code until ratified. Touches the engine's cost computation + the model schema + the grounding metrics, so per CLAUDE.md (schema / money / trust-core) **AI proposes, a human ratifies**.
**Date:** 2026-06-23 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/04` F5 (sim outputs incl. cost), ADR-008 (money = integer minor units), ADR-006 + `docs/12` (the grounding KB — new per-unit rates would be grounded the same way), `prototype/keystone/simulation.py` (the sole producer of numbers), `prototype/keystone/report.py` (the "cost is compute/instance only…" caveat this closes).

---

## Context

Today Keystone's cost is **per-instance compute only** — it sums `monthly_cost_per_instance × instances` across components (`simulation.py`), and the report honestly caveats: *"Cost is compute/instance only; data-transfer/egress and managed-service pricing nuances are not yet modelled."* Real cloud bills are dominated by costs this model can't see — **data egress is routinely the #1 surprise line** — and our "full price" assumption ignores the **40–90% discounts** most real deployments use. So the cost number is directionally useful but materially incomplete.

The root issue: those costs are **consumption-priced** — `cost = f(traffic, volume, requests)`, not a fixed per-machine charge. That is a different *shape* of calculation, not just "more prices to look up." This ADR proposes adding that shape, and records the **full cost taxonomy** so scope is a deliberate decision, not a drift.

## The cost taxonomy (everything a real system pays for)

| # | Category | Examples | Disposition |
|---|---|---|---|
| 1 | **Compute (per-machine)** | VMs, managed DB/cache nodes, LB base | ✅ **modelled + grounded** (PR #64) |
| 2 | **Data movement** | internet egress, inter-region/inter-AZ, NAT, VPN | **Tier 1 (this ADR)** — the #1 surprise |
| 3 | **Storage** | object ($/GB+req), block/IOPS, DB storage, backups | **Tier 1** |
| 4 | **Per-request services** | API gateway, serverless (invocations+GB-s), queues, DNS, pub/sub | **Tier 1** |
| 5 | **Observability** | logs/metrics/traces ingested + retained | **Tier 1** |
| 6 | **Redundancy / scale** | HA standby (~2×), read replicas, multi-region (N×), headroom | **Tier 2** (mostly expressible via instance counts; formalize as multipliers) |
| 7 | **Pricing model / discounts** | reserved/savings (−40–65%), spot (−70–90%), free tier | **Tier 2** — cheap lever, big realism |
| 8 | **AI / LLM** | per-token inference, embeddings, vector DB, GPUs | **Tier 2 (flag as priority)** — Keystone *models AI/MCP systems*; can dominate their bills |
| 9 | **Third-party SaaS** | payments (Stripe ≈2.9%+30¢ of revenue), auth (Auth0/Clerk), email/SMS (SendGrid/Twilio), search, maps | **Defer** — open-ended; Stripe is %-of-revenue (needs a revenue input). Its own future piece. |
| 10 | **Software licensing** | commercial DB (Oracle/SQL Server), OS licenses | **Defer** |
| 11 | **Support & compliance** | cloud support plans (% of bill), SOC2/audits, security tooling | **Defer** |
| 12 | **On-premise / hybrid (capex TCO)** | hardware purchase + depreciation, power, cooling, datacenter space, on-site staff | **Out of scope** — a fundamentally different "buy not rent" model; Keystone is cloud-design-focused. Possible *future* "deployment target" dimension; a large separate effort, not this. |
| 13 | **People / ops, DevOps tooling, taxes/FX** | engineer time, CI subscriptions, sales tax, currency | **Out** — not the system's infrastructure cost; not what Keystone validates. |

## Decision (proposed)

### 1. A usage-based cost layer (Tiers 1–2), engine-computed
Add, alongside the existing per-instance cost, a **usage cost** the engine derives from the model's own workload:
- **New usage inputs on the model** (declarative, never code): per-flow / per-component figures the engine can already reach or that the user supplies — e.g. average **payload/response size**, **egress fraction**, **stored GB**, **requests/sec** (the engine already has request rates from the flows). These are *inputs*, tagged `ASSUMPTION` until grounded — same honesty as everything else.
- **New grounded per-unit rates** (extend `GROUNDABLE_METRICS`, ADR-006/`docs/12`): e.g. `usd_minor_per_gb_egress`, `usd_minor_per_gb_month_storage`, `usd_minor_per_million_requests`. Each is researched + cited + QA-gated exactly like the per-machine prices we just shipped.
- **Total cost = per-instance compute + Σ(usage × grounded rate)** — all integer minor units (ADR-008), all summed by `simulation.py`. The report shows the **breakdown** (compute vs egress vs storage vs requests), so the user sees where the money goes — and which lines are grounded vs assumed.

### 2. A pricing-model discount lever (Tier 2)
A single, explicit multiplier on compute: `on_demand` (1.0) / `reserved_1yr` / `reserved_3yr` / `spot`, grounded to published discount ratios. Cheap, and it's the difference between a believable bill and a 2× overstatement.

### 3. AI/LLM as a first-class cost (Tier 2, flagged priority)
For AI/agent systems (Keystone has MCP/agent blueprints), add an LLM cost driven by a grounded **per-token** rate × the modelled token volume. Likely its own component kind + metric. Recommended early because it can be the *dominant* cost of an AI system and is invisible today.

### 4. Hard boundaries (so scope doesn't creep)
- **On-premise (capex TCO) is out** — different model entirely; recorded as a known boundary, a future "deployment target" if ever.
- **Third-party SaaS / licensing / support** are deferred to their own ADRs (esp. %-of-revenue pricing, which needs a revenue input Keystone doesn't model yet).
- **Every number stays engine-computed** (prime directive); the LLM may set *inputs*, never compute a cost. Rates are grounded with citations, never invented.

## Recorded dissent (kept, not smoothed)
- **YAGNI skeptic:** is a usage layer too much at L0? *Accepted, scoped:* Tier 1 (egress + storage + requests) is where the real money hides and where "compute-only" actively misleads — high value. Tiers below it are deferred/out precisely to avoid over-build.
- **Accuracy purist:** usage inputs (payload size, egress %) are themselves guesses. *Accepted:* they ship `ASSUMPTION` with bands and feed the same "where this is wrong" honesty; a grounded *rate* on a guessed *volume* is still clearly labelled.
- **Prime-directive guard:** more cost math = more places a number could leak from the LLM. *Accepted:* the engine remains the sole writer; the `Metric` envelope (ADR-007) + the integer-cents `Money` rule (ADR-008) already constrain it; add an invariant test.

## Confidence
**High** that Tier 1 (usage-based egress/storage/requests) is the right, high-value next step and fits the existing grounding machinery. **Medium** on the surface area (new model inputs + report breakdown + new grounded rates). **This is why it's Proposed** — Bifola picks the scope tiers before any build.

## Kill criteria (revisit if…)
- Any cost is computed outside `simulation.py` / by the LLM → prime-directive breach.
- A usage *rate* ships `GROUNDED` without a resolvable citation, or money appears as a float → ADR-006 / ADR-008 breach.
- Scope creeps into on-prem TCO or %-of-revenue SaaS without its own ADR.

## Consequences
Closes the biggest honesty gap in the cost number (data egress + the discount blind spot) and makes "total monthly cost" mean it — at the cost of new model inputs, new grounded rates, and a report breakdown. On-prem and third-party SaaS stay explicitly out, recorded so the boundary is a decision, not an omission.

---

**Decision needed from Bifola:** which tiers to build? My recommendation: **Tier 1 now** (usage-based egress/storage/requests — the realism unlock), **Tier 2 next** (discount lever + AI/LLM token cost), **defer** the rest, **on-prem out**.
