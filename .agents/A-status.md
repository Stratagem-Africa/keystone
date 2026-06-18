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

- **Built the ingestion layer (Brief #3)** on `feat/ingestion-layer`: `ingestion.py` (Ingestor seam,
  stub-default/$0, ClaudeIngestor) + shared `llm.py` transport (council refactored onto it, guard/gate
  untouched, 42 tests still green) + `run_from_note.py` demo + 31 ingestion tests. Adversarial
  Review→Verify (4 lenses) found **3 criticals** — secret-class gaps (Stripe/GitHub/`client_secret=`),
  markdown/free-text injection (forged GROUNDED row), NaN/inf/zero fail-open — all **fixed + locked
  with regression tests**. 73 tests green; both loops run.

- **Ingestion MERGED (#31)** — led it: Review→Verify (3 criticals fixed) → PR → merge-gate review
  (more harm-floor gaps fixed) → squash-merge. **The Phase-1 loop is now complete end-to-end**
  (intent→ingest→council→simulate→report), every LLM layer stubbed-by-default. Council fixes (#29),
  ADR-002 (#30), ingestion (#31) all on `main`. CI (Task #4) confirmed live → DONE.

- **Engine scoring (Task #5)** built on `feat/engine-scoring`: **docs/11** (scoring plan) +
  `benchmarks/scoring.py` + `reference_models.py` (5 in-scope models) + `run_scoring.py` +
  `outputs/engine_scorecard.md` + 8 tests. Scorecard: 4/5 cost in-band (URL Shortener 7× over —
  high-traffic seed model vs small-deployment band, a calibration note), 5/5 bottleneck + stable
  breakpoint + deterministic. Honest coverage: **5/34 in-scope modeled** (rest = GAP, L0→L1 path).
  82 tests green.

- **Ticket Booking (case #2, Task #6)** on `feat/ticket-booking-case2`: `blueprints/ticket_booking.py`
  (event-driven, 8 comp, in $300–1500 band) + `run_ticket_booking.py` (the **flash-sale what-if**, F6:
  bottleneck shifts app→inventory DB 667% under an 8× booking spike, breakpoint collapses) + scoring
  entry (now 6/34, ticket_booking in-band) + 6 tests. Completes CLAUDE.md's Phase-1 list (1–4). 88 tests
  green. Updated CLAUDE.md status.

- **Reviewed + merged Jem's #36** (FastAPI scaffold, issue #10) — prime-directive-clean; auth/CORS
  deferred to #20. Closed 5 resolved issues (#4/#5/#7/#25/#26); added `.claude/settings.json`
  (`gh issue` allow, #37). Wrote + ratified **ADR-004** (reconciliation, #38) and **built F2** on
  `feat/reconciliation`: `reconciliation.py` (deterministic merge; halt-on-hard-conflict; never
  auto-resolve; fail-closed) + `ingest_corpus` + `run_reconciliation.py` + 12 tests. 100 tests green.

**What's next (candidates):**
1. Reconciliation **prose-level/semantic** conflicts — the v2 LLM lever (ADR-004).
2. Canonical model store (docs/05, GH #21) — A designs spec / Jem migration; tenant-isolation MUST.
3. Grow the reference-model corpus (6/34 → more) toward L1 calibration (needs the KB).

**Coordination:** B session committed a `B-status.md` update directly to local `main` (`c7a51d7`,
unpushed) — flagged to Bifola; should be PR'd, not held local.

**Blocker:** none. Real-council & real-ingestion activation still need Bifola's manual trigger + the
council's v2 structured-output lever.
