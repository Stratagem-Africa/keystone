# Keystone Stress-Test Report — URL Shortener (from note)

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 100 req/s — placeholder workload (stub — document not read)
**Overall confidence:** medium-high (lightly loaded; estimates most reliable here)
**Reproduce:** engine v0.0.1 · model 'URL Shortener (from note)' · deterministic (identical inputs → identical output)

## Verdict

- **Bottleneck:** App server (utilisation 10%)
- **Max sustainable load:** ~850 req/s at the 85% safe ceiling · ~1,000 req/s theoretical
- **Latency (dominant path):** p50 ~12 ms · p95 ~52 ms · p99 ~80 ms (mean 17 ms)
- **Single points of failure:** Load balancer, Primary database
- **Estimated monthly cost:** ~$0.00/month

## Headline metrics (model · confidence)

| Metric | Value | Model | Confidence |
|---|--:|---|:--|
| bottleneck_utilization | 10% | max rho = arrival / capacity | medium-high |
| breakpoint_rps_safe | 850 req/s | system_rps * (85% ceiling / rho_max) | medium-high |
| breakpoint_rps_theoretical | 1,000 req/s | system_rps * (1.0 / rho_max) | medium-high |
| mean_latency_ms | 17 ms | sum of M/M/1 sojourn W=S/(1-rho) along the dominant flow | medium-high |
| p50_ms | 12 ms | exponential-tail: mean * ln(2) | medium-high |
| p95_ms | 52 ms | exponential-tail: mean * ln(20) | medium-high |
| p99_ms | 80 ms | exponential-tail: mean * ln(100) | medium-high |
| monthly_cost | $0.00/mo | compute (× pricing model) + usage (egress/storage/requests) + AI tokens at ASSUMPTION rates | medium-high |

## Component load

| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |
|---|--:|--:|--:|--:|:--|
| App server | 100 | 1,000 | 10% | 11.1 | ok |
| Primary database | 100 | 2,000 | 5% | 5.3 | ok |
| Load balancer | 100 | 20,000 | 0% | 1.0 | ok |

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

## How these numbers were computed

- Offered load: 100 req/s split across 1 flow(s) by share (request 100%).
- Arrival per component = sum over flows of system_rps * flow.share * visit_prob along its path (open Jackson network).
- Utilisation rho = arrival / capacity, where capacity = per_instance_rps * instances.
- Bottleneck = highest rho -> App server at rho=0.10 (100 / 1,000 rps).
- Max sustainable load = system_rps * (ceiling / rho_max): safe@85% ~ 850 req/s, theoretical@100% ~ 1,000 req/s.
- Latency = sum of M/M/1 sojourn (service / (1 - rho)) * visit_prob along the dominant flow ('request', 100% share) -> mean 17 ms.
- Percentiles via an exponential-tail approximation: p50/p95/p99 = mean x 0.69/3.00/4.61 (over-states the tail; treat as a directional upper bound).
- Monthly cost = compute $0.00 = $0.00 (integer cents; usage rates ASSUMPTION).

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost = per-instance compute × the chosen pricing-model discount + declared usage (egress/storage/requests) + AI/LLM tokens (input/output) at ASSUMPTION rates (ADR-009 Tiers 1–2). Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. AI token rates are a placeholder model class (real prices vary ~100× by model). All these rates are uncited ASSUMPTION seeds until grounded. Volumes are 0 unless a component declares them. Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope.
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| ingestion | Stub model — a placeholder topology, not derived from the document. | low | ASSUMPTION |
