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

## Input grounding — input numbers backed by cited evidence (ADR-006, the L0→L1 lever)

Across the 34 reference models, each component INPUT (capacity / service-time / per-instance cost) is matched to the curated benchmark corpus. This measures input **provenance + agreement**, NOT engine-output accuracy: a *grounded in-band* input is cited evidence the modeler's value sits within; a *reconcile* input diverges from the evidence and is flagged for a human (never auto-changed). It does not certify the derived result.

| Dimension | Result |
|---|--:|
| Input numbers with cited evidence (grounded **or** reconcile) | 122/609 (20%) |
| …modeler value AGREES with the cited band (GROUNDED, in-band) | 50/609 (8%) |
| …modeler value DIVERGES from it (RECONCILE — flagged, kept) | 72/609 (12%) |
| Still ASSUMPTION (no cited datapoint matches yet) | 487/609 (80%) |

> Honest read: most inputs are still ASSUMPTION — this is **early L1**, not calibrated truth. Coverage grows as the corpus does; a RECONCILE is a *signal to check an input*, not an engine error.

## Where this scorecard CANNOT say more (read before trusting it)

- Input grounding (above) measures **input provenance + agreement**, NOT an engine-OUTPUT error envelope — there is still **no per-component error envelope** on the engine's derived latency/cost. A grounded input is cited evidence the modeler's value sits within; it does not tell you how wrong the derived result is. Output error envelopes need field-calibrated ground truth (L2), and most inputs are still ASSUMPTION — this is early L1.
- Cost band is **scale-dependent**: a reference model built heavier than the band's assumed scale reads 'over' even with a correct engine — a model-calibration note, not an engine error.
- The **council's reasoning quality and confidence calibration are NOT evaluated here** — that needs the real LLM (stub-default today) and a graded set of expert-reviewed designs; it is a gated next step, never faked.
- Reconciliation recall is measured on **planted, model-level** conflicts — it does **not** measure conflict extraction from free prose (that is the LLM ingestion step, evaluated separately once activated).
- Every number here is produced by the deterministic engine / reconciler, never by a language model (prime directive).
