# 14 — Grounding the cost rates (verification record)

> **Status:** PROPOSAL — pending Bifola's ratification of the citations. **AI proposes, a human ratifies** grounded data (`docs/12 §5`). The machine-readable evidence is `prototype/keystone/benchmarks/grounded_pricing_rates.json`; the engine seed values (`PricingRates`, `COMPUTE_PRICING_RETAINED_BP`) now mirror the grounded centrals, and `tests/test_grounded_rates.py` locks them to the evidence. The grounding is **not** yet wired into the engine's KB (`KB_PROVIDER` stays stub) — that activation is a separate Bifola trigger.

**Method.** Each of the 8 ADR-009 cost rates was researched from real vendor/aggregator pricing pages, then attacked by **3 independent devil's-advocate verifiers** (lenses: *citation-resolution* — re-fetch every URL and confirm the number appears; *unit-region-SKU* — attack the unit/region/tier/staleness; *cherry-pick-band* — attack best-case cherry-picking and dishonest bands), each told to **refute by default**. Load-bearing rates were then spot-checked again by hand. Region/SKU scope is **US-East / standard tiers**, June 2026.

---

## Summary table

| rate | seed (old guess) | grounded central | band | tier | confirmed | decision |
|---|---|---|---|---|---|---|
| egress | $0.09 /GB | **$0.09 /GB** | $0.087 – $0.12 | T2 | 3/3 | GROUND |
| storage | $0.023 /GB-mo | **$0.021 /GB-mo** | $0.018 – $0.0253 | T2 | 3/3 | GROUND |
| requests | $1.00 /1M *(3× low)* | **$3.00 /1M** | $1.00 – $3.50 | T1 | 3/3 | GROUND |
| llm_input | $0.80 /1M | **$0.50 /1M** | $0.10 – $1.00 | T1 | 3/3 | GROUND |
| llm_output | $4.00 /1M | **$4.00 /1M** | $0.40 – $9.00 | T1 | 1/3\* | GROUND (band corrected) |
| reserved_1yr | 40% off | **30% off** | 28% – 42% | T2 | 2/3 | GROUND (top lowered) |
| reserved_3yr | 60% off | **55% off** | 46% – 72% | T1 | 3/3 | GROUND |
| spot | 80% off | **77% off** | 55% – 91% | T1 | 2/3 | GROUND (central lowered) |

\* `llm_output` came back 1/3 because two skeptics correctly **rejected my first proposal as too narrow** (it excluded the current Gemini 3.5 Flash $9.00); the corrected band in the table is the honest one they converged on. Nothing was kept as a bare ASSUMPTION.

**What the adversarial pass changed vs the guesses:** `requests` was **3× too low**; `llm_input` came down ($0.80→$0.50); `reserved_1yr` (40→30% off) and `spot` (80→77% off, floor to 55%) were **over-optimistic** and were pulled to conservative, money-safe values; `llm_output`'s band was widened to span the real ~22× spread of the small/fast model class.

---

## What is still a guess / double-check before you ratify

1. **Two T2 rates lean on aggregators, not vendor pages.** `egress` and `storage` cite reputable aggregators/blogs because the official AWS/Azure/Google pricing pages are JavaScript-rendered and didn't expose clean numbers on fetch. Every number was independently corroborated by multiple sources, but no canonical first-party table was read directly — open the live vendor pages in a browser if you want these at T1.
2. **`llm_output` is the weakest-confirmed** (1/3 on the first attempt). The corrected band is sound, but re-pull the live Anthropic/Google/OpenAI pages before ratifying — model line-ups churn fast (Gemini 2.0 Flash shut June 2026; Haiku 3.5 retired on the first-party API). **Re-verify LLM prices quarterly.**
3. **The two "lowered" discount rates were originally over-optimistic.** `reserved_1yr` (top cut 55→42%) and `spot` (central cut 80→77%, floor to 55%) were pulled down by the skeptics — sanity-check that the conservative direction matches how you want a *money* model to err.
4. **All discount rates are instrument- and SKU-dependent, not single numbers.** A 1-year discount swings with flexible-vs-resource-locked commitment, instance family, region, OS, and payment option. Vendor "up to 55/66/72%" headlines are mostly 3-year and/or all-upfront and/or memory-optimized maxima — never read the central as a guaranteed rate.
5. **Per-GB storage is a small slice of real storage spend** — the $0.021 is *storage only* (excludes request/retrieval/egress charges).
6. **Scope is US-only, standard tiers.** Non-US regions cost materially more (e.g. São Paulo egress ~$0.15/GB); CDN/inter-region/peering egress and geo-redundant storage are separate, dearer SKUs that are out of scope.
7. **Spot savings are conditional, not contractual** — the 77% carries eviction risk (Azure 30s notice, AWS 2-min), operational cost the headline percentage doesn't show.
8. **Provenance:** no invented citations were found — every cited URL re-fetched and contained its quoted number, independently corroborated by separate search and a hand spot-check. The residual risk here is *scope/SKU mismatch*, not fabricated sources.

---

Per-rate citations, quoted numbers, conditions, caveats, and the full adversarial summary for each rate live in `prototype/keystone/benchmarks/grounded_pricing_rates.json`.
