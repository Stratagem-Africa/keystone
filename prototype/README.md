# Keystone — Phase 0 Prototype

A runnable, no-dependency proof of the core loop:

**intent → canonical model → consensus council → deterministic simulation → what-if → report**

Built against the **URL Shortener** (the most-documented system, so output can be sanity-checked).
Pure Python 3.10+ stdlib — no pip install, no API key needed to run the engine.

## Run it

```bash
cd prototype
python3 run_url_shortener.py            # end-to-end loop -> outputs/url_shortener_report.md
python3 -m unittest discover -s tests -v # 7 deterministic engine tests
python3 -m keystone.benchmarks.syssimulator_blueprints  # the benchmark corpus
```

## The one rule that governs everything

**The LLM reasons; the engine computes.** `simulation.py` is the *only* producer of
numbers — open queueing-network math (utilisation, bottleneck, breakpoint, latency
percentiles, cost). `council.py` reasons about design and never emits a metric. This
separation (Doc 03, Accuracy Charter) is what makes the tool trustworthy.

## Layout

| File | Role |
|---|---|
| `keystone/model.py` | Canonical system model (Doc 05) — the single source of truth |
| `keystone/simulation.py` | Deterministic analytical engine — produces every number |
| `keystone/council.py` | Consensus council interface + deterministic stub (swap in Claude) |
| `keystone/report.py` | Markdown report with the mandatory "where this is wrong" section |
| `keystone/blueprints/url_shortener.py` | The Phase-0 input, hand-built for validation |
| `keystone/benchmarks/` | All 56 SysSimulator blueprints as the ground-truth eval corpus |
| `run_url_shortener.py` | The end-to-end loop |
| `tests/` | 7 deterministic engine tests (all passing) |

## What's real vs stubbed

- **Real & running:** the canonical model, the deterministic simulation engine, the
  what-if mechanism, the report, the benchmark corpus, the tests.
- **Stubbed (clearly labelled):** the council currently returns canned ADRs. Real
  consensus reasoning plugs in behind the `Council` interface — single Claude model,
  multiple persona prompts, via the Agent SDK. This is the only piece that needs a key.

## Accuracy honesty

Output is **L0 (Directional)** per the Accuracy Charter: bottleneck identification and
component ordering are reliable; absolute latency/cost are approximate; component
capacities are SEED assumptions, not yet field-calibrated. Every report says so.

## Next

1. Replace the stub council with the real Claude consensus engine (independent design →
   blind peer review → chairman synthesis).
2. Build the LLM ingestion layer (concept note / docs → canonical model) so the model is
   derived, not hand-built.
3. Score the engine against the in-scope benchmark blueprints (cost band + bottleneck).
4. Add Ticket Booking as case #2 (the dramatic spike what-if).
