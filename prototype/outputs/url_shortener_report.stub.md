# Keystone Stress-Test Report — URL Shortener

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 10,000 req/s — 99:1 read:write, cache-aside
**Overall confidence:** medium (directional; within the model's reliable band)
**Reproduce:** engine v0.0.1 · model 'URL Shortener' · deterministic (identical inputs → identical output)

## Verdict

- **Bottleneck:** App tier (t4g.medium x12) (utilisation 69%)
- **Max sustainable load:** ~12,240 req/s at the 85% safe ceiling · ~14,400 req/s theoretical
- **Latency (dominant path):** p50 ~8 ms · p95 ~33 ms · p99 ~51 ms (mean 11 ms)
- **Single points of failure:** Application Load Balancer, Redis cache (r7g.large), PostgreSQL primary (r7g.large)
- **Estimated monthly cost:** ~$1,045.00/month

## Headline metrics (model · confidence)

| Metric | Value | Model | Confidence |
|---|--:|---|:--|
| bottleneck_utilization | 69% | max rho = arrival / capacity | medium |
| breakpoint_rps_safe | 12,240 req/s | system_rps * (85% ceiling / rho_max) | medium |
| breakpoint_rps_theoretical | 14,400 req/s | system_rps * (1.0 / rho_max) | medium |
| mean_latency_ms | 11 ms | sum of M/M/c sojourn W=S+Wq (Erlang-C) along the dominant flow | medium |
| p50_ms | 8 ms | exponential-tail: mean * ln(2) | medium |
| p95_ms | 33 ms | exponential-tail: mean * ln(20) | medium |
| p99_ms | 51 ms | exponential-tail: mean * ln(100) | medium |
| monthly_cost | $1,045.00/mo | compute (× pricing model) + usage (egress/storage/requests) + AI tokens at ASSUMPTION rates | medium |

## Per-flow latency

_Each flow's own latency (M/M/1 sojourn along its path; exponential-tail percentiles). The headline latency above is the **dominant** flow; a minority flow on a different path can differ sharply — confirm the path that matters to your users._

| Flow | Share | Mean | p50 | p95 | p99 |
|---|--:|--:|--:|--:|--:|
| redirect | 99% | 11 ms | 8 ms | 33 ms | 51 ms |
| create | 1% | 16 ms | 11 ms | 47 ms | 72 ms |

## Component load

| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |
|---|--:|--:|--:|--:|:--|
| App tier (t4g.medium x12) | 10,000 | 14,400 | 69% | 8.4 | ok |
| Application Load Balancer | 10,000 | 30,000 | 33% | 1.5 | ok |
| PostgreSQL primary (r7g.large) | 1,090 | 8,000 | 14% | 5.8 | ok |
| Redis cache (r7g.large) | 9,900 | 100,000 | 10% | 0.6 | ok |

## Design decisions (council)

> _Council running in DETERMINISTIC STUB mode — illustrative ADRs, not live reasoning. Activate the real council with any provider — a free-tier Gemini/Groq key, a Claude key, or a local Ollama (no key, $0)._

### Datastore — confidence: high
**Decision:** URL Shortener keeps its system of record in PostgreSQL primary (r7g.large).

**Rationale:** A relational primary is the boring, reliable default; it is the component whose write path cannot be scaled out by adding instances, so the design hangs on it.

**Recorded dissent:**
- Data engineer: if writes dominate, a partitioned or KV store scales that path more cheaply than a single primary; revisit if the write share rises.

**Kill criteria (revisit this decision if):**
- Write traffic outgrows what one primary can serve
- A second service needs write access to the same tables

### Caching — confidence: med
**Decision:** Reads are shielded by Redis cache (r7g.large).

**Rationale:** The read path dominates, and a cache keeps that volume off the primary.

**Recorded dissent:**
- YAGNI-skeptic: a cache is a second source of truth and a new failure mode; do not add one before the read path is demonstrably the constraint.

**Kill criteria (revisit this decision if):**
- Cache hit-rate falls far enough that the primary sees the read storm
- Stale reads become user-visible in a way the product cannot accept

### Resilience — confidence: med
**Decision:** Single points of failure in this design: Application Load Balancer, Redis cache (r7g.large), PostgreSQL primary (r7g.large).

**Rationale:** Each of these is one instance; losing it takes the system with it.

**Recorded dissent:**
- YAGNI-skeptic: acceptable to defer for a prototype (Tier-0), but NOT for external traffic (Tier-1).

**Kill criteria (revisit this decision if):**
- Going to external/production traffic with a single-instance tier

## What-if interrogation

| Scenario | Bottleneck | Util | Max safe load (rps) |
|---|---|--:|--:|
| Cache cold / stampede (hit-rate 0%) | PostgreSQL primary (r7g.large) | 125% | 6,800 |
| 10x traffic (100k rps) | App tier (t4g.medium x12) | 694% | 12,240 |

## How these numbers were computed

- Offered load: 10,000 req/s split across 2 flow(s) by share (redirect 99%, create 1%).
- Arrival per component = sum over flows of system_rps * flow.share * visit_prob along its path (open Jackson network).
- Utilisation rho = arrival / capacity, where capacity = per_instance_rps * instances.
- Bottleneck = highest rho -> App tier (t4g.medium x12) at rho=0.69 (10,000 / 14,400 rps).
- Max sustainable load = system_rps * (ceiling / rho_max): safe@85% ~ 12,240 req/s, theoretical@100% ~ 14,400 req/s.
- Latency = sum of M/M/c sojourn (Erlang-C, over each tier's instances) * visit_prob along the dominant flow ('redirect', 99% share) -> mean 11 ms.
- Percentiles via an exponential-tail approximation: p50/p95/p99 = mean x 0.69/3.00/4.61 (over-states the tail; treat as a directional upper bound).
- Monthly cost = compute $1,045.00 = $1,045.00 (integer cents; usage rates ASSUMPTION).

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost = per-instance compute × the chosen pricing-model discount + declared usage (egress/storage/requests) + AI/LLM tokens (input/output) at ASSUMPTION rates (ADR-009 Tiers 1–2). Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. AI token rates are a placeholder model class (real prices vary ~100× by model). All these rates are uncited ASSUMPTION seeds until grounded. Volumes are 0 unless a component declares them. Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope.
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.
- Headline latency (mean/p50/p95/p99) is for the DOMINANT flow — 'redirect' (99% of traffic). Each flow's own latency is in the Per-flow latency table; a minority flow on a different (often worse) path can differ sharply.

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| workload | 10,000 req/s peak, 99:1 read:write (redirects:creates) | med | ASSUMPTION |
| cache | Cache hit-rate 90% on the redirect path | med | ASSUMPTION |
| db | Single PostgreSQL primary sized at ~8k rps | low | ASSUMPTION |
| app | App server ~1,200 rps/instance (lightweight redirect handler) | low | ASSUMPTION |
