# Keystone — Engine Scoring Plan (L0 accuracy validation)

**Doc:** 11 · **Status:** Draft v0.1 · **Date:** 2026-06-17 · **Owner:** Keystone A (Bifola)
**Implements:** board Task #5 ("score engine vs in-scope SysSimulator blueprints — cost band + bottleneck").
**Relates to:** `docs/03` §3 (accuracy ladder) & §4 (eval harness MUST), `docs/02` §4 (engine), `prototype/keystone/benchmarks/`.

---

## 1. Why

Doc 03 makes correctness the differentiator and an **eval harness a MUST before external traffic**. This plan defines *how* the deterministic engine's accuracy is measured against the SysSimulator ground-truth corpus, and — honestly — *what that measurement can and cannot say at L0*.

## 2. What the ground truth actually is

`syssimulator_blueprints.py` is **metadata**: per blueprint `(component_count, monthly_cost_band, category, v1_scope)`. It contains **no runnable model, no ground-truth bottleneck, and no breakpoint.** Therefore:

- The engine can only be scored on a blueprint that has a **hand-built `SystemModel`** (`benchmarks/reference_models.py`). Building the rest of the 33 in-scope models is a tracked **GAP** (and is partly what the ingestion layer will eventually automate).
- The only hard ground-truth signals are **cost band** and **component count**.

## 3. What is scored (and the honest caveat on each)

Per Doc 03 §3, L0 is *"right order of magnitude; bottleneck identification reliable; absolute latency/cost approximate."* So the scorecard reports, per reference model:

| Metric | How | Honest caveat |
|---|---|---|
| **Cost band** | engine compute-cost vs `[low, high]`: `in-band` / `near` (≤3× outside) / `oom` (≤10×) / `off` (>10×) | **Scale-dependent** — the band's reference scale is undocumented; a model run heavier than the band assumes reads "over" with a correct engine. Cost is **compute-only** (no egress/managed pricing) → should land at/below an all-in band. A miss is usually **model calibration, not engine error.** |
| **Bottleneck** | engine names a real, saturatable component | **No ground-truth bottleneck** in the corpus → plausibility check, not scored-vs-truth. |
| **Breakpoint** | max sustainable load is **invariant** to current offered load (re-run at 2×) | A correctness property of the linear open network, not a vs-truth score. |
| **Determinism** | identical result on a re-run | Engine MUST be reproducible (seeded). |
| **Component count** | model vs documented | **Informational** — reference models capture the simulated **hot path**, a subset of the full architecture. |

**The engine's math is exact given a model** (the 7 engine unit tests pin it). This harness scores the **(reference-model + engine) pipeline**; capacities/costs are seed `ASSUMPTION`s, so calibration error belongs to the model, not the engine.

## 4. L0 acceptance (what "good enough for L0" means)

- **Bottleneck identification: reliable** — every in-scope reference model names a plausible bottleneck. *(Currently 5/5.)*
- **Breakpoint: stable + deterministic** — invariant to offered load; reproducible. *(5/5.)*
- **Cost: order-of-magnitude** — within an order of magnitude of the band; in-band when the reference model is built at the band's scale. *(4/5 in-band; URL Shortener reads 7× over because its seed model is a 12-instance high-traffic deployment vs a small-deployment band — a calibration note, not an engine error.)*

L0 does **not** claim exact cost/latency. The scorecard ships a permanent "where this is wrong" section.

## 5. The L0 → L1 path

1. **Build the reference corpus** — a `SystemModel` per in-scope blueprint at a documented reference load (the current GAP: 5/33).
2. **Field-calibrate capacities** to published, version-pinned component benchmarks → per-component **error envelopes** (the L1 gate, Doc 03 §3). This needs the Knowledge Base (unbuilt).
3. **Regression-test** the scorecard so accuracy cannot silently regress (this PR wires `score_all()` + tests).
4. **Publish** per-component error envelopes once L1 data exists — never before.

## 6. Run it

```bash
cd prototype
python3 run_scoring.py                       # -> outputs/engine_scorecard.md
python3 -m unittest discover -s tests -v     # includes the scoring regression tests
```
