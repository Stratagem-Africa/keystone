# Keystone Engine Scorecard — vs SysSimulator ground truth

> Accuracy level **L0 (Directional)**. This scores the **(reference-model + engine)** pipeline against documented component counts + monthly cost bands. The engine's math is exact given a model (see engine unit tests); a cost miss is usually **model calibration**, not engine error. Capacities/costs are SEED `ASSUMPTION`s (Doc 03) — not yet field-calibrated.

## Coverage
- **Reference models scored: 6 / 34 in-scope blueprints** (28 still need a model built — a tracked GAP).

## Summary
- **Cost band:** 5/6 in-band · 6/6 within an order of magnitude.
- **Bottleneck identified (plausibility):** 6/6.
- **Breakpoint stable (load-invariant):** 6/6.
- **Deterministic:** 6/6.

## Per-model

| Blueprint | Cat | @rps | Cost (engine) | Band | Verdict | Bottleneck (util) | Safe bp (rps) | Stable | Det | Comp m/t |
|---|---|--:|--:|--|--|--|--:|:--:|:--:|:--:|
| Ticket Booking System | event_driven | 5,000 | $895 | $300–$1,500 | in-band | Booking app tier (62%) | 6,800 | ✓ | ✓ | 8/8 |
| Rate Limiter | infrastructure | 5,000 | $120 | $30–$200 | in-band | Edge gateway (33%) | 12,750 | ✓ | ✓ | 2/6 |
| Key-Value Store | infrastructure | 7,000 | $465 | $100–$500 | in-band | KV API tier (78%) | 7,650 | ✓ | ✓ | 4/7 |
| Paste Bin | web_app | 1,000 | $95 | $15–$100 | in-band | App tier (67%) | 1,275 | ✓ | ✓ | 4/5 |
| Unique ID Generator | infrastructure | 20,000 | $95 | $50–$250 | in-band | ID workers (Snowflake) (67%) | 25,500 | ✓ | ✓ | 2/5 |
| URL Shortener | web_app | 10,000 | $1,045 | $20–$150 | oom 7.0× | App tier (t4g.medium x12) (69%) | 12,240 | ✓ | ✓ | 4/5 |

## Where this is wrong (read before trusting a score)

- **Cost bands are scale-dependent and their reference scale is undocumented.** A model run at a heavier load than the band assumes will read 'over' even with a correct engine (e.g. a 12-instance high-traffic deployment vs a small-deployment band). This is calibration, not engine error.
- **Cost is compute/instance-only** — no egress/data-transfer or managed-service pricing — so it should land at or BELOW an all-in band; landing far above signals an over-provisioned reference model.
- **No ground-truth bottleneck/breakpoint in the corpus** — those columns are plausibility/sanity checks, not scored-vs-truth.
- **Component count is the simulated hot path**, a subset of the full architecture's documented count; it is informational, not a pass/fail.
- **Most in-scope blueprints have no reference model yet** — building them (and field-calibrating capacities to benchmarks) is the L0→L1 path (Doc 03 §3).
