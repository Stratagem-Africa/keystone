# Task board (owned by Keystone A)

Single source of priority. A maintains; everyone reads. Status flow:
`PROPOSED` → `RATIFIED` → `IN-PROGRESS` → `IN-REVIEW` → `DONE`.
Team + governance: see `docs/07-Team-and-Roadmap.md`. **Every task merges to
`main` only via PR that Bifola approves.**

## Now (Phase 1)

| # | Task | Owner | Status | Brief / ADR |
|---|---|---|---|---|
| 1 | Real Claude consensus council behind the `Council` interface (single model, multi-persona; design → blind review → synthesis) | B | **IN-REVIEW** | built; _A to write ADR-001 + run Review→Verify_ |
| 2 | LLM ingestion layer: concept note / docs → canonical model (the last unproven loop piece) | B | PROPOSED | _A to write ADR-002_ |
| 3 | Stand up the delivery layer: FastAPI over engine+council → Next.js/Vercel → Fly+Supabase (dev) | Jem | PROPOSED | _A to write ADR-003 (hosting topology)_ |
| 4 | CI: GitHub Actions running the test suite on every PR | Jem | PROPOSED | — |
| 5 | Score engine vs in-scope SysSimulator blueprints (cost band + bottleneck) | Tunji | PROPOSED | _A to write test plan_ |
| 6 | Ticket Booking blueprint — benchmark case #2 (flash-sale spike what-if) | Tunji | PROPOSED | — |

## Next
- Reconciliation service (merge partial models; conflict/gap report). — B
- Canonical model store (Postgres, versioned). — A design / Jem build
- Knowledge base / RAG (pgvector grounding). — Phase 2

## Done
- Phase 0: deterministic engine + loop on URL Shortener; 7 tests green; 56-blueprint corpus.
- Council (build): real ClaudeCouncil behind the interface; prime-directive guard + high-stakes
  gate; 25 tests green; stub-mode loop unchanged. (Awaiting ADR-001 + A's review — task #1.)
