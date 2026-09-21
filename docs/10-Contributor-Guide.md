# Keystone — Contributor Guide (Jem)

**Doc:** 10 · **Date:** 2026-06-16 · **Owner:** Keystone A (Bifola)

Welcome, Jem. This gets you building today. Read it once, then start.

---

## 0. For your Claude — coordination rules (read these FIRST, every session)

You'll use Claude Code too. **Bifola's Claude reviews your pushes and pushes fixes/improvements straight back onto your branch** — so two rules keep us from clobbering each other:

1. **PULL BEFORE YOU WORK.** At the start of every session: `git fetch origin && git pull` on your branch. The reviewer may have pushed changes since you last looked.
2. **PULL BEFORE YOU COMMIT.** Again right before you commit or push. Your branch is frequently *ahead* of your local copy; committing on a stale branch causes divergence and conflicts.

If you ever see *"your branch and origin/… have diverged,"* stop and `git pull --rebase` before doing anything else.

> Tell your Claude, in its instructions: **"Before you work and before every commit, run `git fetch && git pull` on my branch — Bifola's Claude pushes review fixes directly to it. Never commit on a stale branch."**

---

## 1. Who you are on the team

You own the **delivery layer + backend code**: the **FastAPI API, file parsing, the Next.js frontend, infra (Cloudflare / Fly / Supabase), and CI**. You write Python freely here. The trust-critical core (the deterministic engine, the council's no-numbers guard, the ingestion→model transform) is Bifola's lane — your code **imports** the engine as a library, never reaches into it.

## 2. The workflow (free, in-session review)

1. Pick an issue assigned to you (start with **sprint-1**: #10, #15, #20).
2. Branch from `main` (`feat/…`, `fix/…`) — short-lived.
3. Build it (to `docs/09` + the stack). Keep PRs small.
4. Push your branch / open a PR.
5. Bifola pings his Claude → **we review and leave you clear feedback**: *what to change, **why** it matters, and where to look*, plus a *Verdict*. **You make the fixes on your own branch and re-push** — that's how you learn the codebase; we don't edit your branch for you.
6. We re-check the gate and **merge** when it's green and clean. `git pull` regularly so your local copy stays current with `main`.
7. Production deploys only on Bifola's manual trigger — nothing that merges ships to users without him.

## 3. The gates — they bind everything, even the UI

- **Prime directive:** the LLM reasons; the deterministic engine is the **only** source of numbers. Your frontend/API must **never** compute, fake, or hardcode a metric — every number comes from the engine via the API.
- **Accuracy honesty:** no bare numbers in the UI — every metric shows its **confidence band + provenance** (`docs/09`). Never render an `ASSUMPTION` as `GROUNDED`.
- **Harm floor:** never commit secrets (`.env` is gitignored — keep it so); treat uploaded user docs as **untrusted** input (prompt-injection); fail closed.
- **Design standard:** `docs/09` is the bar for everything user-facing. Read its **§11 (Fixed vs. Latitude)** — the trust thesis is fixed; the craft is yours to own.

## 4. The stack (ratified — `docs/adr/ADR-003`)

Frontend: **Next.js + Tailwind on Cloudflare** (OpenNext). Backend: **FastAPI on Fly**. Data: **Supabase** (Postgres + Auth + Storage + pgvector). Uploads: **Cloudflare R2**. AI: Claude (the council). All free-tier; **$0 dev target** (you won't need an API key until the deployed council goes live).

## 5. Setup (≈5 minutes)

```bash
git clone https://github.com/Stratagem-Africa/keystone.git
cd keystone
./setup.sh
```

That is the whole thing. `setup.sh` checks what you have, names anything missing and how to get it,
installs the frontend dependencies, and — on macOS — builds `Keystone.app`, puts a **Keystone**
shortcut on your Desktop, and installs a git hook so every later `git pull` rebuilds the app for
you. It is safe to re-run at any time.

**What you need first:**

| Tool | Why | If missing |
|---|---|---|
| **python3** | the engine, the API, the tests | `xcode-select --install` (macOS), or python.org |
| **node 20+ and npm** | **the frontend, and half the merge gate** | [nodejs.org](https://nodejs.org), or `brew install node` |
| Claude Code CLI | *optional* — only the council's reasoning | `npm install -g @anthropic-ai/claude-code`, then `claude` |

**Node is not optional for you.** You own the frontend, and `scripts/check.sh` runs its frontend
half — eslint, `next build`, `tsc`, the design-token guard — only when `frontend/node_modules`
exists. Without it that half prints `==> frontend: skipped` and **the gate still exits green**. A
pass on a machine with no node is a Python-only pass, which is how a lint error reached `main` in
#140. Install node and the gate is whole again.

Copy `.env.example` → `.env` (gitignored) when you need config. **Never commit `.env`.**

### Running it

```bash
./scripts/keystone-local.sh            # the whole app: API + studio on 127.0.0.1:3000/studio
./scripts/keystone-local.sh --offline  # no AI at all — the engine and all 56 designs, $0
```

On macOS, double-clicking the Desktop **Keystone** shortcut does the same thing. Either way you get
**the same Next.js frontend the web app serves** — one codebase, not a second UI to keep in sync.

The desktop wrapper exists for one reason: the council can run on `claude -p`, which is a program on
*your* laptop, so Keystone has to run locally to use your own subscription instead of a paid API
key. A Dock icon is just a nicer way to start a local process than remembering a shell command.
Nothing is hosted, shared or billed — it binds to loopback only, so nothing outside your machine can
reach it.

### The gate — run both halves before every push

```bash
./scripts/check.sh     # tests + ruff + mypy + eslint + next build + tsc
```

Keep it green; never push on red. Some Postgres-backed tests are deliberately **not** in that run
(they need a real database). If your change touches `db/migrations/` or `db/testing/`, also run:

```bash
KEYSTONE_TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres \
  ./scripts/test_tenant_isolation.sh
```

## 6. Your first sprint — pick any (all independent)

### #10 — API: FastAPI scaffold → `api/`
**Build:** a FastAPI app that **imports** the existing engine + council as a library and exposes them over HTTP.
**Done when:**
- `api/` with `GET /health` and `POST /design` (or `/simulate`): takes a model (start from the `url_shortener` blueprint) → runs `simulate()` + the council → returns the report as **JSON**.
- It **imports** `keystone.simulation` / `keystone.council` — rebuilds none of it.
- Runs locally (`uvicorn`), returns a real report; one basic test; engine stays zero-dep (`anthropic` only loaded when the council provider is `claude`).

### #15 — Frontend: Next.js + Tailwind on Cloudflare → `frontend/`
**Build:** the app shell + the design-system foundation.
**Done when:**
- Next.js + Tailwind, OpenNext-configured for Cloudflare; `npm run dev` works.
- Design tokens from `docs/09` §2.4 (palette hex), the 3 font families (Inter + Newsreader + Geist Mono), and a first-pass **`<Metric>` / `<ConfidenceBand>` primitive** — a number that *cannot render* without a band + provenance (`docs/09` §3.1, §11).
- A placeholder landing that respects the standard (serif = reasoned, mono = computed). No real numbers yet — you wire to the API later.
- Deploys to a Cloudflare preview.

### #20 — Infra: Supabase dev project
**Build:** the dev data backbone.
**Done when:**
- A Supabase **dev** project with Postgres + Auth + Storage + **pgvector** enabled.
- Connection variable **names** added to `.env.example` (no real secrets committed).
- A short "how to connect" note + a cron-ping reminder (free projects pause after 7 days idle).

## 7. Definition of done (every PR)

Small + focused (one issue) · tests pass (CI green) · UI follows `docs/09` · no committed secrets · no LLM-produced numbers · **you pulled before committing**.

Questions → drop them on the issue, or ping Bifola. Welcome aboard. 🚀
