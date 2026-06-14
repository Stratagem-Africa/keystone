# Keystone — Team, Product Map & WIP Plan

**Doc:** 07 · **Status:** Draft v0.1 · **Date:** 14 June 2026 · **Owner:** Keystone A (Bifola)

The working plan for the team: who we are, what we're building, what's in flight,
and the rule that governs how it ships.

---

## 1. The team

| Person | Hat(s) | Owns | Availability |
|---|---|---|---|
| **Bifola** — *Keystone A* | Eng Lead · Architect · PM · QA / Lead Reviewer · **Release gatekeeper** | `docs/`, ADRs, `.agents/board.md`, roadmap; **approves every merge to `main`** | Core |
| **Bifola** — *Keystone B* | Core / AI builder | `prototype/keystone/**` (engine, council, ingestion), `prototype/tests/**` | Core |
| **Jem** | Full-stack · System designer · DevOps · Infra | The **delivery layer** — API service, frontend, deployment, CI | Core |
| **Tunji** | Full-stack (occasional) | Self-contained, low-coordination workstreams (blueprints, eval, docs) | Occasional |

> A and B are both Bifola in two modes — architect/reviewer vs builder. Jem is a
> full co-creator; Tunji contributes in windows. Set Jem's & Tunji's GitHub
> handles in `.github/CODEOWNERS` when assigning area ownership.

---

## 2. The non-negotiable rule (release governance)

**Nothing reaches `main` without Bifola's review and approval — no exceptions, including admins.**

- `main` is protected: **no direct pushes**; every change lands via Pull Request.
- Every PR requires an **approving review from Bifola** (`CODEOWNERS = * @BifolaX`
  + "require review from Code Owners").
- This binds Jem, Tunji, and every admin: branch → PR → Bifola reviews → Bifola merges.
- `main` is always deployable; production promotes from `main` only.

See §6 for the exact GitHub settings and the plan caveat.

---

## 3. Product map — what Keystone is made of

Intent → validated design. Legend: ✅ built · 🔨 building · ⏭ next · 🔭 later.

| Module | What it does | Status | Lead |
|---|---|---|---|
| Simulation engine | Deterministic queueing model — **the only producer of numbers** | ✅ Phase 0 | B |
| Council orchestrator | Real Claude consensus council (design→blind review→synthesis) behind the `Council` interface | 🔨 built, in review | B → A |
| Report & export | Markdown stress-test report + "where this is wrong" | ✅ Phase 0 | B |
| Ingestion & parsing | Docs / voice / text / diagram → partial canonical model | ⏭ next | B |
| Reconciliation | Merge partial models; conflict/gap report (never auto-resolve) | ⏭ next | B |
| Canonical model store | Versioned source of truth (Postgres) | 🔭 Phase 2 | A design / Jem build |
| Knowledge base / RAG | pgvector grounding corpus | 🔭 Phase 2 | — |
| Calibration store | Prediction vs actuals (the moat) | 🔭 Phase 2 | — |
| **API** (FastAPI) | HTTP surface over engine + council | ⏭ next | Jem |
| **Frontend** (Next.js) | Thin UI: intent in → report out | ⏭ next | Jem |
| **Infra** (Fly + Supabase) | Hosting, data, auth, storage | ⏭ next | Jem |

**Hosting topology** (to be ratified in ADR-003): Next.js → **Vercel**;
FastAPI + engine/council → **Fly.io** (+ a background worker for the long
council/ingestion runs); Postgres/Auth/Storage/pgvector → **Supabase**. The
$0-dev-target rule holds across all three free tiers.

---

## 4. WIP plan — now → near term

**Phase 1 goal:** prove the full loop on real inputs and stand up a deployable thin product.

### In flight
- **[B] Real Claude council** — built behind the interface; prime-directive guard +
  high-stakes gate + 25 tests green. → awaiting **[A] ADR-001** ratification + Review→Verify.

### Next up (distributed)

| Owner | Workstream | Output |
|---|---|---|
| **A** (Bifola) | ADR-001 (council), ADR-002 (ingestion design), ADR-003 (hosting topology), the eval/test plan; **review every PR** | `docs/adr/*`, board |
| **B** (Bifola) | LLM **ingestion layer** (concept note / docs → canonical model) — the last unproven piece of the loop; then reconciliation | `prototype/keystone/ingestion*` |
| **Jem** | Stand up the **delivery layer**: FastAPI over engine+council → Next.js on Vercel → Fly+Supabase (dev tier); **CI** (GitHub Actions running the test suite) | `api/`, `frontend/`, `.github/workflows/`, `fly.toml` |
| **Tunji** | **Ticket Booking** blueprint (benchmark case #2) + score the engine vs the in-scope SysSimulator corpus | `prototype/keystone/blueprints/`, `benchmarks/` |

### Boundaries (so we don't collide on the same files)
- **B owns the engine / AI core** (`prototype/keystone/**`) — it stays an importable library.
- **Jem owns the app / delivery layer** (API, UI, infra, CI) — imports the engine, never reaches into it.
- **Tunji's work is isolated** (new blueprint + eval files) — no shared hot files.
- The deterministic engine and the LLM stay separated (prime directive) across all of it.

---

## 5. Always-on gates (everyone, every PR)
- **Prime directive:** the LLM reasons; the engine computes. No metric ever comes from the LLM.
- **Accuracy honesty:** no bare numbers; never present an `ASSUMPTION` as `GROUNDED`; v1 is L0.
- **Harm floor:** no committed secrets; integer-minor-unit money; fail closed; uploads are untrusted.
- **High blast radius** (auth, money, PII, tenant isolation, schema, crypto): ADR + Bifola review *before* code.

---

## 6. How we work (the loop)
1. Pick a task from `.agents/board.md` (A maintains priority).
2. Branch from `main` (`feat/…`, `docs/…`, `fix/…`) — short-lived.
3. Build in your lane; keep tests green; keep PRs small.
4. Open a PR → **Bifola reviews** (adversarial Review→Verify on anything risky) → Bifola merges.
5. `main` deploys to dev; promote to prod at the Tier-1 line (first external user).

### GitHub enforcement
- **Branch protection on `main`:** require a PR; require 1 approving review **from Code Owners**;
  dismiss stale approvals; **include administrators**; block force-push / deletion.
- **`.github/CODEOWNERS`:** `* @BifolaX` → Bifola is auto-requested and required on every PR.
- ⚠️ **Plan caveat:** branch protection on a **private** repo needs GitHub **Team** (≈$4/user/mo).
  On Free it is **not enforceable** for private repos — until you upgrade, the rule runs on
  convention + CODEOWNERS auto-review-requests (Bifola is auto-added as reviewer, but a merge is
  not hard-blocked). Decision for Bifola: **upgrade to enforce**, or **convention-for-now**.
