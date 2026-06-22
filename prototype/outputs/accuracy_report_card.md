# Keystone — Accuracy Report Card

> **Accuracy level: L0 (Directional).** This card reports only what can be measured against ground truth today, with an explicit *what this cannot say* section. It publishes no single headline accuracy number (Doc 03: no bare numbers, never overclaim).

## Simulation eval — engine vs the SysSimulator ground-truth corpus

| Dimension | Result | What the ground truth is |
|---|--:|---|
| Cost within documented band | 33/34 | the corpus's published monthly cost band |
| Bottleneck is a real, saturatable component | 34/34 | plausibility (no ground-truth bottleneck in corpus) |
| Breakpoint stable (load-invariant) | 34/34 | a correctness property of the open-network model |
| Deterministic (identical on re-run) | 34/34 | engine MUST be reproducible |

## Reconciliation eval — planted-conflict corpora (model level)

| Dimension | Result |
|---|--:|
| Planted conflicts surfaced (recall) | 4/4 |
| No invented hard conflict (false-positive-free) | 4/4 |
| Halts exactly when it must (no missed/spurious halt) | 4/4 |

## Where this scorecard CANNOT say more (read before trusting it)

- Latency & throughput have **no ground truth** in the corpus, so there is **no per-component error envelope** on them yet — only cost band + component count are checkable at L0. A real error envelope arrives with the grounded benchmark corpus (L1) and field calibration (L2).
- Cost band is **scale-dependent**: a reference model built heavier than the band's assumed scale reads 'over' even with a correct engine — a model-calibration note, not an engine error.
- The **council's reasoning quality and confidence calibration are NOT evaluated here** — that needs the real LLM (stub-default today) and a graded set of expert-reviewed designs; it is a gated next step, never faked.
- Reconciliation recall is measured on **planted, model-level** conflicts — it does **not** measure conflict extraction from free prose (that is the LLM ingestion step, evaluated separately once activated).
- Every number here is produced by the deterministic engine / reconciler, never by a language model (prime directive).
