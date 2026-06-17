# Keystone Stress-Test Report — URL Shortener

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 10,000 req/s — 99:1 read:write, cache-aside
**Overall confidence:** medium (directional; within the model's reliable band)

## Verdict

- **Bottleneck:** App tier (t4g.medium x12) (utilisation 69%)
- **Max sustainable load:** ~12,240 req/s at the 85% safe ceiling · ~14,400 req/s theoretical
- **Latency (dominant path):** p50 ~20 ms · p95 ~86 ms · p99 ~133 ms (mean 29 ms)
- **Single points of failure:** Application Load Balancer, Redis cache (r7g.large), PostgreSQL primary (r7g.large)
- **Estimated compute cost:** ~$1,045/month

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

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost is compute/instance only; data-transfer/egress and managed-service pricing nuances are not yet modelled.
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| workload | 10,000 req/s peak, 99:1 read:write (redirects:creates) | med | ASSUMPTION |
| cache | Cache hit-rate 90% on the redirect path | med | ASSUMPTION |
| db | Single PostgreSQL primary sized at ~8k rps | low | ASSUMPTION |
| app | App server ~1,200 rps/instance (lightweight redirect handler) | low | ASSUMPTION |
