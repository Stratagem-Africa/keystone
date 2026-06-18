# Task board (owned by Keystone A)

Single source of priority. A maintains; everyone reads. Status flow:
`PROPOSED` → `RATIFIED` → `IN-PROGRESS` → `IN-REVIEW` → `DONE`.
Team + governance: see `docs/07-Team-and-Roadmap.md`. **Every task merges to
`main` only via PR that Bifola approves.**

**Trackers.** Granular sprint work lives in **GitHub Issues** (jem: API/frontend/infra
`#10–#24`; shared evals `#9/#25/#26`; bifola: ingestion/ADRs `#4–#8`). This board is the
priority rollup; the issue each Done item closes is noted inline.

## Now (Phase 1)

| # | Task | Owner | Status | Brief / ADR |
|---|---|---|---|---|
| 3 | Delivery layer: FastAPI over engine+council/ingestion → Next.js/Cloudflare → Fly+Supabase (dev) | Jem | **IN-PROGRESS** | ADR-003 ratified; broken into GH issues `#10–#24`. Jem on **#10** (FastAPI scaffold) — local branch, not pushed yet. Core is import-ready on `main` (engine/council/ingestion). |

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
- Council fixes close GH issue **#4** (ADR-001); ingestion closes **#7**; see below for #5/#25/#26.
- **ADR-002 — ingestion layer** (2026-06-17): design + M1 injection-envelope + harm-floor +
  input-vs-derived boundary. Merged in #30 (closes GH issue **#5**).
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
- **Engine scoring (Task #5) — DONE, merged in #33** (2026-06-17, closes GH issue **#26**).
  `docs/11` plan + `benchmarks/scoring.py` + `reference_models.py` + `run_scoring.py`. Scorecard
  (honest by construction): bottleneck + stable-breakpoint + deterministic across all models; cost
  within an order of magnitude of band; coverage now **6/34 in-scope modeled** (rest = L0→L1 GAP).
- **Ticket Booking case #2 (Task #6) — DONE, merged in #34** (2026-06-17, closes GH issue **#25**).
  `blueprints/ticket_booking.py` + `run_ticket_booking.py` flash-sale what-if (F6): an 8× booking
  spike shifts the bottleneck app→inventory-DB (667% util) and collapses the breakpoint. In-band; 6 tests.
- **Phase-1 documented list (1–4) complete.** All LLM layers stub-default; real activation = manual
  Bifola trigger. **Open in GitHub Issues:** jem delivery `#10–#24`; reconciliation **#8** + file
  intake **#6** + ingestion-tests **#9** (partial); model-store **#21**.
