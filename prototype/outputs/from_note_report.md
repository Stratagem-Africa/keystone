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

| Metric | Value | Range (cited inputs) | Model | Confidence |
|---|--:|--:|---|:--|
| bottleneck_utilization | 10% | — | max rho = arrival / capacity | medium-high |
| breakpoint_rps_safe | 850 req/s | — | system_rps * (85% ceiling / rho_max) | medium-high |
| breakpoint_rps_theoretical | 1,000 req/s | — | system_rps * (1.0 / rho_max) | medium-high |
| mean_latency_ms | 17 ms | 17 ms – 19 ms | sum of M/M/1 sojourn W=S/(1-rho) along the dominant flow | medium-high |
| p50_ms | 12 ms | 12 ms – 13 ms | exponential-tail: mean * ln(2) | medium-high |
| p95_ms | 52 ms | 50 ms – 58 ms | exponential-tail: mean * ln(20) | medium-high |
| p99_ms | 80 ms | 77 ms – 89 ms | exponential-tail: mean * ln(100) | medium-high |
| monthly_cost | $0.00/mo | — | compute (× pricing model) + usage (egress/storage/requests) + AI tokens at GROUNDED (cited) rates | medium-high |

_Range = the output span when each GROUNDED input is swept across its **cited** confidence band (assumed / reconciled inputs held fixed). It expresses input-evidence uncertainty only — **not** a validated-accuracy guarantee, and the true value can fall outside it. Accuracy stays **L0 (Directional)** until field-calibrated._

## Component load

| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |
|---|--:|--:|--:|--:|:--|
| App server | 100 | 1,000 | 10% | 11.1 | ok |
| Primary database | 100 | 2,000 | 5% | 5.3 | ok |
| Load balancer | 100 | 20,000 | 0% | 1.0 | ok |

## Grounding & reconciliation (input evidence)

Input numbers matched to **cited benchmark evidence**. The engine still computed every result above; this annotates the *inputs* only. **GROUNDED** = your value sits inside the cited band; **RECONCILE** = it falls outside, and your value was **kept** (not overwritten).

| Component | Input | Your value | Grounded central | Cited band | Status | Source |
|---|---|--:|--:|:--:|:--|:--|
| Load balancer | base_latency_ms | 1.00 ms | 1.00 ms | 0.40–3.00 ms | GROUNDED ✓ | AWS — Application Load Balancer access logs (official docs) |
| Load balancer | per_instance_rps | 20,000 rps | 350,000 rps | 315,000–385,000 rps | RECONCILE ⚠ | NGINX/F5 — Sizing Guide for Deploying NGINX Plus on Bare Metal Servers (official datasheet, published 11 Nov 2019; retrieved via Internet Archive OCR full-text) |
| App server | per_instance_rps | 1,000 rps | 4,000 rps | 2,000–8,000 rps | RECONCILE ⚠ | Sharkbench (go-gin web benchmark) |
| Primary database | base_latency_ms | 5.00 ms | 0.30 ms | 0.15–0.80 ms | RECONCILE ⚠ | computingforgeeks (PostgreSQL vs MySQL vs MariaDB benchmark) |
| Primary database | monthly_cost_per_instance | $0.00/mo | $122.10/mo | $109.89–$134.31 | RECONCILE ⚠ | https://www.digitalocean.com/pricing/managed-databases |
| Primary database | per_instance_rps | 2,000 rps | 8,133 rps | 4,800–29,000 rps | RECONCILE ⚠ | ClickHouse Blog — PostgresBench: A Reproducible Benchmark for Postgres Services |

**Reconcile — your value is outside the cited band (kept, not overwritten):**
- **Load balancer** · `per_instance_rps`: you have **20,000 rps**, the cited evidence says **350,000 rps** (band 315,000–385,000 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **App server** · `per_instance_rps`: you have **1,000 rps**, the cited evidence says **4,000 rps** (band 2,000–8,000 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Primary database** · `base_latency_ms`: you have **5.00 ms**, the cited evidence says **0.30 ms** (band 0.15–0.80 ms). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Primary database** · `monthly_cost_per_instance`: you have **$0.00/mo**, the cited evidence says **$122.10/mo** (band $109.89–$134.31). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Primary database** · `per_instance_rps`: you have **2,000 rps**, the cited evidence says **8,133 rps** (band 4,800–29,000 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.

**Evidence (resolvable sources):**
- AWS — Application Load Balancer access logs (official docs) — https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html
- HAProxy Technologies — 'HAProxy Forwards Over 2 Million HTTP Requests per Second on a Single AWS Arm Instance' — https://www.haproxy.com/blog/haproxy-forwards-over-2-million-http-requests-per-second-on-a-single-aws-arm-instance
- Istio — 'Best Practices: Benchmarking Service Mesh Performance' (Envoy sidecar overhead) — https://istio.io/latest/blog/2019/performance-best-practices/
- NGINX/F5 — Sizing Guide for Deploying NGINX Plus on Bare Metal Servers (official datasheet, published 11 Nov 2019; retrieved via Internet Archive OCR full-text) — https://ia801500.us.archive.org/31/items/sizing-guide-for-deploying-nginx-plus-on-bare-metal-servers-2019-11-09/sizing-guide-for-deploying-nginx-plus-on-bare-metal-servers-2019-11-09_djvu.txt
- Internet Archive item landing page (provenance for the OCR full-text above) — https://archive.org/details/sizing-guide-for-deploying-nginx-plus-on-bare-metal-servers-2019-11-09
- NGINX/F5 — NGINX Plus Sizing Guide: How We Tested (methodology, corroborates test conditions) — https://www.f5.com/company/blog/nginx/nginx-plus-sizing-guide-how-we-tested
- Sharkbench (go-gin web benchmark) — https://sharkbench.dev/web/go-gin
- nDmitry/web-benchmarks (GitHub) — https://github.com/nDmitry/web-benchmarks
- DEV.to — Under Pressure: Benchmarking Node.js on a Single-Core EC2 — https://dev.to/ocodista/under-pressure-benchmarking-nodejs-on-a-single-core-ec2-5ghe
- computingforgeeks (PostgreSQL vs MySQL vs MariaDB benchmark) — https://computingforgeeks.com/database-benchmark-postgresql-mysql-mariadb/
- DoltHub Blog — Postgres vs MySQL Sysbench Latency — https://www.dolthub.com/blog/2024-07-16-mysql-postgres-sysbench-latency/
- faucetDB (MCP database benchmark) — https://faucetdb.ai/blog/mcp-database-benchmark/
- https://www.digitalocean.com/pricing/managed-databases — PostgreSQL plan table, 8 GiB row
- https://docs.digitalocean.com/products/databases/postgresql/details/pricing/ — PostgreSQL pricing overview
- ClickHouse Blog — PostgresBench: A Reproducible Benchmark for Postgres Services — https://clickhouse.com/blog/postgresbench
- Severalnines — Benchmarking Managed PostgreSQL Cloud Solutions: Part Two - Amazon RDS — https://severalnines.com/blog/benchmarking-managed-postgresql-cloud-solutions-part-two-amazon-rds/

## Cost rate evidence (grounded)

The per-unit cost rates are matched to **cited** vendor/benchmark pricing (researched + adversarially verified, ratified). Values are the grounded centrals; the band shows the real provider/model spread. Rates apply only to the cost lines a model actually uses.

| Rate | Grounded value | Band | Source |
|---|--:|:--:|:--|
| egress | $0.090/GB | $0.087–$0.120 | AWS (via leanopstech) |
| storage | $0.0210/GB-mo | $0.0180–$0.0253 | AWS S3 (CloudZero) |
| requests | $3.00/1M req | $1.00–$3.50 | AWS API Gateway (official, T1) |
| LLM input | $0.50/1M tok | $0.10–$1.00 | Anthropic (vendor) |
| LLM output | $4.00/1M tok | $0.40–$9.00 | Anthropic (vendor) |
| reserved 1yr | 30% off | 28–42% off | AWS Savings Plans (vendor doc) |
| reserved 3yr | 55% off | 46–72% off | AWS EC2 Reserved Instances (vendor) |
| spot | 77% off | 55–91% off | AWS EC2 Spot (vendor) |

**Evidence (resolvable sources):**
- AWS (Usage.ai) — https://www.usage.ai/blogs/aws/reserved-instances/
- AWS (Usage.ai) — https://www.usage.ai/blogs/aws/savings-plans/ec2/1-year-vs-3-year/
- AWS (via leanopstech) — https://leanopstech.com/blog/aws-data-transfer-pricing-2026/
- AWS API Gateway (official, T1) — https://aws.amazon.com/api-gateway/pricing/
- AWS EC2 Reserved Instances (vendor) — https://aws.amazon.com/ec2/pricing/reserved-instances/
- AWS EC2 Spot (vendor) — https://aws.amazon.com/ec2/spot/
- AWS S3 (CloudZero) — https://www.cloudzero.com/blog/s3-pricing/
- AWS Savings Plans (vendor doc) — https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-applying.html
- AWS Spot (nOps) — https://www.nops.io/blog/aws-spot-instance-pricing/
- Anthropic (vendor) — https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic corroboration (CloudZero) — https://www.cloudzero.com/blog/claude-api-pricing/
- Azure (ProsperOps) — https://www.prosperops.com/blog/azure-savings-plan-vs-reserved-instances/
- Azure (via egresscost.com) — https://egresscost.com/azure/
- Azure APIM (apigatewaycost.com) — https://apigatewaycost.com/azure
- Azure Blob (nOps) — https://www.nops.io/blog/azure-storage-pricing/
- Azure Spot (Flexera) — https://www.flexera.com/blog/finops/azure-pricing-azure-spot-pricing-how-much-do-azure-spot-vms-really-cost/
- Cross-check aggregator — https://egresscost.com/
- Cross-provider (Finout) — https://www.finout.io/blog/cloud-storage-pricing-comparison
- Google (vendor) — https://ai.google.dev/gemini-api/docs/pricing
- Google Cloud (via cloudbolt) — https://www.cloudbolt.io/gcp-cost-optimization/gcp-egress-pricing/
- Google Cloud API Gateway (apigatewaycost.com) — https://apigatewaycost.com/google-cloud
- Google Cloud CUD (vendor doc) — https://docs.cloud.google.com/compute/docs/instances/committed-use-discounts-overview
- Google Cloud Spot (vendor blog) — https://cloud.google.com/blog/products/compute/google-cloud-spot-vm
- Google Cloud Spot (vendor doc) — https://docs.cloud.google.com/compute/docs/instances/spot
- Google Cloud Storage (CloudZero) — https://www.cloudzero.com/blog/gcp-storage-pricing/
- Multi-provider (Zuplo 2026) — https://zuplo.com/learning-center/api-gateway-pricing-comparison-2026
- OpenAI (vendor) — https://developers.openai.com/api/docs/pricing
- OpenAI corroboration (aipricing.guru) — https://www.aipricing.guru/openai-pricing/

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
- Monthly cost = compute $0.00 = $0.00 (integer cents; usage rates GROUNDED (cited)).

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities are SEED benchmarks tagged ASSUMPTION, not calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost = per-instance compute × the chosen pricing-model discount + declared usage (egress/storage/requests) + AI/LLM tokens (input/output) at GROUNDED (cited) rates (ADR-009 Tiers 1–2). Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. AI token rates span a wide model-class band (real prices vary ~100× by model). These per-unit rates are GROUNDED to cited benchmarks (see *Cost rate evidence*). Volumes are 0 unless a component declares them. Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope.
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.
- Some inputs above are GROUNDED to cited benchmarks matched by component **kind** (not your exact instance type / region / workload), so treat them as directional evidence, not stack-calibrated truth. RECONCILE rows fall outside the cited band and kept **your** value — a human should check them. The citations are AI-proposed, pending ratification.

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| ingestion | Stub model — a placeholder topology, not derived from the document. | low | ASSUMPTION |
