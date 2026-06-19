# Keystone Engine Scorecard — vs SysSimulator ground truth

> Accuracy level **L0 (Directional)**. This scores the **(reference-model + engine)** pipeline against documented component counts + monthly cost bands. The engine's math is exact given a model (see engine unit tests); a cost miss is usually **model calibration**, not engine error. Capacities/costs are SEED `ASSUMPTION`s (Doc 03) — not yet field-calibrated.

## Coverage
- **Reference models scored: 34 / 34 in-scope blueprints — full in-scope coverage.** The remaining work is field-calibration, not coverage (see 'where this is wrong'); out-of-scope blueprints await the v2 engine.

## Summary
- **Cost band:** 33/34 in-band · 34/34 within an order of magnitude.
- **Bottleneck identified (plausibility):** 34/34.
- **Breakpoint stable (load-invariant):** 34/34.
- **Deterministic:** 34/34.

## Per-model

| Blueprint | Cat | @rps | Cost (engine) | Band | Verdict | Bottleneck (util) | Safe bp (rps) | Stable | Det | Comp m/t |
|---|---|--:|--:|--|--|--|--:|:--:|:--:|:--:|
| Ticket Booking System | event_driven | 5,000 | $895 | $300–$1,500 | in-band | Booking app tier (62%) | 6,800 | ✓ | ✓ | 8/8 |
| Rate Limiter | infrastructure | 5,000 | $120 | $30–$200 | in-band | Edge gateway (33%) | 12,750 | ✓ | ✓ | 2/6 |
| Key-Value Store | infrastructure | 7,000 | $465 | $100–$500 | in-band | KV API tier (78%) | 7,650 | ✓ | ✓ | 4/7 |
| Paste Bin | web_app | 1,000 | $95 | $15–$100 | in-band | App tier (67%) | 1,275 | ✓ | ✓ | 4/5 |
| Unique ID Generator | infrastructure | 20,000 | $95 | $50–$250 | in-band | ID workers (Snowflake) (67%) | 25,500 | ✓ | ✓ | 2/5 |
| Serverless REST API | web_app | 2,000 | $155 | $10–$200 | in-band | Function tier (Lambda) (67%) | 2,550 | ✓ | ✓ | 4/5 |
| Blog Platform | web_app | 3,000 | $270 | $50–$300 | in-band | Render tier (68%) | 3,778 | ✓ | ✓ | 6/6 |
| Hotel Reservation System | web_app | 3,000 | $470 | $100–$500 | in-band | Reservation app (67%) | 3,825 | ✓ | ✓ | 6/6 |
| Parking Lot System | web_app | 500 | $105 | $30–$150 | in-band | App tier (50%) | 850 | ✓ | ✓ | 4/6 |
| Leaderboard System | real_time | 8,000 | $300 | $50–$300 | in-band | Leaderboard API (67%) | 10,200 | ✓ | ✓ | 4/6 |
| Typeahead / Autocomplete | real_time | 12,000 | $445 | $100–$600 | in-band | Suggest API (80%) | 12,750 | ✓ | ✓ | 4/6 |
| Task Queue | event_driven | 1,000 | $345 | $80–$400 | in-band | Worker pool (83%) | 1,020 | ✓ | ✓ | 5/7 |
| MCP Starter | ai_agents | 400 | $180 | $50–$250 | in-band | MCP server (67%) | 510 | ✓ | ✓ | 5/6 |
| E-Commerce Platform | web_app | 4,000 | $390 | $200–$800 | in-band | Storefront app (67%) | 5,100 | ✓ | ✓ | 6/6 |
| File Hosting Service | web_app | 3,000 | $250 | $50–$500 | in-band | App tier (75%) | 3,400 | ✓ | ✓ | 6/6 |
| Image Hosting Service | web_app | 4,000 | $200 | $30–$300 | in-band | App tier (67%) | 5,100 | ✓ | ✓ | 7/7 |
| Yelp / Proximity Service | web_app | 5,000 | $660 | $200–$1,200 | in-band | Geo index service (83%) | 5,100 | ✓ | ✓ | 7/7 |
| Social Media Feed | event_driven | 10,000 | $820 | $500–$2,000 | in-band | Feed API (83%) | 10,200 | ✓ | ✓ | 8/8 |
| CI/CD Pipeline | event_driven | 80 | $280 | $50–$300 | in-band | Build runners (80%) | 85 | ✓ | ✓ | 5/5 |
| Notification System | event_driven | 2,000 | $345 | $100–$800 | in-band | Dispatch workers (67%) | 2,550 | ✓ | ✓ | 8/8 |
| Microservices Gateway | microservices | 16,000 | $1,035 | $800–$3,000 | in-band | Service C (80%) | 17,000 | ✓ | ✓ | 10/10 |
| Payment System | microservices | 5,000 | $1,140 | $600–$2,000 | in-band | Fraud scoring (88%) | 4,857 | ✓ | ✓ | 8/8 |
| Food Delivery System | microservices | 7,000 | $790 | $400–$2,000 | in-band | Geo matching (79%) | 7,556 | ✓ | ✓ | 8/8 |
| Digital Wallet | microservices | 7,000 | $1,100 | $500–$3,000 | in-band | Fraud scoring (88%) | 6,800 | ✓ | ✓ | 8/8 |
| Search Engine | data_pipeline | 6,000 | $810 | $300–$1,500 | in-band | Index shards (75%) | 6,800 | ✓ | ✓ | 7/7 |
| Web Crawler | data_pipeline | 800 | $670 | $200–$1,500 | in-band | Fetch workers (80%) | 850 | ✓ | ✓ | 7/7 |
| Metrics & Monitoring | data_pipeline | 12,000 | $495 | $150–$800 | in-band | TSDB writers (72%) | 14,167 | ✓ | ✓ | 7/7 |
| Distributed Cache | infrastructure | 60,000 | $650 | $200–$1,000 | in-band | Cache proxy/router (67%) | 76,500 | ✓ | ✓ | 5/7 |
| API Rate Limiting Gateway | infrastructure | 30,000 | $510 | $100–$600 | in-band | Auth/token validation (71%) | 35,789 | ✓ | ✓ | 8/8 |
| RAG + MCP Assistant | ai_agents | 600 | $300 | $150–$900 | in-band | RAG orchestrator (75%) | 680 | ✓ | ✓ | 6/6 |
| Multi-Agent Supervisor | ai_agents | 600 | $510 | $300–$1,800 | in-band | Agent workers (75%) | 680 | ✓ | ✓ | 7/7 |
| MCP Tool Gateway | ai_agents | 8,000 | $575 | $300–$2,200 | in-band | Tool router (72%) | 9,444 | ✓ | ✓ | 7/7 |
| Agent Observability Stack | ai_agents | 10,000 | $415 | $120–$700 | in-band | Span/trace writers (75%) | 11,333 | ✓ | ✓ | 6/6 |
| URL Shortener | web_app | 10,000 | $1,045 | $20–$150 | oom 7.0× | App tier (t4g.medium x12) (69%) | 12,240 | ✓ | ✓ | 4/5 |

## Where this is wrong (read before trusting a score)

- **Cost bands are scale-dependent and their reference scale is undocumented.** A model run at a heavier load than the band assumes will read 'over' even with a correct engine (e.g. a 12-instance high-traffic deployment vs a small-deployment band). This is calibration, not engine error.
- **Cost is compute/instance-only** — no egress/data-transfer or managed-service pricing — so it should land at or BELOW an all-in band; landing far above signals an over-provisioned reference model.
- **No ground-truth bottleneck/breakpoint in the corpus** — those columns are plausibility/sanity checks, not scored-vs-truth.
- **Component count is the simulated hot path**, a subset of the full architecture's documented count; it is informational, not a pass/fail.
- **Capacities/costs are SEED `ASSUMPTION`s, not field-calibrated** — even at full in-scope coverage, calibrating them to real benchmarks is the remaining L0→L1 **GAP** (Doc 03 §3); out-of-scope blueprints still await the v2 engine.
