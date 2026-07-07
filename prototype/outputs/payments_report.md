# Keystone Stress-Test Report — Payments / Checkout

> Accuracy level **L0 (Directional)**. Decision support, **not** certification. Numbers come from the deterministic engine; the council reasons about design and is constrained and scrubbed to keep figures out of its output (best-effort, not a guarantee). Read *Where this is wrong* before trusting a number.

**Offered load:** 80 req/s — 80% checkout / 20% status (steady state)
**Overall confidence:** medium (directional; within the model's reliable band)
**Reproduce:** engine v0.0.1 · model 'Payments / Checkout' · deterministic (identical inputs → identical output)

> ⚠️ **HIGH-STAKES DOMAIN — mandatory expert review.** This design touches a high-stakes domain. It **REQUIRES expert / legal / security review before any production use.** Keystone does **not** certify safety or production-readiness.

## Verdict

- **Bottleneck:** Payment gateway (Stripe) (utilisation 64%)
- **Max sustainable load:** ~106 req/s [90–212] at the 85% safe ceiling · ~125 req/s theoretical
- **Latency (dominant path):** p50 ~274 ms [83–711] · p95 ~1184 ms [357–3073] · p99 ~1820 ms [549–4725] (mean 395 ms)
- **Single points of failure:** API gateway / load balancer, Payments ledger (ACID, idempotent writes), Idempotency / order cache
- **Estimated monthly cost:** ~$428.00/month [$418–$442]
- _`[low–high]` = confidence range from cited input evidence (details + 'measured on' below) — input-uncertainty only, **not** a validated-accuracy guarantee._

## Headline metrics (model · confidence)

| Metric | Value | Range (cited inputs) | Model | Confidence |
|---|--:|--:|---|:--|
| bottleneck_utilization | 64% | 32% – 75% | max rho = arrival / capacity | medium |
| breakpoint_rps_safe | 106 req/s | 90 req/s – 212 req/s | system_rps * (85% ceiling / rho_max) | medium |
| breakpoint_rps_theoretical | 125 req/s | 106 req/s – 250 req/s | system_rps * (1.0 / rho_max) | medium |
| mean_latency_ms | 395 ms | 119 ms – 1,026 ms | sum of M/M/1 sojourn W=S/(1-rho) along the dominant flow | medium |
| p50_ms | 274 ms | 83 ms – 711 ms | exponential-tail: mean * ln(2) | medium |
| p95_ms | 1,184 ms | 357 ms – 3,073 ms | exponential-tail: mean * ln(20) | medium |
| p99_ms | 1,820 ms | 549 ms – 4,725 ms | exponential-tail: mean * ln(100) | medium |
| monthly_cost | $428.00/mo | $417.89/mo – $442.31/mo | compute (× pricing model) + usage (egress/storage/requests) + AI tokens at GROUNDED (cited) rates | medium |

_Range = the output span when each GROUNDED input is swept across its **cited** confidence band (assumed / reconciled inputs held fixed). It expresses input-evidence uncertainty only — **not** a validated-accuracy guarantee, and the true value can fall outside it. A **—** means no grounded input moves that number (no cited spread to show) — it is not zero uncertainty. Accuracy stays **L0 (Directional)** until field-calibrated._

## Per-flow latency

_Each flow's own latency (M/M/1 sojourn along its path; exponential-tail percentiles). The headline latency above is the **dominant** flow; a minority flow on a different path can differ sharply — confirm the path that matters to your users._

| Flow | Share | Mean | p50 | p95 | p99 |
|---|--:|--:|--:|--:|--:|
| checkout | 80% | 395 ms | 274 ms | 1,184 ms | 1,820 ms |
| status | 20% | 7 ms | 5 ms | 20 ms | 30 ms |

## Component load

| Component | Arrival (rps) | Capacity (rps) | Utilisation | Mean svc (ms) | Status |
|---|--:|--:|--:|--:|:--|
| Payment gateway (Stripe) | 64 | 100 | 64% | 388.9 | ok |
| Checkout service | 80 | 8,000 | 1% | 5.1 | ok |
| Payments ledger (ACID, idempotent writes) | 67 | 12,000 | 1% | 0.3 | ok |
| API gateway / load balancer | 80 | 50,000 | 0% | 1.0 | ok |
| Idempotency / order cache | 16 | 110,000 | 0% | 0.5 | ok |

## Grounding & reconciliation (input evidence)

Input numbers matched to **cited benchmark evidence**, by component **kind**, or your **declared setup** where a component is tagged (see *Measured on*). The engine still computed every result above; this annotates the *inputs* only. **GROUNDED** = your value sits inside the cited band; **RECONCILE** = it falls outside, and your value was **kept** (not overwritten). **Measured on** shows the hardware / workload the benchmark actually ran on — check it matches your setup before trusting the band.

| Component | Input | Your value | Grounded central | Cited band | Status | Measured on | Source |
|---|---|--:|--:|:--:|:--|:--|:--|
| API gateway / load balancer | base_latency_ms | 1.00 ms | 1.00 ms | 0.40–3.00 ms | GROUNDED ✓ | Managed/software L7 load balancer (AWS ALB / HAProx… | AWS — Application Load Balancer access logs (official docs) |
| API gateway / load balancer | per_instance_rps | 50,000 rps | 350,000 rps | 315,000–385,000 rps | RECONCILE ⚠ | 8 CPU cores, 4 GB RAM, Intel Xeon E5-2699 v4 @ 2.2 … | NGINX/F5 — Sizing Guide for Deploying NGINX Plus on Bare Metal Servers (official datasheet, published 11 Nov 2019; retrieved via Internet Archive OCR full-text) |
| Checkout service | base_latency_ms | 5.00 ms | 3.00 ms | 1.00–10.00 ms | GROUNDED ✓ | ~2-4 vCPU app-server instance running a typical web… | Fiber (Go framework) official docs — TechEmpower benchmark results (republishes official TechEmpower run data with hardware context) |
| Checkout service | per_instance_rps | 4,000 rps | 4,000 rps | 2,000–8,000 rps | GROUNDED ✓ | One app-server instance, ~2-4 vCPU (e.g. AWS c5.xla… | Sharkbench (go-gin web benchmark) |
| Payment gateway (Stripe) | base_latency_ms | 140.00 ms | 140.00 ms | 80.00–250.00 ms | GROUNDED ✓ | Stripe/Adyen-class payment-gateway external HTTPS A… | Probecast — Adyen API status / latency monitoring (independent third-party) |
| Payment gateway (Stripe) | per_instance_rps | 100 rps | 100 rps | 85–200 rps | GROUNDED ✓ | stripe · live_mode · per_account | Stripe Documentation — Rate limits (official vendor doc) |
| Payments ledger (ACID, idempotent writes) | base_latency_ms | 0.30 ms | 0.30 ms | 0.15–0.80 ms | GROUNDED ✓ | PostgreSQL/MySQL/MariaDB, sysbench warm-cache singl… | computingforgeeks (PostgreSQL vs MySQL vs MariaDB benchmark) |
| Payments ledger (ACID, idempotent writes) | monthly_cost_per_instance | $120.00/mo | $122.10/mo | $109.89–$134.31 | GROUNDED ✓ | Managed PostgreSQL — 8 GiB RAM / 4 vCPUs / 140 GiB … | https://www.digitalocean.com/pricing/managed-databases |
| Payments ledger (ACID, idempotent writes) | per_instance_rps | 12,000 rps | 8,133 rps | 4,800–29,000 rps | GROUNDED ✓ | AWS RDS db.m8gd.4xlarge (16 vCPU / 64 GB, NVMe-back… | ClickHouse Blog — PostgresBench: A Reproducible Benchmark for Postgres Services |
| Idempotency / order cache | base_latency_ms | 0.50 ms | 1.00 ms | 0.40–1.50 ms | GROUNDED ✓ | HPE ProLiant DL380 Gen10, one Intel Xeon Gold 6230 … | Redis official documentation — How fast is Redis? (redis-benchmark) |
| Idempotency / order cache | per_instance_rps | 110,000 rps | 110,000 rps | 70,000–180,000 rps | GROUNDED ✓ | Redis single node, GET/SET, NON-pipelined (pipeline… | Redis official documentation (How fast is Redis? / Benchmarks, readthedocs) |

**Reconcile — your value is outside the cited band (kept, not overwritten):**
- **API gateway / load balancer** · `per_instance_rps`: you have **50,000 rps**, the cited evidence says **350,000 rps** (band 315,000–385,000 rps). Check the context (hardware / region / workload) — the engine used **your** value, not the benchmark.

**Evidence (resolvable sources):**
- AWS — Application Load Balancer access logs (official docs) — https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-access-logs.html
- HAProxy Technologies — 'HAProxy Forwards Over 2 Million HTTP Requests per Second on a Single AWS Arm Instance' — https://www.haproxy.com/blog/haproxy-forwards-over-2-million-http-requests-per-second-on-a-single-aws-arm-instance
- Istio — 'Best Practices: Benchmarking Service Mesh Performance' (Envoy sidecar overhead) — https://istio.io/latest/blog/2019/performance-best-practices/
- NGINX/F5 — Sizing Guide for Deploying NGINX Plus on Bare Metal Servers (official datasheet, published 11 Nov 2019; retrieved via Internet Archive OCR full-text) — https://ia801500.us.archive.org/31/items/sizing-guide-for-deploying-nginx-plus-on-bare-metal-servers-2019-11-09/sizing-guide-for-deploying-nginx-plus-on-bare-metal-servers-2019-11-09_djvu.txt
- Internet Archive item landing page (provenance for the OCR full-text above) — https://archive.org/details/sizing-guide-for-deploying-nginx-plus-on-bare-metal-servers-2019-11-09
- NGINX/F5 — NGINX Plus Sizing Guide: How We Tested (methodology, corroborates test conditions) — https://www.f5.com/company/blog/nginx/nginx-plus-sizing-guide-how-we-tested
- Fiber (Go framework) official docs — TechEmpower benchmark results (republishes official TechEmpower run data with hardware context) — https://docs.gofiber.io/extra/benchmarks/
- GoFrame official docs — TechEmpower Round 23 Web Benchmarks evaluation (Go frameworks JSON test, P99) — https://goframe.org/en/articles/techempower-web-benchmarks-r23
- Pau Sanchez — 'Yet another nodejs benchmark' (independent benchmark, Express vs node:http, text handler) — https://www.pausanchez.com/en/articles/yet-another-nodejs-benchmark/
- Deno — 'Who has the best response time for Hello world: Node.js, Deno, or Bun?' (independent runtime benchmark) — https://medium.com/deno-the-complete-reference/who-has-the-best-response-time-for-hello-world-node-js-deno-or-bun-65bd1ae3bc64
- Sharkbench (go-gin web benchmark) — https://sharkbench.dev/web/go-gin
- nDmitry/web-benchmarks (GitHub) — https://github.com/nDmitry/web-benchmarks
- DEV.to — Under Pressure: Benchmarking Node.js on a Single-Core EC2 — https://dev.to/ocodista/under-pressure-benchmarking-nodejs-on-a-single-core-ec2-5ghe
- Probecast — Adyen API status / latency monitoring (independent third-party) — https://probecast.io/status/adyen-api
- The Stripe Latency Post-Mortem Every Engineer Should Read (Medium, secondary account of Stripe's March 2022 incident) — https://medium.com/@warstories/the-stripe-latency-post-mortem-every-engineer-should-read-before-launching-their-api-6514411772f8
- Stripe Documentation — Rate limits (official vendor doc) — https://docs.stripe.com/rate-limits
- Stripe Support — "rate_limit" error when creating bulk API requests (official Stripe support page, same-vendor corroboration) — https://support.stripe.com/questions/rate-limit-error-when-creating-bulk-api-requests
- computingforgeeks (PostgreSQL vs MySQL vs MariaDB benchmark) — https://computingforgeeks.com/database-benchmark-postgresql-mysql-mariadb/
- DoltHub Blog — Postgres vs MySQL Sysbench Latency — https://www.dolthub.com/blog/2024-07-16-mysql-postgres-sysbench-latency/
- faucetDB (MCP database benchmark) — https://faucetdb.ai/blog/mcp-database-benchmark/
- https://www.digitalocean.com/pricing/managed-databases — PostgreSQL plan table, 8 GiB row
- https://docs.digitalocean.com/products/databases/postgresql/details/pricing/ — PostgreSQL pricing overview
- ClickHouse Blog — PostgresBench: A Reproducible Benchmark for Postgres Services — https://clickhouse.com/blog/postgresbench
- Severalnines — Benchmarking Managed PostgreSQL Cloud Solutions: Part Two - Amazon RDS — https://severalnines.com/blog/benchmarking-managed-postgresql-cloud-solutions-part-two-amazon-rds/
- Redis official documentation — How fast is Redis? (redis-benchmark) — https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- Redis official documentation (How fast is Redis? / Benchmarks, readthedocs) — https://redis-doc-test.readthedocs.io/en/latest/topics/benchmarks/
- Redis official documentation (Benchmarks, current docs) — https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
- OneUptime — How to Benchmark Redis Performance with redis-benchmark — https://oneuptime.com/blog/post/2026-03-31-redis-benchmark-performance/view

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

> _Council running in DETERMINISTIC STUB mode — illustrative ADRs, not live reasoning. Activate the real council with any provider — a free-tier Gemini/Groq key, a Claude key, or a local Ollama (no key, $0)._

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

### Review gate — confidence: high
**Decision:** REQUIRES expert/legal/security review before any production use.

**Rationale:** Domain flagged high-stakes; Keystone does not certify safety.

**Kill criteria (revisit this decision if):**
- Shipped without independent expert sign-off

## What-if interrogation

| Scenario | Bottleneck | Util | Max safe load (rps) |
|---|---|--:|--:|
| Sale: 2× traffic (160 rps), 85% checkout | Payment gateway (Stripe) | 136% | 100 |
| Black-Friday: 4× traffic (320 rps), 90% checkout | Payment gateway (Stripe) | 288% | 94 |

## How these numbers were computed

- Offered load: 80 req/s split across 2 flow(s) by share (checkout 80%, status 20%).
- Arrival per component = sum over flows of system_rps * flow.share * visit_prob along its path (open Jackson network).
- Utilisation rho = arrival / capacity, where capacity = per_instance_rps * instances.
- Bottleneck = highest rho -> Payment gateway (Stripe) at rho=0.64 (64 / 100 rps).
- Max sustainable load = system_rps * (ceiling / rho_max): safe@85% ~ 106 req/s, theoretical@100% ~ 125 req/s.
- Latency = sum of M/M/1 sojourn (service / (1 - rho)) * visit_prob along the dominant flow ('checkout', 80% share) -> mean 395 ms.
- Percentiles via an exponential-tail approximation: p50/p95/p99 = mean x 0.69/3.00/4.61 (over-states the tail; treat as a directional upper bound).
- Monthly cost = compute $428.00 = $428.00 (integer cents; usage rates GROUNDED (cited)).

## Where this is wrong (read before trusting a number)

- Analytical queueing approximation (M/M/1 per component), not a discrete-event simulation. Async/streaming/multi-region topologies are out of v1 scope.
- Component capacities & prices have MIXED provenance — each is GROUNDED (matches a cited benchmark band), RECONCILE (your value kept despite falling outside the cited band), or ASSUMPTION (uncited), as marked in the Grounding & reconciliation section. None are calibrated to your stack. Accuracy is L0 (Directional) until field-calibrated (Doc 03).
- Percentiles use an exponential-tail approximation and tend to OVER-state the tail; treat p95/p99 as upper-bound directional figures.
- Cost = per-instance compute × the chosen pricing-model discount + declared usage (egress/storage/requests) + AI/LLM tokens (input/output) at GROUNDED (cited) rates (ADR-009 Tiers 1–2). Compute defaults to on_demand list price; reserved/spot apply published-range discount ratios. AI token rates span a wide model-class band (real prices vary ~100× by model). These per-unit rates are GROUNDED to cited benchmarks (see *Cost rate evidence*). Volumes are 0 unless a component declares them. Third-party SaaS (payments/auth/etc.) and on-prem are still out of scope. NOTE: that 'rates' provenance is for the per-unit usage/AI/discount rates only — the per-component COMPUTE prices that drive most of this figure carry their own provenance (GROUNDED / RECONCILE / ASSUMPTION), shown per component in the Grounding & reconciliation section; some may be RECONCILE (your value kept despite the cited band).
- Bottleneck identification and the relative ordering of components are far more reliable than absolute latency/cost numbers.
- Headline latency (mean/p50/p95/p99) is for the DOMINANT flow — 'checkout' (80% of traffic). Each flow's own latency is in the Per-flow latency table; a minority flow on a different (often worse) path can differ sharply.
- Some inputs above are GROUNDED to cited benchmarks matched by component **kind**, or to your **declared setup** where a component is tagged (e.g. a specific payment vendor — see the *Measured on* column), so treat them as directional evidence, not stack-calibrated truth. RECONCILE rows fall outside the cited band and kept **your** value — a human should check them. These component-input citations are AI-matched and pass the curation gate; independent citation review remains the standing bar before treating them as calibrated (the per-unit cost **rates** were separately ratified — see *Cost rate evidence*).

## Assumptions (each editable)

| Subject | Statement | Confidence | Provenance |
|---|---|:--:|:--:|
| workload | 80 req/s, 80% checkout / 20% status (steady state) | med | ASSUMPTION |
| gateway | Third-party payment gateway is the binding constraint: a server-enforced ~100 req/s RATE LIMIT (HARD 429 ceiling, NOT a graceful slowdown) and a ~140 ms external round-trip. Confirm YOUR vendor/tier — limits vary widely. | med | ASSUMPTION |
| db | Single ACID ledger; writes are idempotent (a charge is recorded exactly once even on retry). Sized well above the gateway-capped write rate. | low | ASSUMPTION |
| compliance | Money movement: PCI-DSS scope, fraud, reconciliation and idempotency are REQUIRED and out of this model's scope — expert review is mandatory. | high | ASSUMPTION |
