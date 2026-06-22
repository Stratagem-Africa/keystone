# Contributing to Keystone

Keystone runs **trunk-based** with one rule above all:
**nothing reaches `main` or production without Bifola's review.**

## The loop
1. Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…` — short-lived.
2. Build in your lane (see [`docs/07`](docs/07-Team-and-Roadmap.md) §4). Before pushing, get the
   **local gate** green: **`scripts/check.sh`** (runs the suite — zero-dependency, $0).
3. Open a PR. **CODEOWNERS** auto-requests Bifola. (GitHub Actions is **dormant** — see below — so
   there's no auto-CI check on the PR; the test signal comes from the local gate the reviewer runs.)
4. Bifola reviews — runs the gate + an adversarial Review→Verify — and leaves clear feedback for
   **you to address on your own branch** (the reviewer explains what & why; you make the fix and
   re-push). Once it's green and clean, he **squash-merges**. **Do not merge your own PR. Do not push to `main`.**

## Why it's convention, not a hard lock (and how prod is still safe)
The org is on **GitHub Free**, where branch protection isn't available on private repos —
**and GitHub Actions is currently dormant** (account billing), so CI doesn't run on PRs.
The rule holds anyway via:
- **CODEOWNERS** (`* @BifolaX`) → Bifola auto-requested on every PR.
- **Local gate** (`scripts/check.sh`) → the reviewer runs the suite (use `scripts/review-pr.sh <N>`
  to fetch + diff + check a PR in one step) before merging. The CI workflows
  (`.github/workflows/*.yml`) are kept as `workflow_dispatch` stubs so they re-enable instantly
  if Actions returns.
- **Production is Bifola-gated** → prod deploys **only** on Bifola's manual trigger
  (`workflow_dispatch` / a release tag he controls). So even an accidental push to `main`
  never ships to users without him. *This gates the thing that matters — production — for free.*
- **Convention** → only Bifola merges to `main`.

Residual risk (accepted): on Free, an admin *can* technically push to `main`; it's not
hard-blocked. Mitigated by the local gate + the Bifola-gated prod deploy + the convention above.

## Reviewer runbook (manual merge gate)
With Actions dormant, the merge gate is **manual and local** — and merging never needed Actions
anyway (`gh pr merge` is a plain git op). For each contributor PR, the reviewer (Bifola / his Claude):
1. **`scripts/review-pr.sh <PR#>`** — checks out the PR, shows the diff vs `origin/main`, runs the gate.
2. **Adversarial Review→Verify** of the diff against the gates below (prime directive, accuracy
   honesty, harm floor, correctness). Trust-critical changes (auth, money, PII, tenant isolation,
   schema, crypto, the prime-directive guard) get an independent, author-recused pass.
3. If anything needs changing, **leave clear, beginner-friendly feedback (what, why, where) and let
   the contributor fix it on their own branch** — the reviewer doesn't push fixes onto it (she's
   learning by doing). Re-check after she re-pushes.
4. On a **green gate + clean review**: `gh pr merge <PR#> --squash --delete-branch`. **Never merge on
   a failing gate; never merge your own PR; production stays a manual Bifola trigger.** (Bifola's Claude
   makes direct fixes only to the trust-critical core it owns, not to contributors' branches.)

## Gates on every change (no exceptions)
- **Prime directive:** the LLM reasons; the engine computes. No number ever comes from the LLM.
- **Accuracy honesty:** no bare numbers; never present an `ASSUMPTION` as `GROUNDED`.
- **Harm floor:** no committed secrets; uploads are untrusted input to the LLM.

## Determinism footgun checklist (engine-path code review)
The engine must be a **pure function of its inputs** — "same corpus + seed → same result" (`docs/04`). The
merge gate enforces this (`scripts/check.sh` runs the corpus twice across hash seeds; see `docs/11` §3.1),
but catch it in review too. On any change under `prototype/keystone/simulation.py` (or anything it calls),
reject these unless provably output-irrelevant:
- **Iteration over `set`/`dict` whose order can affect a result** (a sum's float order, a "first match", a
  list build) — sort first, or iterate a stable sequence.
- **`hash()`-dependent ordering** (relies on `PYTHONHASHSEED`) — the cross-process gate will fail this.
- **Unseeded nondeterminism:** `random` without a passed seed, `time`/`datetime.now`, `uuid` — none belong
  on the number path.
- **Float-reduction order** that varies run to run (parallelism, set-order sums).
- **Anything the LLM/UI/orchestration layer computes into a number** — that's a prime-directive breach, not
  just a determinism one.

See [`docs/07`](docs/07-Team-and-Roadmap.md) §5–6 and [`docs/08`](docs/08-Work-Breakdown.md) for the full plan.
