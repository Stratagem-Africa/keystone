# Keystone — Team, Product Map & WIP Plan

**Doc:** 07 · **Status:** Draft v0.1 · **Date:** 14 June 2026 · **Owner:** Keystone A (Bifola)

The working plan for the team: who we are, what we're building, what's in flight,
and the rule that governs how it ships. Granular activity breakdown lives in
`docs/08-Work-Breakdown.md`.

---

## 1. The team

| Person | Hat(s) | Owns | Availability |
|---|---|---|---|
| **Bifola** — *Keystone A* | Eng Lead · Architect · PM · QA / Lead Reviewer · **Release gatekeeper** | `docs/`, ADRs, `.agents/board.md`, roadmap; **approves every merge to `main`** | Core |
| **Bifola** — *Keystone B* | Core / AI builder | the trust-critical core: deterministic engine, council, ingestion→model transform | Core |
| **Jem** | Full-stack (strong **Python**) · System designer · DevOps · Infra | **delivery layer + backend code** — FastAPI/API, file parsing, frontend, infra, CI | Core |
| **Tunji** | Full-stack (occasional) | **Overflow only** — picks up scoped chunks when free; his lane is split between Jem & Bifola | Occasional |

> A and B are both Bifola in two modes. Jem is a full co-creator who **writes
> Python/backend**, not just UI. Tunji is off the critical path — anything for him
> is shared between Jem and Bifola. Set Jem's & Tunji's GitHub handles in
> `.github/CODEOWNERS` when assigning area ownership.

---

## 2. The non-negotiable rule (release governance)

**Nothing reaches `main` without Bifola's review and approval — no exceptions, including admins.**

- `main` is protected: **no direct pushes**; every change lands via Pull Request.
- Every PR requires Bifola's approving review (`CODEOWNERS = * @BifolaX`).
- Binds Jem, Tunji, and every admin: branch → PR → Bifola reviews (and edits if needed) → Bifola merges.
- **Production deploys from `main` only** — so nothing reaches prod without Bifola's review.

See §6 for the GitHub settings, the four ways to edit a PR, and the plan caveat.

---

## 3. Product map — what Keystone is made of

Intent → validated design. Legend: ✅ built · 🔨 building · ⏭ next · 🔭 later.

| Module | What it does | Status | Lead |
|---|---|---|---|
| Simulation engine | Deterministic queueing model — **the only producer of numbers** | ✅ Phase 0 | B |
| Council orchestrator | Real Claude consensus council (design→blind review→synthesis) behind the `Council` interface | 🔨 built, in review | B → A |
| Report & export | Markdown stress-test report + "where this is wrong" | ✅ Phase 0 | B |
| Ingestion & parsing | Docs / voice / text / diagram → partial canonical model | ⏭ next | B core + Jem parsing |
| Reconciliation | Merge partial models; conflict/gap report (never auto-resolve) | ⏭ next | B |
| Canonical model store | Versioned source of truth (Postgres) | 🔭 Phase 2 | A design / Jem build |
| Knowledge base / RAG | pgvector grounding corpus | 🔭 Phase 2 | — |
| Calibration store | Prediction vs actuals (the moat) | 🔭 Phase 2 | — |
| **API** (FastAPI) | HTTP surface over engine + council | ⏭ next | Jem |
| **Frontend** (Next.js) | Thin UI: intent in → report out | ⏭ next | Jem |
| **Infra** (Cloudflare + Fly + Supabase) | Hosting, data, auth, storage | ⏭ next | Jem |

**Hosting topology** (to ratify in ADR-003): Next.js → **Cloudflare** (Pages/Workers
via OpenNext — the stack the team already runs on SAMS); FastAPI + engine/council →
**Fly.io** (+ a background worker for long council/ingestion runs); Postgres / Auth /
Storage / pgvector → **Supabase**; large uploads → **Cloudflare R2**. $0-dev target
holds across the free tiers. Note: Cloudflare Workers can't run the Python backend —
**frontend on Cloudflare, backend on Fly**.

---

## 4. WIP plan — now → near term

**Phase 1 goal:** prove the full loop on real inputs and stand up a deployable thin product.

### In flight
- **[B] Real Claude council** — built behind the interface; prime-directive guard +
  high-stakes gate + 25 tests green. → awaiting **[A] ADR-001** + Review→Verify.

### Next up (distributed)

| Owner | Workstream | Output |
|---|---|---|
| **A** (Bifola) | ADR-001 (council), ADR-002 (ingestion), ADR-003 (hosting), eval plan; **review every PR** | `docs/adr/*`, board |
| **B** (Bifola) | LLM **ingestion core** (text → canonical model + assumption ledger) + reconciliation — trust-critical | `prototype/keystone/ingestion/` |
| **Jem** | **Delivery layer + backend**: FastAPI over engine+council, the ingestion **parsing** layer (Python), Next.js on **Cloudflare**, Fly+Supabase (dev), **CI** | `api/`, `frontend/`, `ingestion/parse*`, `.github/workflows/`, `fly.toml` |
| **Jem + Bifola** | (ex-Tunji overflow) **Ticket Booking** blueprint + score engine vs corpus — split | `prototype/keystone/blueprints/`, `benchmarks/` |

### Boundaries (avoid collisions; the review is the trust gate)
- **B owns the trust-critical core** — deterministic engine, the council's no-numbers guard, and the ingestion→canonical-model transform. The prime directive lives here.
- **Jem owns the delivery layer + safe backend** — FastAPI/API, file parsing, frontend, infra, CI. She writes Python freely here; it imports the engine as a library, never reaches into it.
- **Overflow (ex-Tunji)** — blueprint + benchmark scoring, split Jem/Bifola, in new files (no shared hot paths).
- Every PR passes through Bifola's review, so the boundaries are about avoiding merge collisions, not gatekeeping trust.

---

## 5. Always-on gates (everyone, every PR)
- **Prime directive:** the LLM reasons; the engine computes. No metric ever comes from the LLM.
- **Accuracy honesty:** no bare numbers; never present an `ASSUMPTION` as `GROUNDED`; v1 is L0.
- **Harm floor:** no committed secrets; integer-minor-unit money; fail closed; uploads are untrusted.
- **High blast radius** (auth, money, PII, tenant isolation, schema, crypto): ADR + Bifola review *before* code.

---

## 6. How we work (the loop + governance)
1. Pick a task from `docs/08-Work-Breakdown.md` / `.agents/board.md`.
2. Branch from `main` (`feat/…`, `fix/…`, `docs/…`, `chore/…`) — short-lived.
3. Build in your lane; keep tests green; keep PRs small (one task each).
4. Open a PR → **Bifola reviews** (and edits if needed — see below) → Bifola **squash-merges** to `main`.
5. `main` deploys to dev; promote to prod at the Tier-1 line (first external user).

### How Bifola reviews / edits a PR before it ships
1. **Suggest changes** inline in the review → Jem one-click "commit suggestion". (small edits)
2. **Request changes** → Jem revises and re-pushes.
3. **Push directly to her PR branch** (`gh pr checkout <n>` → edit → commit → push) — hands-on edits.
4. **Edit in the GitHub web UI** on her branch.
Production builds run **only from `main`**, so editing-before-merge = editing-before-prod by construction.

### GitHub enforcement — the free model (decided: **not upgrading**)
Branch protection isn't available on private repos on GitHub Free (`403`), and we're
staying on Free. So the rule is enforced **without** paid branch protection:
- **CODEOWNERS** (`* @BifolaX`) → Bifola is auto-requested on every PR.
- **CI** (`.github/workflows/ci.yml`) → the test suite runs on every PR and on `main`; a red PR is visible at review time.
- **Production is Bifola-gated** → prod deploys **only** on Bifola's manual trigger
  (`workflow_dispatch` / a release tag he controls). So even an accidental direct push to
  `main` never ships to users without Bifola. *This gates the thing that actually matters — production — for free.*
- **Convention** → only Bifola merges to `main`; nobody pushes to `main` directly. See `CONTRIBUTING.md`.
- **Residual risk (accepted):** on Free, an admin *can* technically push to `main` or self-merge — it isn't hard-blocked. Mitigated by CI + the Bifola-gated prod deploy + the convention. Revisit only if the team grows or the risk bites.
