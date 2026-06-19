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
| 3 | Delivery layer: FastAPI over engine+council/ingestion → Next.js/Cloudflare → Fly+Supabase (dev) | Jem | **IN-PROGRESS** | ADR-003 ratified; GH issues `#10–#24`. **#10 scaffold merged (#36)** — auth deferred to #20, CORS hardening tied to it. Jem on #11–#14 next. |

## Next
- Reconciliation **prose-level (semantic) conflicts** — the v2 LLM lever (ADR-004); v1 (merged, #39) is deterministic over typed models.
- Canonical model store (Postgres, versioned; GH #21) — A designs spec / Jem migration; carries the tenant-isolation MUST.
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
- **Reconciliation (F2, Task #8) — DONE, merged in #39** (closes GH issue **#8**). `reconciliation.py`
  (deterministic merge over typed models) + `ingest_corpus` + `run_reconciliation.py` + 12 tests.
  Halts on hard conflicts (never designs on a contradiction), never auto-resolves (soft conflicts kept
  side-by-side), fail-closed (empty corpus / invalid merge → `halted`, no model). Emits a model + a
  Reconciliation Report, never an engine number. Prose-level/semantic conflicts = the v2 LLM lever (ADR-004).
- **CI — MANUAL + LOCAL (Task #4 superseded, #40)**: GitHub Actions is **dormant** (account billing), so
  the merge gate is now `scripts/check.sh` run by the reviewer (`scripts/review-pr.sh <N>` to fetch+diff+check
  a PR). Workflows kept as `workflow_dispatch` stubs to re-enable instantly if Actions returns. Runbook in
  CONTRIBUTING.md. *(The earlier "Actions runs on every PR since #27" no longer holds.)*
- **Engine scoring (Task #5) — DONE, merged in #33** (2026-06-17, closes GH issue **#26**).
  `docs/11` plan + `benchmarks/scoring.py` + `reference_models.py` + `run_scoring.py`. Scorecard
  (honest by construction): bottleneck + stable-breakpoint + deterministic across all models; cost
  within an order of magnitude of band. Coverage grown **6 → 14/34 in-scope modeled** (#42 — +8
  across web_app/real_time/event_driven/ai_agents; 13/14 in-band); rest = L0→L1 GAP.
- **Ticket Booking case #2 (Task #6) — DONE, merged in #34** (2026-06-17, closes GH issue **#25**).
  `blueprints/ticket_booking.py` + `run_ticket_booking.py` flash-sale what-if (F6): an 8× booking
  spike shifts the bottleneck app→inventory-DB (667% util) and collapses the breakpoint. In-band; 6 tests.
- **Phase-1 documented list (1–4) complete.** All LLM layers stub-default; real activation = manual
  Bifola trigger. **Open in GitHub Issues:** jem delivery `#10–#24`; reconciliation **#8** + file
  intake **#6** + ingestion-tests **#9** (partial); model-store **#21**.
