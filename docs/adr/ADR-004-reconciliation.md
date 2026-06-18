# ADR-004 — Cross-document Reconciliation (F2)

**Status:** Accepted · **Ratified-by:** Bifola, 2026-06-18 (build assigned to A / issue #8)
**Date:** 2026-06-18 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/04` F2 (the differentiator), `docs/02` §4 (REC component), `docs/05` (ReconciliationReport), `docs/03` §2/§6 (prime directive, fail-closed); ADR-002 (ingestion — produces the partial models this merges)
**Implements:** GH issue **#8** (Ingestion: reconciliation → conflict/gap report). Unblocks the F2 build that B-status lists as "next, gated on ADR".

---

## Context

Ingestion (ADR-002) turns **one** source into **one** partial `SystemModel` + assumption ledger. Reconciliation is the step Doc 04 calls *"the differentiator most tools skip"*: merge the **N** partial models from a document corpus into **one** canonical model, and emit a **Reconciliation Report** of conflicts, gaps, and duplications. The hard rule (Doc 04 F2 `MUST`): **Keystone halts at unresolved hard conflicts and asks the user to choose — it never designs on a contradiction, and never auto-resolves one.** The eval that governs it (Doc 03 §4): surface **every** real conflict (recall) without **inventing** false ones (precision).

## The deterministic-vs-LLM decision (load-bearing)

Per the prime directive, reconciliation must not become a place where an LLM silently invents structure or numbers. So **v1 reconciliation is DETERMINISTIC**, operating on the **typed** partial models (not raw prose):

- **What's deterministic (v1, here):** structural merge + conflict/gap/duplication detection over `SystemModel` fields — component kinds/capacities/instances, flows, workload, domain flags, assumptions. This is precise, testable, and reproducible.
- **What's deferred to a v2 LLM lever:** semantic contradictions that live only in the *prose* ("offline-first" vs "real-time global consistency") and that ingestion already collapsed into the typed model. Detecting those needs the LLM to compare requirement text; v1 reconciles what the typed models actually disagree on. Documented GAP.

Reconciliation produces a **model + a report** — never an engine metric (the engine remains the only number producer).

## Decision

1. **Interface (mirrors the council/ingestion seams).**
   - `reconcile(results: list[IngestResult]) -> ReconciliationOutcome`
   - `ReconciliationOutcome(model: SystemModel | None, report: ReconciliationReport, halted: bool)` — `model` is the merged canonical model, or **`None` when `halted`** (a hard conflict blocks the merge).
   - `ReconciliationReport(conflicts: list[Conflict], gaps: list[Gap], duplications: list[Duplication])`; each record carries the two sides (refs + values) and a `severity`. Rendered into the Doc 05 report shape.

2. **Merge (only when not halted).** Union components by `id`; merge flows; reconcile the workload (e.g. take the max stated `system_rps` with the divergence recorded as an assumption, never silently averaged). Every merged value keeps its provenance; nothing becomes `GROUNDED` by merging.

3. **Conflict detection.**
   - **HARD** (→ halt, no merged model): same component `id` with a different `kind`; the same subject asserted with mutually-exclusive structural values; an out-of-scope kind. The report shows both sides; the user chooses; **we do not design on it.**
   - **SOFT** (merge proceeds, flagged): same `id` + same `kind` but divergent capacity/instances/latency, or divergent workload numbers. Kept side-by-side as an editable assumption — **never auto-resolved away.**

4. **Gaps (deterministic heuristics, additive).** Structural gaps the merged model is missing: no workload/`system_rps`, no flows, a flow step referencing an undefined component, no high-stakes flag where one source implied a high-stakes domain. Flagged for the user to confirm (Doc 04 F2 "Claude proposes; user confirms" is the v2 lever; v1 surfaces the deterministic gaps).

5. **Duplications.** Components across sources with the same `kind` and a similar/near-duplicate name but different `id` → flagged as a likely duplicate for the user to merge. Never auto-merged (could erase a real distinct component).

6. **Fail closed (Doc 03 §6).** Any hard conflict, an empty corpus, or a merged model that fails `validate_model` (reuse the ingestion validator) → return `halted=True` with the report, never a half-merged model to the engine.

7. **Honesty.** The report is the artifact; it shows conflicts side-by-side and never claims a resolution the user didn't make. No accuracy/derived numbers.

## Build plan (Brief → issue #8 owner)

- `prototype/keystone/reconciliation.py`: `Conflict`, `Gap`, `Duplication`, `ReconciliationReport`, `ReconciliationOutcome`, `reconcile(results)`, and `render_reconciliation_report()`. Reuse `ingestion.validate_model` for the fail-closed merge check.
- `tests/test_reconciliation.py` (offline): planted hard conflict (kind mismatch) → halts, no model; soft conflict (capacity divergence) → merges + flags, never auto-resolves; duplication detection; gap detection; clean two-source merge; fail-closed on empty/invalid.
- Optional demo: reconcile two stub-ingested notes (one with a planted contradiction) → report.
- Adversarial Review→Verify before merge (it's a trust-surface: "never design on a contradiction", "never auto-resolve", recall/precision of conflicts).

## Recorded dissent

- **Data engineer:** deterministic typed-model reconciliation misses prose-level contradictions. *Accepted:* those are the v2 LLM lever; v1 is precise on what the models actually disagree on, and honest about the gap.
- **YAGNI:** duplication/gap heuristics may over- or under-flag. *Accepted:* they only *flag* (never auto-act), so a false flag costs a user glance, not a wrong design — the safe direction.

## Confidence

**High** on the interface, the deterministic structural merge, and the halt-on-hard-conflict MUST. **Lower** on gap/duplication heuristic tuning (will need iteration against real corpora) and on prose-level conflicts (v2).

## Kill criteria (revisit if…)

- A hard conflict is ever auto-resolved or a contradictory model reaches the engine → prime-directive/F2 MUST breach; block.
- Conflict recall misses a planted contradiction in the eval, or precision invents false ones → re-tune before external use.
- Prose-level (semantic) contradictions become a launch requirement → pull the v2 LLM lever (and it must stay deterministic-checked).
- Multi-source ingestion (>1 doc) isn't wired yet → reconciliation has no inputs; sequence behind multi-source ingest.

## Consequences

Unblocks the F2 build (issue #8). Whoever owns #8 builds `reconciliation.py` behind this interface; A runs Review→Verify; merge keeps it offline/no-activation. Note the **input dependency**: reconciliation needs *multiple* partial models, so multi-source ingestion (a small extension of ADR-002's single-source `ingest`) is its prerequisite.
