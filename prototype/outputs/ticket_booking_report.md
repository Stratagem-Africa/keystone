# Keystone Stress-Test Report — Ticket Booking

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 5,000 req/s — 95% browse / 5% book (steady state)
**Overall confidence:** medium (directional; within the model's reliable band)

## Verdict

- **Bottleneck:** Booking app tier (utilisation 62%)
- **Max sustainable load:** ~6,800 req/s at the 85% safe ceiling · ~8,000 req/s theoretical
- **Latency (dominant path):** p50 ~21 ms · p95 ~93 ms · p99 ~142 ms (mean 31 ms)
- **Single points of failure:** Load balancer, Seat-availability cache, Booking request queue, Inventory DB (seats)
- **Estimated compute cost:** ~$895/month

## Component load

| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |
|---|--:|--:|--:|--:|:--|
| Booking app tier | 5,000 | 8,000 | 62% | 26.7 | ok |
| Load balancer | 5,000 | 40,000 | 12% | 1.1 | ok |
| Inventory DB (seats) | 250 | 3,000 | 8% | 6.5 | ok |
| CDN (event pages) | 4,750 | 80,000 | 6% | 2.1 | ok |
| Read replica | 475 | 8,000 | 6% | 4.3 | ok |
| Payment gateway | 250 | 5,000 | 5% | 126.3 | ok |
| Seat-availability cache | 4,750 | 100,000 | 5% | 0.5 | ok |
| Booking request queue | 250 | 20,000 | 1% | 2.0 | ok |

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
| Flash sale: 8× traffic, browsing → buying (50% book) | Inventory DB (seats) | 667% | 5,100 |
| Mild on-sale: 2× traffic, 20% book | Booking app tier | 125% | 6,800 |

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost is compute/instance only; data-transfer/egress and managed-service pricing nuances are not yet modelled.
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| workload | 5,000 req/s, 95% browse / 5% book (steady state) | med | ASSUMPTION |
| db | Single inventory DB sized ~3k writes/s; seat decrements are the contended path | low | ASSUMPTION |
| queue | Booking writes serialized through a queue to prevent overselling | med | ASSUMPTION |
