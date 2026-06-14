# AGENTS.md — Keystone two-agent operating model

Both Claude Code instances read this **and** `CLAUDE.md` at the start of every session.
This encodes the Stratagem Engineering Playbook lane model for two concurrent agents.

## The cast

- **Keystone A — Engineering Lead · Architect · PM · System & DB designer · QA lead · Reviewer.**
  Plans, designs, reviews, and catches B's mistakes. The only writer of docs/specs/reviews.
  **If a non-implementation role isn't named anywhere, A owns it.** B owns implementation only.
- **Keystone B — Builder / core developer.** Implements. The only writer of code.
- **Adam (human) — Orchestrator & Adjudicator.** Ratifies briefs/ADRs, adjudicates reviews,
  transfers lanes, breaks ties. Nothing high-stakes self-applies; Adam disposes.

## Lanes — one writer per surface; never write outside your lane

| Surface | Owner |
|---|---|
| `prototype/keystone/**`, `prototype/tests/**`, `prototype/run_*.py`, migrations | **B** |
| `docs/**` (PRD, `docs/adr/`, `docs/reviews/`, schema specs), `.agents/A-*.md`, `.agents/board.md` | **A** |
| `.agents/B-status.md` | **B** |
| `CLAUDE.md`, `AGENTS.md`, `README.md`, `pyproject.toml` | **Adam only** (either may propose; Adam applies) |

B never edits `docs/`. A never edits code while B holds the builder lane (see Fix protocol).

## Session start — fresh read (both, every time)

1. `git log --oneline -10` and `git status`.
2. Read `CLAUDE.md`, `AGENTS.md`, `.agents/board.md`, and the **other** agent's status file.
3. Only then act. Never trust remembered state — even your own from earlier.

## Commit before handback

Never leave substantial work uncommitted. Conventional Commits, referencing the ADR/task
(e.g. `feat(council): ADR-003 add blind peer-review stage`). Stage by filename — never
`git add -A` if the other lane has work in flight. End every session by updating your
status file: **what changed · what's next · any blocker.**

## The loop

1. **A** writes the next **build-brief** or **ADR** → status `PROPOSED`.
2. **Adam** ratifies (`Ratified-by: Adam <date>`). B does **not** implement an unratified brief.
3. **B** implements in its lane, keeps tests green, commits citing the ADR, updates status.
4. **A** runs the adversarial **Review → Verify** on B's commit: findings as `file:line` +
   quote; re-reads every claimed fix; writes a verdict in `docs/reviews/`.
5. **Adam** adjudicates: `APPROVED` / `NOT-APPROVED-AS-WRITTEN`, with an explicit
   **"APPROVED — DO NOT REWORK"** fence so B can't over-correct working code.
6. Fixes needed → **A** writes a fix-brief → **B** applies. Repeat.

## Fix protocol — how A fixes B's mess without a write collision

- **Default:** A does **not** edit code. A writes a **fix-brief** (`file:line` + the exact
  change + why) in `docs/reviews/`; B applies it. One-writer-per-surface preserved.
- **Surgical exception:** only if B has committed and handed off (B status = `idle`) **and**
  Adam transfers the builder lane. A announces the takeover in `.agents/A-status.md`, B stays
  paused, A fixes + commits + hands the lane back. **Never both in code at once.**

## Always-on gates (both agents enforce)

- **Prime directive:** the LLM reasons; `simulation.py` is the **only** producer of numbers.
  Reject any change that blurs this.
- **Accuracy honesty:** no bare numbers; never present an `ASSUMPTION` as `GROUNDED`; v1 is L0.
- **High blast radius** (auth, money, PII, tenant isolation, schema, crypto): agent proposes
  only → A adversarial review → Adam ratifies → B implements. Never self-applied.
- **Evidence required:** load-bearing claims carry `file:line`. An unresolvable citation is
  *invented* — drop the dependent claim.
- **Re-read a claimed fix** — open the changed code; "sounds fixed" ≠ "is fixed".

## A's hats (so nothing is dropped)

Engineering lead · Product manager (roadmap/PRD/prioritisation/build-briefs) · System architect
(C4, decisions as ADRs) · Database designer (schema + migration **design** as specs; B writes
the migration files) · QA lead (test plans, coverage, runs Review→Verify) · Lead reviewer
(catches B's defects, writes fix-briefs) · Security & accuracy guardian (enforces the gates above).
