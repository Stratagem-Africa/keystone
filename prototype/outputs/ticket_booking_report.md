# Keystone Stress-Test Report — Ticket Booking

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 5,000 req/s — 95% browse / 5% book (steady state)
**Overall confidence:** medium (directional; within the model's reliable band)
**Reproduce:** engine v0.0.1 · model 'Ticket Booking' · deterministic (identical inputs → identical output)

## Verdict

- **Bottleneck:** Booking app tier (utilisation 62%)
- **Max sustainable load:** ~6,800 req/s [6,800–27,200] at the 85% safe ceiling · ~8,000 req/s theoretical
- **Latency (dominant path):** p50 ~21 ms [11–24] · p95 ~93 ms [46–103] · p99 ~142 ms [70–158] (mean 31 ms)
- **Single points of failure:** Load balancer, Seat-availability cache, Booking request queue, Inventory DB (seats)
- **Estimated monthly cost:** ~$895.00/month
- _`[low–high]` = confidence range from cited input evidence (details + 'measured on' below) — input-uncertainty only, **not** a validated-accuracy guarantee._

## Headline metrics (model · confidence)

| Metric | Value | Range (cited inputs) | Model | Confidence |
|---|--:|--:|---|:--|
| bottleneck_utilization | 62% | 16% – 62% | max rho = arrival / capacity | medium |
| breakpoint_rps_safe | 6,800 req/s | 6,800 req/s – 27,200 req/s | system_rps * (85% ceiling / rho_max) | medium |
| breakpoint_rps_theoretical | 8,000 req/s | 8,000 req/s – 32,000 req/s | system_rps * (1.0 / rho_max) | medium |
| mean_latency_ms | 31 ms | 15 ms – 34 ms | sum of M/M/1 sojourn W=S/(1-rho) along the dominant flow | medium |
| p50_ms | 21 ms | 11 ms – 24 ms | exponential-tail: mean * ln(2) | medium |
| p95_ms | 93 ms | 46 ms – 103 ms | exponential-tail: mean * ln(20) | medium |
| p99_ms | 142 ms | 70 ms – 158 ms | exponential-tail: mean * ln(100) | medium |
| monthly_cost | $895.00/mo | — | compute (× pricing model) + usage (egress/storage/requests) + AI tokens at GROUNDED (cited) rates | medium |

_Range = the output span when each GROUNDED input is swept across its **cited** confidence band (assumed / reconciled inputs held fixed). It expresses input-evidence uncertainty only — **not** a validated-accuracy guarantee, and the true value can fall outside it. A **—** means no grounded input moves that number (no cited spread to show) — it is not zero uncertainty. Accuracy stays **L0 (Directional)** until field-calibrated._

## Per-flow latency

_Each flow's own latency (M/M/1 sojourn along its path; exponential-tail percentiles). The headline latency above is the **dominant** flow; a minority flow on a different path can differ sharply — confirm the path that matters to your users._

| Flow | Share | Mean | p50 | p95 | p99 |
|---|--:|--:|--:|--:|--:|
| browse | 95% | 31 ms | 21 ms | 93 ms | 142 ms |
| book | 5% | 163 ms | 113 ms | 487 ms | 749 ms |

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

## Grounding & reconciliation (input evidence)

Input numbers matched to **cited benchmark evidence**, by component **kind**. The engine still computed every result above; this annotates the *inputs* only. **GROUNDED** = your value sits inside the cited band; **RECONCILE** = it falls outside, and your value was **kept** (not overwritten). **Measured on** shows the hardware / workload the benchmark actually ran on — check it matches your setup before trusting the band.

| Component | Input | Your value | Grounded central | Cited band | Status | Measured on | Source |
|---|---|--:|--:|:--:|:--|:--|:--|
| Load balancer | base_latency_ms | 1.00 ms | 1.00 ms | 0.40–3.00 ms | GROUNDED ✓ | Managed/software L7 load balancer (AWS ALB / HAProx… | AWS — Application Load Balancer access logs (official docs) |
| Load balancer | per_instance_rps | 40,000 rps | 350,000 rps | 315,000–385,000 rps | RECONCILE ⚠ | 8 CPU cores, 4 GB RAM, Intel Xeon E5-2699 v4 @ 2.2 … | NGINX/F5 — Sizing Guide for Deploying NGINX Plus on Bare Metal Servers (official datasheet, published 11 Nov 2019; retrieved via Internet Archive OCR full-text) |
| Booking app tier | per_instance_rps | 2,000 rps | 4,000 rps | 2,000–8,000 rps | GROUNDED ✓ | One app-server instance, ~2-4 vCPU (e.g. AWS c5.xla… | Sharkbench (go-gin web benchmark) |
| Seat-availability cache | base_latency_ms | 0.50 ms | 1.00 ms | 0.40–1.50 ms | GROUNDED ✓ | HPE ProLiant DL380 Gen10, one Intel Xeon Gold 6230 … | Redis official documentation — How fast is Redis? (redis-benchmark) |
| Seat-availability cache | per_instance_rps | 100,000 rps | 110,000 rps | 70,000–180,000 rps | GROUNDED ✓ | Redis single node, GET/SET, NON-pipelined (pipeline… | Redis official documentation (How fast is Redis? / Benchmarks, readthedocs) |
| Booking request queue | per_instance_rps | 20,000 rps | 10,000 rps | 1,000–50,000 rps | GROUNDED ✓ | Per single ordered queue unit (one RabbitMQ classic… | Confluent — Benchmarking RabbitMQ vs Kafka vs Pulsar (OpenMessaging Benchmark) |
| Inventory DB (seats) | base_latency_ms | 6.00 ms | 0.30 ms | 0.15–0.80 ms | RECONCILE ⚠ | PostgreSQL/MySQL/MariaDB, sysbench warm-cache singl… | computingforgeeks (PostgreSQL vs MySQL vs MariaDB benchmark) |
| Inventory DB (seats) | monthly_cost_per_instance | $300.00/mo | $122.10/mo | $109.89–$134.31 | RECONCILE ⚠ | Managed PostgreSQL — 8 GiB RAM / 4 vCPUs / 140 GiB … | https://www.digitalocean.com/pricing/managed-databases |
| Inventory DB (seats) | per_instance_rps | 3,000 rps | 8,133 rps | 4,800–29,000 rps | RECONCILE ⚠ | AWS RDS db.m8gd.4xlarge (16 vCPU / 64 GB, NVMe-back… | ClickHouse Blog — PostgresBench: A Reproducible Benchmark for Postgres Services |
| Read replica | per_instance_rps | 8,000 rps | 10,000 rps | 5,000–50,000 rps | GROUNDED ✓ | Single Postgres read replica, ~8-16 vCPU mid-size S… | Google Cloud (AlloyDB official OLTP benchmark docs) |
| Payment gateway | base_latency_ms | 120.00 ms | 140.00 ms | 80.00–250.00 ms | GROUNDED ✓ | Stripe/Adyen-class payment-gateway external HTTPS A… | Probecast — Adyen API status / latency monitoring (independent third-party) |
| Payment gateway | per_instance_rps | 5,000 rps | 100 rps | 7–140 rps | RECONCILE ⚠ | Payment-gateway-class third-party API, published pe… | Stripe Documentation — Rate limits |

**Reconcile — your value is outside the cited band (kept, not overwritten):**
- **Load balancer** · `per_instance_rps`: you have **40,000 rps**, the cited evidence says **350,000 rps** (band 315,000–385,000 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Inventory DB (seats)** · `base_latency_ms`: you have **6.00 ms**, the cited evidence says **0.30 ms** (band 0.15–0.80 ms). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Inventory DB (seats)** · `monthly_cost_per_instance`: you have **$300.00/mo**, the cited evidence says **$122.10/mo** (band $109.89–$134.31). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Inventory DB (seats)** · `per_instance_rps`: you have **3,000 rps**, the cited evidence says **8,133 rps** (band 4,800–29,000 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.
- **Payment gateway** · `per_instance_rps`: you have **5,000 rps**, the cited evidence says **100 rps** (band 7–140 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.

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
- Redis official documentation — How fast is Redis? (redis-benchmark) — https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- Redis official documentation (How fast is Redis? / Benchmarks, readthedocs) — https://redis-doc-test.readthedocs.io/en/latest/topics/benchmarks/
- Redis official documentation (Benchmarks, current docs) — https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- OneUptime — How to Benchmark Redis Performance with redis-benchmark — https://oneuptime.com/blog/post/2026-03-31-redis-benchmark-performance/view
- Confluent — Benchmarking RabbitMQ vs Kafka vs Pulsar (OpenMessaging Benchmark) — https://www.confluent.io/blog/kafka-fastest-messaging-system/
- Factor House — Kafka topic & partition best practices (citing Confluent, LinkedIn, Netflix, Uber) — https://factorhouse.io/articles/kafka-topic-partition-best-practices
- CloudAMQP — Part 2: RabbitMQ Best Practice for High Performance — https://www.cloudamqp.com/blog/part2-rabbitmq-best-practice-for-high-performance.html
- computingforgeeks (PostgreSQL vs MySQL vs MariaDB benchmark) — https://computingforgeeks.com/database-benchmark-postgresql-mysql-mariadb/
- DoltHub Blog — Postgres vs MySQL Sysbench Latency — https://www.dolthub.com/blog/2024-07-16-mysql-postgres-sysbench-latency/
- faucetDB (MCP database benchmark) — https://faucetdb.ai/blog/mcp-database-benchmark/
- https://www.digitalocean.com/pricing/managed-databases — PostgreSQL plan table, 8 GiB row
- https://docs.digitalocean.com/products/databases/postgresql/details/pricing/ — PostgreSQL pricing overview
- ClickHouse Blog — PostgresBench: A Reproducible Benchmark for Postgres Services — https://clickhouse.com/blog/postgresbench
- Severalnines — Benchmarking Managed PostgreSQL Cloud Solutions: Part Two - Amazon RDS — https://severalnines.com/blog/benchmarking-managed-postgresql-cloud-solutions-part-two-amazon-rds/
- Google Cloud (AlloyDB official OLTP benchmark docs) — https://docs.cloud.google.com/alloydb/docs/benchmark-oltp-performance-alloydb
- Crunchy Data (PostgreSQL 13 benchmark blog) — quote CORRECTED to figures verifiers confirmed on the page — https://www.crunchydata.com/blog/postgresql-13-benchmark-memory-speed-vs.-tps
- Severalnines (How to Benchmark PostgreSQL Performance) — https://severalnines.com/blog/benchmarking-postgresql-performance/
- AWS (Optimizing PostgreSQL on EC2 using EBS whitepaper) — https://docs.aws.amazon.com/whitepapers/latest/optimizing-postgresql-on-ec2-using-ebs/postgresql-benchmark-observations-and-considerations.html
- Probecast — Adyen API status / latency monitoring (independent third-party) — https://probecast.io/status/adyen-api
- The Stripe Latency Post-Mortem Every Engineer Should Read (Medium, secondary account of Stripe's March 2022 incident) — https://medium.com/@warstories/the-stripe-latency-post-mortem-every-engineer-should-read-before-launching-their-api-6514411772f8
- Stripe Documentation — Rate limits — https://docs.stripe.com/rate-limits
- Adyen Docs / API Explorer — Legal Entity Management v3 Overview (rate limits) — https://docs.adyen.com/api-explorer/legalentity/3/overview
- PayPal Developer — Payouts: Test and go live (rate limiting) — https://developer.paypal.com/docs/payouts/standard/integrate-api/test-and-go-live/

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

## What-if interrogation

| Scenario | Bottleneck | Util | Max safe load (rps) |
|---|---|--:|--:|
| Flash sale: 8× traffic, browsing → buying (50% book) | Inventory DB (seats) | 667% | 5,100 |
| Mild on-sale: 2× traffic, 20% book | Booking app tier | 125% | 6,800 |

## How these numbers were computed

- Offered load: 5,000 req/s split across 2 flow(s) by share (browse 95%, book 5%).
- Arrival per component = sum over flows of system_rps * flow.share * visit_prob along its path (open Jackson network).
- Utilisation rho = arrival / capacity, where capacity = per_instance_rps * instances.
- Bottleneck = highest rho -> Booking app tier at rho=0.62 (5,000 / 8,000 rps).
- Max sustainable load = system_rps * (ceiling / rho_max): safe@85% ~ 6,800 req/s, theoretical@100% ~ 8,000 req/s.
- Latency = sum of M/M/1 sojourn (service / (1 - rho)) * visit_prob along the dominant flow ('browse', 95% share) -> mean 31 ms.
- Percentiles via an exponential-tail approximation: p50/p95/p99 = mean x 0.69/3.00/4.61 (over-states the tail; treat as a directional upper bound).
- Monthly cost = compute $895.00 = $895.00 (integer cents; usage rates GROUNDED (cited)).

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities & prices have MIXED provenance — each is GROUNDED (matches a cited benchmark band), RECONCILE (your value kept despite falling outside the cited band), or ASSUMPTION (uncited), as marked in the Grounding & reconciliation section. None are calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost = per-instance compute × the chosen pricing-model discount + declared usage (egress/storage/requests) + AI/LLM tokens (input/output) at GROUNDED (cited) rates (ADR-009 Tiers 1–2). Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. AI token rates span a wide model-class band (real prices vary ~100× by model). These per-unit rates are GROUNDED to cited benchmarks (see *Cost rate evidence*). Volumes are 0 unless a component declares them. Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope. NOTE: that 'rates' provenance is for the per-unit usage/AI/discount rates only — the per-component COMPUTE prices that drive most of this figure carry their own provenance (GROUNDED / RECONCILE / ASSUMPTION), shown per component in the Grounding & reconciliation section; some may be RECONCILE (your value kept despite the cited band).
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.
- Headline latency (mean/p50/p95/p99) is for the DOMINANT flow — 'browse' (95% of traffic). Each flow's own latency is in the Per-flow latency table; a minority flow on a different (often worse) path can differ sharply.
- Some inputs above are GROUNDED to cited benchmarks matched by component **kind** (not your exact instance type / region / workload), so treat them as directional evidence, not stack-calibrated truth. RECONCILE rows fall outside the cited band and kept **your** value — a human should check them. These component-input citations are AI-matched and pass the curation gate; independent citation review remains the standing bar before treating them as calibrated (the per-unit cost **rates** were separately ratified — see *Cost rate evidence*).

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| workload | 5,000 req/s, 95% browse / 5% book (steady state) | med | ASSUMPTION |
| db | Single inventory DB sized ~3k writes/s; seat decrements are the contended path | low | ASSUMPTION |
| queue | Booking writes serialized through a queue to prevent overselling | med | ASSUMPTION |
