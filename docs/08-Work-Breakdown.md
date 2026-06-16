# Keystone — Work Breakdown (activities × responsibility)

**Doc:** 08 · **Status:** Draft v0.1 · **Date:** 14 June 2026 · **Owner:** Keystone A (Bifola)

Every plan in `docs/07` broken into small, **PR-sized** activities with a clear owner.
Owners: **A** / **B** = Bifola (architect-reviewer / builder), **J** = Jem. Tunji =
occasional overflow (Epic 7), no critical-path items. Status: ☐ todo · ◐ doing · ☑ done.
Each row should be roughly one PR. Bifola reviews & approves every one before `main`.

---

## Epic 1 — Council (close it out)
| # | Activity | Owner | Output |
|---|---|---|---|
| ☑ | Build real ClaudeCouncil behind the interface (3-stage, guard, high-stakes gate, 25 tests) | B | `claude_council.py` |
| 1.1 | ADR-001: record the council decision, dissent, kill-criteria, and the 4 deferred items | A | `docs/adr/ADR-001` |
| 1.2 | Run Review→Verify on B's council commit; write verdict / fix-brief | A | `docs/reviews/` |
| 1.3 | Apply fix-brief if any; keep tests green | B | `prototype/keystone/` |

## Epic 2 — Ingestion layer (the last unproven loop piece)
| # | Activity | Owner | Output |
|---|---|---|---|
| 2.1 | ADR-002: ingestion design (sources, extraction, assumption ledger, **prompt-injection guard** — uploads are untrusted) | A | `ADR-002` |
| 2.2 | File intake + parsing: PDF/DOCX/MD/TXT → clean text; secret + size scan on intake | J | `ingestion/parse.py` |
| 2.3 | LLM extraction: text → partial `SystemModel` + assumption ledger (**trust-critical**) | B | `ingestion/extract.py` |
| 2.4 | Reconciliation: merge partial models → conflict/gap report (never auto-resolve) | B | `ingestion/reconcile.py` |
| 2.5 | Tests: parsing (J), extraction via fake LLM (B), planted-conflict reconciliation (B) | J + B | `tests/` |

## Epic 3 — API layer (FastAPI on Fly)
| # | Activity | Owner | Output |
|---|---|---|---|
| 3.1 | ADR-003: ratify hosting topology (Cloudflare + Fly + Supabase) | A | `ADR-003` |
| 3.2 | FastAPI scaffold: health, CORS, Supabase-JWT auth middleware | J | `api/` |
| 3.3 | Endpoint: submit intent → enqueue council/ingestion job | J | `api/` |
| 3.4 | Background worker: runs long council/ingestion jobs; job state in Postgres | J | `api/worker.py` |
| 3.5 | Endpoint: poll job status / fetch report (JSON + markdown) | J | `api/` |
| 3.6 | `Dockerfile` + `fly.toml`; deploy to dev | J | `fly.toml` |

## Epic 4 — Frontend (Next.js on Cloudflare)
| # | Activity | Owner | Output |
|---|---|---|---|
| 4.1 | Scaffold Next.js + Tailwind; OpenNext → Cloudflare; wire design tokens from doc 09 | J | `frontend/` |
| 4.2 | Intent input (text + file upload) → submit | J | `frontend/` |
| 4.3 | Report view: verdict, component table, ADRs, and **"where this is wrong" front-and-centre** (trust = the feature) | J | `frontend/` |
| 4.4 | What-if interactions (re-simulate, show the delta) — the retention feature; must feel instant | J | `frontend/` |
| 4.5 | Auth UI (Supabase) | J | `frontend/` |

## Epic 5 — Infra & data (Supabase + Cloudflare + Fly)
| # | Activity | Owner | Output |
|---|---|---|---|
| 5.1 | Supabase dev project: Postgres + Auth + Storage + pgvector; cron-ping to stop the 7-day pause | J | console |
| 5.2 | Canonical-model-store schema (A designs the spec, J writes the migration) | A → J | `db/migrations/` |
| 5.3 | Cloudflare Pages project + R2 bucket (uploads) | J | console |
| 5.4 | Secrets discipline: per-dev `.env`, Fly secrets, Cloudflare/Supabase secrets — never in repo | J | — |

## Epic 6 — CI/CD & quality gates
| # | Activity | Owner | Output |
|---|---|---|---|
| 6.1 | GitHub Actions: run the test suite on every PR (**works on Free** — gives a signal even without branch protection) | J | `.github/workflows/ci.yml` |
| 6.2 | Lint + type: `ruff` + `mypy` on PR | J | same |
| 6.3 | Deploy-on-merge-to-`main`: Fly (backend) + Cloudflare (frontend) | J | `.github/workflows/deploy.yml` |
| 6.4 | (When on GitHub Team) enable branch protection on `main`: PR + Code-Owner review + include admins | A | repo settings |

## Epic 7 — Benchmarks & eval (ex-Tunji overflow, split J + B)
| # | Activity | Owner | Output |
|---|---|---|---|
| 7.1 | Ticket Booking blueprint (flash-sale spike what-if) | J or B | `blueprints/ticket_booking.py` |
| 7.2 | Score engine vs in-scope SysSimulator corpus (cost band + bottleneck) | J or B | `benchmarks/` |
| 7.3 | Per-component error-envelope notes (step toward accuracy level L1) | B | `docs/` |

## Cross-cutting (Bifola, continuous)
- **A** reviews & approves **every** PR before `main` (the gate); maintains the board + ADRs.
- Prime directive / accuracy honesty / harm floor checked on every PR.
- **J** keeps CI green; **B** keeps the engine deterministic and the LLM out of the number path.

---

### Suggested first sprint (1–2 weeks)
- **A:** ADR-001, ADR-003. **B:** ingestion extract (2.3). **J:** CI (6.1), FastAPI scaffold (3.2),
  Next.js+Cloudflare scaffold (4.1), Supabase dev (5.1).
- Goal: a deployed dev URL that runs the existing loop end-to-end behind a thin UI.
