# Keystone Stress-Test Report — URL Shortener

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 10,000 req/s — 99:1 read:write, cache-aside
**Overall confidence:** medium (directional; within the model's reliable band)
**Reproduce:** engine v0.0.1 · model 'URL Shortener' · deterministic (identical inputs → identical output)

## Verdict

- **Bottleneck:** App tier (t4g.medium x12) (utilisation 69%)
- **Max sustainable load:** ~12,240 req/s at the 85% safe ceiling · ~14,400 req/s theoretical
- **Latency (dominant path):** p50 ~20 ms · p95 ~86 ms · p99 ~133 ms (mean 29 ms)
- **Single points of failure:** Application Load Balancer, Redis cache (r7g.large), PostgreSQL primary (r7g.large)
- **Estimated monthly cost:** ~$1,045.00/month

## Headline metrics (model · confidence)

| Metric | Value | Model | Confidence |
|---|--:|---|:--|
| bottleneck_utilization | 69% | max rho = arrival / capacity | medium |
| breakpoint_rps_safe | 12,240 req/s | system_rps * (85% ceiling / rho_max) | medium |
| breakpoint_rps_theoretical | 14,400 req/s | system_rps * (1.0 / rho_max) | medium |
| mean_latency_ms | 29 ms | sum of M/M/1 sojourn W=S/(1-rho) along the dominant flow | medium |
| p50_ms | 20 ms | exponential-tail: mean * ln(2) | medium |
| p95_ms | 86 ms | exponential-tail: mean * ln(20) | medium |
| p99_ms | 133 ms | exponential-tail: mean * ln(100) | medium |
| monthly_cost | $1,045.00/mo | compute + usage (egress/storage/requests) at ASSUMPTION rates | medium |

## Component load

| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |
|---|--:|--:|--:|--:|:--|
| App tier (t4g.medium x12) | 10,000 | 14,400 | 69% | 26.2 | ok |
| Application Load Balancer | 10,000 | 30,000 | 33% | 1.5 | ok |
| PostgreSQL primary (r7g.large) | 1,090 | 8,000 | 14% | 5.8 | ok |
| Redis cache (r7g.large) | 9,900 | 100,000 | 10% | 0.6 | ok |

## Design decisions (council)

> _Council running in DETERMINISTIC STUB mode — illustrative ADRs, not live reasoning. Provide a Claude API key to activate the real consensus engine._

### Datastore — confidence: high
**Decision:** Single relational primary (PostgreSQL) for the mapping table.

**Rationale:** Workload is simple key->value with strong-read tolerance once cached; a relational primary is the boring, reliable default.

**Recorded dissent:**
- Data engineer: a KV store (DynamoDB) scales writes more cheaply at very high create volume; revisit if write share rises.

**Kill criteria (revisit this decision if):**
- Create (write) traffic exceeds ~30% of total
- Mapping table exceeds single-primary write capacity

### Caching — confidence: high
**Decision:** Cache-aside on the redirect (read) path with a high hit-rate cache.

**Rationale:** Redirects dominate traffic and are highly cacheable; the cache shields the primary from the read storm.

**Recorded dissent:**
- SRE: the cache is now load-bearing -- a cold cache or stampede melts the DB. Add request-coalescing / stampede protection.

**Kill criteria (revisit this decision if):**
- Cache hit-rate falls below ~70% in production
- No stampede protection before launch

### Resilience — confidence: med
**Decision:** Add a read replica and cache failover before production.

**Rationale:** A single primary and single cache are single points of failure.

**Recorded dissent:**
- YAGNI-skeptic: acceptable to defer for a prototype (Tier-0), but NOT for external traffic (Tier-1).

**Kill criteria (revisit this decision if):**
- Going to external/production traffic with 1 DB + 1 cache

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
- Latency = sum of M/M/1 sojourn (service / (1 - rho)) * visit_prob along the dominant flow ('redirect', 99% share) -> mean 29 ms.
- Percentiles via an exponential-tail approximation: p50/p95/p99 = mean x 0.69/3.00/4.61 (over-states the tail; treat as a directional upper bound).

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost = per-instance compute + declared usage (egress/storage/requests) at ASSUMPTION rates (ADR-009 Tier 1); usage is 0 unless a component declares it, and the rates are uncited seeds until grounded. Discounts (reserved/spot) and other services are not yet modelled.
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| workload | 10,000 req/s peak, 99:1 read:write (redirects:creates) | med | ASSUMPTION |
| cache | Cache hit-rate 90% on the redirect path | med | ASSUMPTION |
| db | Single PostgreSQL primary sized at ~8k rps | low | ASSUMPTION |
| app | App server ~1,200 rps/instance (lightweight redirect handler) | low | ASSUMPTION |
