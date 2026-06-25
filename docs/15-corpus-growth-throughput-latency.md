# 15 — Growing the grounding corpus: throughput + latency benchmarks (verification record)

> **Status:** PROPOSAL — pending Bifola's ratification. **AI proposes, a human ratifies** grounded data (`docs/12 §5`). Adds **8** cited component benchmarks to `prototype/keystone/benchmarks/corpus.jsonl` (now 27 datapoints). Grounding is **active** (`KB_PROVIDER=curated`), so merging this immediately enriches the reports — review the citations before merging.

**Why throughput/latency, not cost.** The gap analysis showed cost metrics are blocked by a *context* problem (4 disjoint per-cloud prices → the KB refuses or picks the wrong cloud — that needs context-aware matching, a later slice). Throughput (rps) + latency (ms) were just **missing**, so each one grounded turns an ungrounded row into GROUNDED (or a valuable RECONCILE flag). 13 candidate (kind, metric) gaps were researched.

**Method.** Each candidate was web-researched (≥2 cited sources with a stated config), then attacked by **3 independent devil's-advocate verifiers** (citation-resolution / operating-point / band-honesty, refute-by-default, re-fetching every cited number), then I spot-checked the load-bearing citations by hand. Everything is **L0 directional** — honestly wide bands, not per-stack guarantees.

---

## Survived → GROUND (8)

| kind | metric | value | band | unit | tier | confirmed |
|---|---|--:|:--:|:--|:--:|:--:|
| app_server | per_instance_rps | 4,000 | 2,000–8,000 | rps | T2 | 3/3 |
| cache (redis) | per_instance_rps | 110,000 | 70,000–180,000 | rps | T1 | 3/3 |
| sql_db | base_latency_ms | 0.3 | 0.15–0.8 | ms | T2 | 2/3 |
| load_balancer | base_latency_ms | 1 | 0.4–3 | ms | T1 | 3/3 |
| queue | per_instance_rps | 10,000 | 1,000–50,000 | rps | T2 | 2/3 |
| replica | per_instance_rps | 10,000 | 5,000–50,000 | rps | T2 | 2/3 |
| external_api (payment) | per_instance_rps | 100 | 7–140 | rps | T1 | 3/3 |
| external_api (payment) | base_latency_ms | 140 | 80–250 | ms | T2 | 3/3 |

**The adversarial pass earned its keep** — it caught the cherry-picks and corrected real over-optimism:
- **Redis cache:** central is the **non-pipelined** ~110k ops/s operating point; the ~1.5M **pipelined** headline was correctly *excluded* (the mistake we made earlier with raw throughput numbers).
- **Payment gateway capacity:** the model assumed **5,000 rps**, but a real payment API rate-**limits** to ~**100 rps** (Stripe live mode 100/s, verified independently; Adyen 140/s). → flagged **RECONCILE** — a genuine design over-optimism.
- **sql_db latency:** server-side simple point-query latency is ~**0.3 ms** (sysbench/oltp_point_select); the modeled 5 ms (which bundles network/app) now shows **RECONCILE**.
- **app_server throughput:** honest wide band 2k–8k; the modeled 1,200 rps sits *below* it → **RECONCILE** (the model may be conservative or doing per-request DB work).

## Did NOT survive → stay ASSUMPTION (5)
`app_server base_latency_ms`, `queue base_latency_ms`, `replica base_latency_ms`, `cdn per_instance_rps`, `cdn base_latency_ms`. **The verifiers caught fabricated/unresolvable citations** in three of these (a invented "P50" framing; a non-resolving Conduktor URL; an F5/NGINX page quoted as "keepalive" when it says "new connection" — the opposite) — so they correctly stayed ASSUMPTION rather than grounding on invented evidence. The other two had a cherry-picked operating point (CDN POP-internal serve-time vs client TTFB; replica latency from a 14-query transaction, not a single read).

## Coverage impact
Grounding roughly **tripled**: across url_shortener + ticket_booking, **11 metrics now GROUNDED + 9 RECONCILE** (was ~3 GROUNDED). Every RECONCILE is an honest "double-check this input" signal.

## What's weak / double-check before ratifying
1. **Bands are honestly WIDE** (e.g. app_server 2k–8k rps spans 4×) because throughput is framework/workload-dependent — these GROUND a *directional* range, not a calibrated truth. That's the honest L0 state.
2. **`replica` per_instance_rps** is down-scaled from large-hardware benchmarks (AlloyDB/Crunchy ran 64-vCPU, 200k–467k TPS) to a "single typical replica" band — the weakest extrapolation; re-check if it matters.
3. **`external_api`** rps is a **rate limit**, not a throughput benchmark — correct for a payment gateway, but it's a different *kind* of number (a ceiling the provider imposes).
4. **RECONCILE rows are the point, not a bug** — they flag where the modeler's value diverges from cited evidence (payment-gateway capacity, db latency, app throughput). A human should look at each.
5. **Provenance:** no invented citation survived into a GROUND datapoint (the verifiers + my spot-check confirmed; the fabrications were caught and the datapoints kept ASSUMPTION). The residual risk is operating-point/SKU mismatch, not fabrication.

Per-datapoint citations, configs, bands, and adversarial summaries are in `corpus.jsonl` (the 8 new lines).
