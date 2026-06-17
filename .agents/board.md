# Task board (owned by Keystone A)

Single source of priority. A maintains; everyone reads. Status flow:
`PROPOSED` → `RATIFIED` → `IN-PROGRESS` → `IN-REVIEW` → `DONE`.
Team + governance: see `docs/07-Team-and-Roadmap.md`. **Every task merges to
`main` only via PR that Bifola approves.**

## Now (Phase 1)

| # | Task | Owner | Status | Brief / ADR |
|---|---|---|---|---|
| 3 | Stand up the delivery layer: FastAPI over engine+council → Next.js/Vercel → Fly+Supabase (dev) | Jem | PROPOSED | _A to write ADR-003 (hosting topology)_ |
| 5 | Score engine vs in-scope SysSimulator blueprints (cost band + bottleneck) | A/Tunji | **IN-REVIEW** | **docs/11** (plan) + `benchmarks/scoring.py` + `reference_models.py` + `run_scoring.py`; scorecard: 4/5 cost in-band, 5/5 bottleneck+stable+det; 5/34 modeled (GAP). PR pending |
| 6 | Ticket Booking blueprint — benchmark case #2 (flash-sale spike what-if) | Tunji | PROPOSED | — |

## Next
- Reconciliation service (merge partial models; conflict/gap report). — B
- Canonical model store (Postgres, versioned). — A design / Jem build
- Knowledge base / RAG (pgvector grounding). — Phase 2

## Done
- Phase 0: deterministic engine + loop on URL Shortener; 7 tests green; 56-blueprint corpus.
- Council (build): real ClaudeCouncil behind the interface; prime-directive guard + high-stakes
  gate; 25 tests green; stub-mode loop unchanged.
- Council (review): adversarial Review→Verify (8 dimensions, 46 agents, all findings reproduced
  in code). Outcome → **ADR-001** (2026-06-17). Architecture ratified; 3 CRITICAL trust-core
  bugs found (C1 high-stakes gate droppable via "review" substring; C2 metric-family guard
  bypass; C3 percentage leak) + H1 dissent char-explosion + H2 ReDoS — all invisible to the 25
  green tests.
- **Council fixes (Task #1/#1b) — DONE, merged in #29** (2026-06-17). Keystone-owned high-stakes
  gate (undroppable/unforgeable) + Hybrid prime-directive guard (bounded non-backtrackable int +
  noun-anchored backstop) + `_as_list` + honest banner. THREE adversarial re-verify rounds (each
  caught real defects: re-introduced ReDoS, leading-digit-eat, comma-branch ReDoS, a carve-out
  latency leak — all fixed). Independent pre-merge review (author recused) → APPROVE; flaky ReDoS
  test de-flaked before merge. 42 tests green. Real council **stays `stub`-gated**; activation +
  the documented bare-number residuals await the structured-output v2 lever + Bifola's trigger.
- **ADR-002 — ingestion layer** (2026-06-17): design + M1 injection-envelope + harm-floor +
  input-vs-derived boundary. Merged in #30.
- **Ingestion layer (Task #2) — DONE, merged in #31** (2026-06-17). `ingestion.py` behind the
  `Ingestor` seam (stub-default/$0) + shared `llm.py` transport (council refactored onto it,
  guard/gate byte-for-byte intact). Injection envelope + harm-floor secret-scan + provenance
  tagging + prime-directive-by-schema + fail-closed validation. TWO adversarial review rounds
  (Review→Verify + merge-gate) found 3 criticals (secret-class gaps, markdown/free-text injection,
  NaN/inf fail-open) + more harm-floor gaps — all fixed + locked. 74 tests green. `run_from_note.py`
  runs the full intent→ingest→council→simulate→report loop ($0/stub). Real ingestion stays
  stub-gated. **The Phase-1 loop is now complete end-to-end (all LLM layers stubbed-by-default).**
- **CI (Task #4) — DONE**: GitHub Actions runs the test suite + the automated reviewer on every PR
  (the `tests (engine + council)` + `review` checks, live since #27).
