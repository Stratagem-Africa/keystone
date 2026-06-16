# Contributing to Keystone

Keystone runs **trunk-based** with one rule above all:
**nothing reaches `main` or production without Bifola's review.**

## The loop
1. Branch from `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…` — short-lived.
2. Build in your lane (see [`docs/07`](docs/07-Team-and-Roadmap.md) §4). Keep tests green:
   `cd prototype && python3 -m unittest discover -s tests`.
3. Open a PR. **CI** runs the suite; **CODEOWNERS** auto-requests Bifola.
4. Bifola reviews — and may edit (inline suggestions, or push to your branch) — then
   **squash-merges**. **Do not merge your own PR. Do not push to `main`.**

## Why it's convention, not a hard lock (and how prod is still safe)
The org is on **GitHub Free**, where branch protection isn't available on private repos.
So the rule holds via:
- **CODEOWNERS** (`* @BifolaX`) → Bifola auto-requested on every PR.
- **CI** (`.github/workflows/ci.yml`) → tests must pass; visible on the PR.
- **Production is Bifola-gated** → prod deploys **only** on Bifola's manual trigger
  (`workflow_dispatch` / a release tag he controls). So even an accidental push to `main`
  never ships to users without him. *This gates the thing that matters — production — for free.*
- **Convention** → only Bifola merges to `main`.

Residual risk (accepted): on Free, an admin *can* technically push to `main`; it's not
hard-blocked. Mitigated by CI + the Bifola-gated prod deploy + the convention above.

## Gates on every change (no exceptions)
- **Prime directive:** the LLM reasons; the engine computes. No number ever comes from the LLM.
- **Accuracy honesty:** no bare numbers; never present an `ASSUMPTION` as `GROUNDED`.
- **Harm floor:** no committed secrets; uploads are untrusted input to the LLM.

See [`docs/07`](docs/07-Team-and-Roadmap.md) §5–6 and [`docs/08`](docs/08-Work-Breakdown.md) for the full plan.
