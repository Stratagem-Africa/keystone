# CLAUDE.md — Keystone

Guidance for Claude Code (and any AI agent) working in this repository. **Read this every session before acting.**

---

## Team & coordination (read every session)

Keystone is built by a small team, each using Claude Code: **Bifola** (architect/reviewer + builder of the trust-critical core) and **Jem** (`foreverjamila` — delivery layer: API, frontend, infra, CI). Bifola's Claude reviews contributors' pushes and **leaves clear, beginner-friendly feedback — what to change, *why* it matters, and where to look — and lets the contributor fix their own code** (the reviewer does **not** push fixes onto their branch; she's learning by doing). The reviewer then re-checks the gate and merges. Bifola's Claude still makes direct fixes only to the trust-critical core it owns. Because of that:

- **MANDATORY — pull before you work AND before every commit.** Run `git fetch origin && git pull` on your branch at session start and again before committing/pushing. Your local copy is frequently *behind* `origin` (a concurrent Bifola/Claude session runs, and `main` moves as PRs merge); committing stale causes divergence. If you see *"branches have diverged,"* `git pull --rebase` before anything else.
- **Branch → small PR → review → merge.** Nobody pushes to `main` directly. Bifola's Claude merges reviewed PRs; **production deploys only on Bifola's manual trigger** — nothing reaches users without him.
- **CI is LOCAL + MANUAL.** GitHub Actions is dormant (account billing), so the merge gate is `scripts/check.sh` (the test/lint signal) run by the reviewer — `scripts/review-pr.sh <N>` fetches + diffs + checks a PR in one step. Never merge on a red gate. Full runbook in **`CONTRIBUTING.md`** ("Reviewer runbook"). The `.github/workflows/*.yml` are `workflow_dispatch` stubs, re-enabled instantly if Actions returns.
- New contributor? Read **`docs/10-Contributor-Guide.md`** and **`CONTRIBUTING.md`** first.

---

## What Keystone is

*Describe what you're building in plain English — a grounded consensus of AI architects designs it, justifies every decision, and validates it with simulation, improving toward enterprise-grade correctness over time.*

It is **not** a diagramming tool (no blank canvas) and **not** "a better simulator" (simulation is one feature). It takes a builder from **intent → validated design**. Primary user: developers who can build but can't yet architect for scale. Full strategy in `docs/product-definition.md`.

---

## Prime directive — never violate

**The LLM reasons; the deterministic engine computes.** No metric is ever produced by a language model. `prototype/keystone/simulation.py` is the *only* source of numbers (utilisation, bottleneck, breakpoint, latency, cost). The council (`council.py`) reasons about design and emits ADRs — it must **never** emit a throughput/latency/cost figure. This separation is the entire trust basis of the product (`docs/03-Accuracy-and-Trust-Charter.md`). Any change that blurs it must be rejected.

## Accuracy honesty — non-negotiable

- Every number ships with its **assumptions + confidence band + the model that produced it**. No bare numbers.
- Never present an `ASSUMPTION` as `GROUNDED`. Never claim "pristine/elite/100%" accuracy. v1 is **L0 (Directional)**.
- High-stakes domains (elections, payments, health, safety) get a **mandatory expert-review flag**; never imply production-safety or certification.
- Every report keeps its "where this is wrong" section. Honesty is the feature.

## Engineering standards — Stratagem Engineering Playbook v1.0

- **Tier-1** from first external traffic (external users + multi-tenant + commercially-sensitive uploads). The **harm floor binds always**: no committed secrets, no data loss, no corrupted money (integer minor units only), no leaked credentials.
- Obligations: `MUST` (must be gated, not just intended) · `SHOULD` (deviation requires an ADR) · `NICE`. Provenance: `GROUNDED` (file:line/benchmark proves it) · `GAP` (state shortfall + fix) · `ASSUMPTION`.
- **Evidence is a required field.** Load-bearing claims carry `file:line`. A citation that doesn't resolve in the tree is *invented* — drop the dependent claim.
- Any change touching **auth, money, PII, tenant isolation, schema, or crypto** → adversarial **Review → Verify → Adjudicate** before code; **a human ratifies** — AI proposes, never self-applies.
- **Re-read a claimed fix** (open the changed code). A fix that *sounds* right ≠ a fix that *closes the bug*.

---

## Repository structure

```
Keystone/
  CLAUDE.md                 <- you are here
  README.md                 <- repo overview + run
  .env.example              <- copy to .env (gitignored); never commit keys
  pyproject.toml
  docs/                     <- the spec suite (read for any non-trivial change)
    product-definition.md   00..06: PRD, architecture, accuracy charter, fn spec, data model, roadmap
  prototype/                <- the running Phase-0 codebase
    keystone/
      model.py              canonical system model (single source of truth)
      simulation.py         deterministic engine — the ONLY producer of numbers
      council.py            consensus council interface + deterministic stub
      report.py             markdown report incl. "where this is wrong"
      blueprints/           input system models (url_shortener.py)
      benchmarks/           all 56 SysSimulator blueprints = ground-truth eval corpus
    tests/                  deterministic engine tests
    run_url_shortener.py    end-to-end loop
```

## Stack (free-tier first, enterprise-grade later)

- **Language/core:** Python 3.10+ · FastAPI for the API (when added). Engine is pure stdlib today; hot path may be ported to Rust later (the SysSimulator lesson) — not now, and only behind an ADR.
- **DB:** Supabase (Postgres) free tier — also gives Auth, Storage, pgvector (RAG later). Note: free projects pause after 7 days idle (cron-ping to keep alive).
- **File/object storage:** Supabase Storage or Cloudflare R2. **Not Google Drive** (not an app object store).
- **Frontend (later):** Next.js + Tailwind on Vercel free tier.
- **AI:** Claude API via the Agent SDK (Haiku for dev = pennies). Council = single model, multiple persona prompts (cost control). May prototype on free OpenRouter models / local Ollama for $0.
- **Cost rule:** **do not add a paid dependency without an ADR.** Dev target is ~$0/month.

## How to run

```bash
scripts/check.sh                             # the merge gate: full suite (+ruff if installed); run before every push
cd prototype
python3 run_url_shortener.py                 # end-to-end loop -> outputs/url_shortener_report.md (loads .env; a live council writes *.local.md)
python3 -m unittest discover -s tests -v     # engine tests (must stay green)
python3 -m keystone.benchmarks.syssimulator_blueprints   # the benchmark corpus
```

## Conventions

- Conventional Commits; reference the doc/decision the change implements.
- Python: type hints, dataclasses, **stdlib-first** — no heavy dependency without an ADR.
- The engine must stay **deterministic and reproducible** (seeded); tests assert exact behaviour.
- Secrets live in `.env` (gitignored). Never commit a key (harm floor).
- Treat uploaded user documents as **untrusted input** to the LLM (prompt-injection guard).

## Current status (Phase 1 — in progress)

Phase 0 complete (deterministic engine + loop; 56-blueprint corpus). The documented Phase-1 list is now **landed on `main`, all stub-default with no live activation**: (1) real Claude consensus council behind the `Council` interface (#29, ADR-001) — Keystone-owned high-stakes gate + Hybrid prime-directive guard; (2) LLM **ingestion layer** (#31, ADR-002) — intent → canonical model behind the `Ingestor` seam, with the injection envelope + harm-floor secret-scan; (3) **engine scoring** vs the benchmark corpus (#33, docs/11); (4) **Ticket Booking** as case #2 + a flash-sale what-if (F6). The full `intent → ingest → council → simulate → report` loop runs offline; the suite is green (**290 tests** as of 2026-06-28).

**All LLM layers default to STUB** (`COUNCIL_PROVIDER` / `INGEST_PROVIDER`); real activation is a **manual Bifola trigger** — and is gated on the council's structured-output v2 lever (ADR-001) + the model store's no-retention/tenant-isolation MUST (ADR-002) before any real upload. **Multi-LLM cross-vendor consensus** is also stub-gated (ADR-010, ratified 2026-06-25): `COUNCIL_PROVIDER=consensus` runs the council on a primary model + independent voter models (Claude/OpenAI/OpenRouter/local Ollama) via the provider-agnostic `LLM` seam; the prime-directive guard runs on every model, keys come from env, and activation inherits ADR-001's council gates. The run scripts load a local (gitignored) `.env` on startup (`_env.load_env`, #80), so activation is just: paste keys + flip `COUNCIL_PROVIDER`; a live run writes `outputs/<name>.local.md` (gitignored) and never clobbers the committed deterministic goldens. The recommended near-$0 default in `.env.example` is a Haiku primary + two **free** OpenRouter voters (`CONSENSUS_VOTERS=openrouter:…:free, openrouter:…:free`); a fully $0 panel uses local Ollama. (`KB_PROVIDER` / `INGEST_PROVIDER` load the same way.)

**Grounding (the KB) is ACTIVATED** (ADR-006; `KB_PROVIDER=curated` is now the report-generation default; the library `make_knowledge_base()` default stays `stub`; `KB_PROVIDER=stub` disables). Reports show cited **GROUNDED/RECONCILE** evidence behind input numbers + the **cost rates** — using the corpus (#64) + the ratified rate evidence (`benchmarks/grounded_pricing_rates.json`, #71). This is **evidence-only**: grounding **never changes a computed number** (the engine never reads a grounding value); it only adds the evidence sections + provenance labels, and out-of-band modeler values are flagged for reconciliation, never overwritten (override is opt-in, unshipped). The KB uses **no LLM** — it is cited data, so this does not touch the prime directive or the $0/offline rule, and the council/ingestion layers stay STUB. The corpus has grown to **27 cited datapoints** (#77, throughput/latency), and each grounded row now surfaces its **measured context** (the hardware/workload the cited benchmark ran on, #93) so a reader can judge whether the evidence fits their setup.

**Output confidence bands + honesty/correctness hardening (shipped this cycle).** Every headline number can now ship with a **confidence band** propagated deterministically from the cited input ranges (#88) — shown on the Verdict summary (#95), the headline-metrics table, and **per flow** (#94); it is honestly **omitted** (with a caveat) when the cited range crosses the model's stable limit, so there is no false precision. A **third worked case** — **Payments / Checkout** (#91: high-stakes expert-review gate + a rate-limited external gateway as the binding constraint) — joins url_shortener + ticket_booking. Two adversarial **audits** landed real fixes: a report **honesty audit** (#90 — fixed ASSUMPTION-vs-GROUNDED contradictions, mixed-provenance caveat) and an **engine correctness audit** (#92 — core math verified CLEAN; added capacity/latency input validation + per-flow latency). **Harm-floor hardening:** integer-money invariants (instances + exact-integer cost division, #83) + the grounded-cost float seam closed (#86). Every band/grounding change is **evidence-only / display-only** — the engine stays the sole producer of numbers; determinism + the stub off-state goldens hold. **Delivery layer (Jem):** the async API loop — background worker + Postgres job state (#85) + poll-status / fetch-report endpoints (#89) — has landed.

**Next** (the high-leverage moves are now **decision- or data-gated**): grow the reference-model corpus toward **L1 calibration** (needs new web-verified, **ratified** datapoints) and **true context-matching** (per-vendor/per-context corpus data, then match-with-fallback plumbing); **activate the LLM layers** (council / ingestion — a manual Bifola trigger: add keys + flip the provider env, gated on the model store's tenant-isolation MUST before real uploads); the **canonical model store** (docs/05, versioned + tenant-isolation) and the rest of the **delivery layer** (FastAPI → Next.js, ADR-003 — Jem). *(F2 reconciliation is already **built** — `reconciliation.py` + `run_reconciliation.py`.)*

## What NOT to do

- Don't let the LLM emit numbers.
- Don't claim accuracy the eval harness hasn't proven.
- Don't add cloud services that cost money without an ADR (we are on free tiers).
- Don't break the v1 scope freeze (single-region web stack); streaming/multi-region/chaos is v2.
- Don't over-engineer. Ship the smallest correct thing; respect the YAGNI lane.
