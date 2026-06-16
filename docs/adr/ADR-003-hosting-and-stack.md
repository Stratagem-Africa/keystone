# ADR-003 — Hosting & Stack Topology

**Status:** Accepted · **Ratified-by:** Bifola, 2026-06-15
**Date:** 2026-06-15 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/02` §5 (recommended stack), `docs/07` §3, `docs/08` Epics 3–6

---

## Context

Phase 1 needs a deployable thin product (intent → report) on a **free-tier-first, ~$0/month dev** budget. Two forces shape the topology:

1. **The council and ingestion are long-running, multi-LLM-call orchestrations** (the council alone is ~15 sequential Claude calls; ingestion adds an LLM pass per document). On Opus-tier models a run can take minutes — which **exceeds serverless function timeouts** (e.g. Cloudflare Workers / Vercel functions). The Python backend therefore needs a host that allows long-running work + a background worker.
2. **The team already runs Next.js-on-Cloudflare (OpenNext) and Fly.io in production on SAMS** — so choosing those here means existing tooling and muscle memory, not a learning tax.

The prime directive (the LLM reasons; the deterministic engine computes) must survive the deployment topology: the frontend must never call Claude or the engine directly.

## Decision

| Layer | Choice |
|---|---|
| Frontend | **Next.js + Tailwind** on **Cloudflare** (Pages/Workers via OpenNext); open-source fonts (Inter + Newsreader + Geist Mono) |
| Backend | **Python 3.10+ / FastAPI**; engine stays **pure stdlib** (zero-dep, deterministic); hosted on **Fly.io** (API + background worker) |
| AI / council | **Claude API** via the Anthropic SDK; **Haiku 4.5** dev / **Opus 4.8** prod (one `COUNCIL_MODEL` env flag) |
| Data / Auth / Storage / Vectors | **Supabase** (Postgres + Auth + Storage + pgvector) |
| Large uploads | **Cloudflare R2** |
| Repo / VCS | **GitHub** `Stratagem-Africa/keystone`, **private**, **Free plan** |
| CI / CD | **GitHub Actions** — tests on PR; deploy on merge; **production deploy = Bifola-gated manual trigger** |
| Governance | Trunk-based · PR + CODEOWNERS (`@BifolaX`) · Bifola merges high-blast-radius · prod gated |

**Boundary (MUST):** Browser → Cloudflare (Next.js UI) → **FastAPI API on Fly** → Supabase. The frontend never talks to Claude or the engine directly; the engine remains the only producer of numbers.

## Rationale (per choice)

- **Cloudflare (frontend):** existing SAMS stack; free Preview-per-PR + Production; edge performance suits the design standard's <2.0s LCP budget (`docs/09` §10).
- **Fly (backend):** the only choice that holds a minutes-long Python orchestration + a background worker; team already operates it.
- **Supabase (data):** one free backbone for Postgres + Auth + Storage + pgvector (RAG later) — minimizes moving parts.
- **Claude (AI):** configurable model keeps dev cheap (Haiku ≈ $0.10 per council run) and prod strong (Opus); the **only paid line** in the stack.
- **GitHub Free:** private repos are free; we accept convention-based main protection (no Team upgrade) because production is Bifola-gated regardless.

## Recorded dissent (kept, not smoothed)

- **YAGNI / onboarding:** Next-on-Cloudflare via OpenNext has real quirks ("not the Next.js you know") — a tax for any non-SAMS contributor. *Accepted:* the team already runs it; the tax is already paid.
- **SRE:** two hosts (Cloudflare + Fly) means two deploy surfaces and a CORS/auth seam versus an all-in-one platform. *Accepted:* the long-running Python backend genuinely cannot live on Cloudflare Workers.
- **Security:** GitHub Free cannot hard-enforce `main` protection on a private repo; the gate leans on convention + CODEOWNERS + the Bifola-gated prod deploy. *Accepted with eyes open* (residual risk logged in `docs/07` §6).

## Confidence

**High** — for the Phase-1, single-region web-stack scope. Lower confidence on long-horizon scale (a single Fly worker; Supabase free-tier ceilings), which the kill-criteria below guard.

## Kill criteria (revisit this ADR if…)

- Council/ingestion latency or concurrency outgrows a single Fly worker → real queue + worker fleet.
- Supabase free-tier limits bite (idle pauses, connection caps) → paid Supabase or self-hosted Postgres.
- OpenNext/Cloudflare friction costs more than a Vercel move would save → reconsider the frontend host.
- The team grows and the convention-based `main` gate fails → GitHub Team + branch protection.
- Second region / streaming / multi-tenant-at-scale enters scope → that is v2, out of this ADR.

## Consequences

Ratifies `docs/07` §3 and unblocks `docs/08` Epics 3–6. Jem builds the delivery layer (API, frontend, infra, CI) on this topology; the engine/council/ingestion core stays an importable library behind the FastAPI boundary.
