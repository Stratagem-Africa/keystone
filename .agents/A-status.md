# Keystone A (Engineering Lead / Architect / PM / QA / Reviewer) — status

**Lane state:** active
**Last changed:** 2026-06-17
**What changed this session:**
- Ran the formal adversarial Review→Verify on the real council (commit `5650ab0`): 8 dimensions,
  46 agents, every finding reproduced empirically against the code (not asserted).
- Wrote **`docs/adr/ADR-001-real-consensus-council.md`** — ratifies the council *architecture*
  (3-stage / 7-persona / one-model, Doc 02 §4 + Doc 04 F4) but **conditionally**: the `claude`
  provider stays gated to `stub` until the blocking trust-core fixes land.
- Findings: **3 CRITICAL** (C1 high-stakes gate silently droppable via a `"review"` substring;
  C2 whole metric families bypass the guard and render verbatim; C3 engine-owned percentages
  leak) + H1 (dissent string → per-character bullets) + H2 (ReDoS in `_NUM`) + H3 (guard tests
  are tautological). All invisible to the 25 green tests. **No live exposure** (stub default, no
  user-facing path) — blocking-before-activation, not an incident.
- Resolved B's 4 open items in ADR-001 (guard policy = **Hybrid**: redact-and-flag + widen +
  noun-anchored backstop + honest report banner; raise rejected).
- Issued **Fix-brief #2 → B** (board task #1b) with file:line + required regression tests.

- **Implemented Fix-brief #2** on branch `fix/council-trust-core` (ADR ratified, "do what's best"):
  C1 Keystone-owned gate (+ render-from-flags), C2/C3 Hybrid guard (bounded non-backtrackable
  integer + noun-anchored backstop + spelled multipliers/data-rate + bare cost-rate), honest
  banner, H1 `_as_list`. **3 adversarial re-verify rounds** (each found real defects: re-introduced
  ReDoS, leading-digit-eat, comma-branch ReDoS, a duration-carve-out latency leak — all fixed; the
  carve-out was removed as un-leak-safe). 42 tests green (new ones fail-before/pass-after). Residual
  bare-number leak classes documented in ADR-001 as accepted L0 (structured output = v2 lever).

- **Council fixes MERGED (#29)** — led the merge myself (Bifola delegated): independent pre-merge
  review (author recused, 4 reviewers, APPROVE/no-blockers), de-flaked the new ReDoS test, squash-
  merged to `main` (5912ee6), branch deleted, tests green on `main`. Council stays `stub`-gated.
- **Wrote ADR-002** (ingestion layer) — design + M1 injection-envelope + harm-floor secret-scan +
  the input-vs-derived boundary (ingestion carries tagged INPUTS; engine still owns all DERIVED
  metrics). Board updated (Task #1/#1b → DONE; Task #2 → RATIFIED/ready-to-build, Brief #3).

**What's next (driving autonomously):**
1. Build the ingestion layer (Brief #3) behind the `Ingestor` interface: stub + ClaudeIngestor +
   envelope + secret-scan + validation + offline tests; then adversarial Review→Verify (untrusted
   input / harm floor / prime directive) before merge. Stub-default/$0; no activation.
2. Reconciliation service (F2) is the follow-on ("Next").

**Blocker:** none. Real-council activation still needs Bifola's manual trigger + the v2 structured-output lever.
