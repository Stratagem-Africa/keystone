# ADR-001 — Real Consensus Council (ratification + Review→Verify outcome)

**Status:** Accepted · **Ratified-by:** Bifola, 2026-06-17
**Date:** 2026-06-17 · **Owner:** Keystone A (Bifola)
**Relates to:** `docs/02` §4 (council), `docs/03` §2 (prime directive) & §6 (trust guardrails), `docs/04` F4, `docs/07` §3, CLAUDE.md (prime directive, accuracy honesty, Tier-1 harm floor)
**Reviews:** commit `5650ab0` (`feat(council): real Claude consensus council`) — `prototype/keystone/claude_council.py`, `council.py`, `report.py`, `tests/test_council.py`
**Method:** adversarial Review→Verify, 8 dimensions × per-finding empirical verification × completeness critic (46 agents). Every finding below was reproduced in code, not asserted.

---

## Context

Brief #1 built a real Claude council (`ClaudeCouncil`) behind the existing `Council` interface — three stages (independent design → blind peer review → chairman synthesis), one Claude model wearing 7 persona system-prompts (Doc 02 §4 cost control), emitting ADRs with dissent/confidence/kill-criteria (Doc 04 F4). It was built **ahead of the A/B loop on Adam's direct instruction**; this ADR is the formal architectural ratification and the record of the Review→Verify that CLAUDE.md mandates for any change touching the trust core.

The council sits on the product's **prime directive**: *the LLM reasons; the deterministic engine computes — no number ever originates from a language model* (Doc 03 §2). It is defended in two layers: a prompt-level rule (`_NO_NUMBERS_RULE`) forbidding figures, and a defence-in-depth output guard (`_redact_engine_metrics`) that scrubs any figure that leaks before it reaches a report. The high-stakes review gate (Doc 03 §6) is a hard MUST: flagged domains (payments/elections/health/safety) must always carry a mandatory expert-review block.

**Current exposure:** the real council is **stubbed by default** (`COUNCIL_PROVIDER=stub`) and wired to **no user-facing path** (no API, no frontend yet). There is therefore **no live user exposure today**. The findings below are *blocking-before-activation*, not a production incident.

## What the Review→Verify found

Three confirmed breaks of a prime-directive / Doc 03 §6 MUST, each reproduced end-to-end, **all invisible to the 25 green tests** (the tests exercise only inputs the code already handles):

| ID | Severity | Finding | Location |
|----|----------|---------|----------|
| **C1** | CRITICAL | The **mandatory high-stakes expert-review block is silently dropped** whenever any chairman ADR area merely *contains the substring* `"review"` (e.g. "Code review process", "Peer review cadence"). A payments/health report then ships with no expert-review block and no "does not certify" language — the exact "imply production-safe" outcome Doc 03 §6 forbids. Confirmed across 5 dimensions; severity raised to critical by every verifier. | `claude_council.py:273-275` |
| **C2** | CRITICAL | **Whole metric families bypass the guard and render verbatim** under the report's "every number is from the engine" banner, with no transparency flag (hit count stays 0): throughput synonyms (`8000 requests/second`, `transactions/second`, `reqs/sec`), per-minute rates, data-rate/volume (`GB/s`, `Gbps`, `Mbps`, `IOPS`, `TB/day`, `50 GB`), bare per-second (`8000/s`), scientific notation (`5e3 rps`), word-before-number currency (`USD 500`), bare cost-per-period (`4200 per month`). | `claude_council.py:146-155` |
| **C3** | CRITICAL | **Engine-owned percentages leak** — the guard whitelists every `%` to preserve design ratios, but utilisation/availability/saturation/hit-rate are engine-owned and rendered as `%` in `report.py:33,50`. `92 percent utilisation`, `99.99 percent availability` pass with hit count 0. | `claude_council.py:135-155` |

C2 and C3 share one root truth (named by the completeness critic): **an allowlist of unit spellings can never be complete.** A consequence is that `report.py`'s absolute banner — *"Every number below is produced by the deterministic engine, not the LLM"* — currently over-claims what the guard can prove.

Confirmed high/medium-severity findings:

| ID | Severity | Finding | Location |
|----|----------|---------|----------|
| **H1** | HIGH | If the chairman returns `dissent`/`kill_criteria` as a JSON **string** (common deviation, e.g. `"none"`), the list comprehension iterates its **characters**, rendering per-character bullets (`- n / - o / - n / - e`) in the "Recorded dissent" section — corrupting a Doc 03 §6 trust surface ("never hide dissent"). | `claude_council.py:387,389` |
| **H2** | HIGH | **ReDoS** in `_NUM`: catastrophic backtracking on a long digit/comma run (~9.4 s on `'1,'×4000`; superlinear). Untrusted-doc text echoed into an ADR field can stall report generation. Bounded by `max_tokens` (seconds, not unbounded), trivial fix (`\d{1,3}(?:,\d{3})*` → ~1 ms). *(The completeness critic flagged this a false positive with no evidence; two independent verifiers reproduced it with timings and a verified fix — the empirics stand.)* | `claude_council.py:146` |
| **H3** | HIGH | The guard's redaction tests are **tautological** — they only feed strings the regex already matches, so the suite cannot fail when the guard misses a real number (C2/C3). The single most important invariant has no test that can catch its violation. | `tests/test_council.py:105-128` |
| **M1** | MED | **No prompt-injection framing** on the untrusted path: `_model_brief` interpolates model-derived (ultimately upload-derived) text verbatim into prompts (Doc 02 §6 MUST, Overlay G). *Latent* — the untrusted source (ingestion) does not exist yet; the model is hand-built today. GAP owned by the ingestion layer. | `claude_council.py:207-225` |
| **M2** | MED | `_extract_json` returns a leading prose bracket (a valid-JSON footnote `[1]`/`[2]`) instead of the real array → the whole run aborts with a misleading "no proposals/ADRs". Fails closed (no wrong answer reaches a user) but discards a valid reply. | `claude_council.py:239-245` |
| **M3** | MED | `high_stakes` flag detection (`f.startswith("high_stakes")`) fails **open** on `HIGH_STAKES:`, ` high_stakes:`, `high-stakes:`. *Latent* — only the canonical lowercase token exists today; becomes live with ingestion. Cheap fix. | `claude_council.py:273` |

Low-severity items (range/approximation lower-bound leaks, spelled-out numbers, zero-review stage runs silently, `_extract_json` wrapped-object shapes, `max_tokens` truncation surfaces as a generic error, confidence enum silently defaults to `med`, no timeout/retry config, `report.render` never tested) are folded into the fix brief as GAPs.

## Decision

1. **Ratify the council architecture.** The 3-stage / 7-persona / one-model design, the ADR schema (decision + named dissent + confidence + kill criteria), the lazy optional-SDK transport, the env-driven `make_council()` factory, and the stub default all conform to Doc 02 §4 and Doc 04 F4 and are **accepted as the design**. The defects below are implementation bugs in the guard and gate, not architecture flaws.

2. **Activation is conditional (MUST).** `COUNCIL_PROVIDER` stays `stub` by default. The `claude` provider **must not be wired to any user-facing path until the BLOCKING fixes (C1, C2, C3, banner, H1, H2) land with green regression tests that fail before the fix and pass after.** No hotfix is required (stub default, no live path), but activation is gated.

3. **Prime-directive guard policy = Hybrid (resolves B open item #2).** Keep **redact-and-flag** (never raise — raising would crash the loop on benign output and over-fail). Then:
   - **Widen the allowlist** for precision: throughput synonyms (`requests`/`transactions`/`ops`/`calls` per second; `/sec`, `/second`), per-minute rates, data-rate/volume (`GB/s`, `Gbps`, `Mbps`, `IOPS`, `TB/day`), bare per-second (`N/s`), scientific notation, word/symbol-before-number currency (`USD 500`), cost-per-period anchored to cost context, ranges/approximations (`50-100ms`, `~50ms`), and **engine-bound percentages** (utilisation/availability/saturation/hit-rate/SLA `%`).
   - **Add a noun-anchored deny-by-default backstop:** flag *and* redact any numeric token adjacent to a performance/cost/capacity/latency/throughput/percentage noun even when no unit spelling matches — so a new leak class is caught-and-flagged rather than silently passing. Preserve recognised design vocabulary (`90/10`, `shard into 4`, `version 16`, `x12 instances`) via a small allow-set.
   - **Make `report.py`'s banner honest:** state what is true (numbers come from the engine; the council is constrained and scrubbed to keep figures out of its reasoning; see "where this is wrong") rather than an absolute guarantee the guard cannot back.
   - Keep `_NO_NUMBERS_RULE` as the prompt-level first line; treat the guard as the **binding** control. Fix the ReDoS (H2) as part of this rewrite. Structured-output typed-numeric stripping is recorded as a **v2 hardening lever** if the backstop proves insufficient in the field.

4. **High-stakes gate (fix C1).** De-duplicate on the gate's **own identity** — `area == "Review gate"` / `decision.startswith("REQUIRES expert/legal/security review")` — never on a substring of LLM-authored area text. Apply the identical fix to the stub (`council.py:82`). **Defence in depth:** have `report.py` render the mandatory block directly from `model.domain_flags`, so the block can never be dropped by ADR-list mutation regardless of council. Normalise `domain_flags` (`strip().lower().replace('-','_')`) so the gate **fails closed** (M3 — cheap, do now, even though the variant input source is not yet live).

5. **Dissent/kill-criteria normalisation (fix H1).** Coerce each list-typed chairman field through an `_as_list()` helper so a bare string becomes a single bullet, never per-character noise.

6. **B's remaining open items, resolved:**
   - **(1) Adaptive thinking (Opus-tier):** DEFER behind a model-capability check. Correctly omitted now (effort/adaptive is a model-tier capability); a future enhancement, not a defect.
   - **(3) `openrouter`/`ollama` providers:** factory raising `ValueError` is correct (YAGNI; documented v2 lever, Doc 02 §4). Not a defect.
   - **(4) Per-persona proposal/review text not scrubbed:** ACCEPTED. Only ADRs reach the report and the chairman's output *is* scrubbed; per-persona text never surfaces to a user. Acceptable.

7. **Prompt-injection framing (M1)** is a documented GAP **owned by the ingestion layer (Task #2 / ADR-002)**: before ingestion feeds untrusted document text into the council, `_model_brief` must wrap every model-derived field in a data envelope (untrusted-data-not-instructions framing + control-sequence neutralisation).

## Conditions of ratification — Fix brief (Brief #2 → B)

Implement behind the **unchanged `Council` interface**; A re-verifies; Bifola ratifies; only then is `claude` activation considered. Each fix must ship with a regression test that **fails on the current code and passes after** (the test gap, H3, is itself a finding).

**BLOCKING (before any `claude` activation):**
- **C1** — gate dedupe on identity, not `"review"` substring; mirror in stub; render block from `domain_flags` in `report.py`. Test: high-stakes model + chairman ADR area "Code review process" → rendered report still contains the expert-review block + "does not certify".
- **C2 + C3 + ReDoS(H2)** — rewrite the guard per Decision §3 (widen + noun-anchored backstop + bounded `_NUM`). Tests: the ~17-string leak corpus + the percentage corpus all redact and flag; the design-language allow-set is preserved (no over-redaction of `90/10`, `version 16`, `30s TTL`, `us-east`, `x12`); a 12 KB pathological digit/comma string completes < 50 ms.
- **Banner** — soften `report.py:22-23` to an honest claim.
- **H1** — `_as_list()` normalisation. Test: `"dissent": "none"` → one bullet, not four.

**NON-BLOCKING (track as GAPs):**
- **M3** flag normalisation (do alongside C1 — cheap).
- **M1** `_model_brief` data envelope — **gate to ship with the ingestion layer** (ADR-002).
- **M2** `_extract_json` type-checks the decoded value against `expect`; **L** wrapped/single-object shapes.
- **L** zero-review stage logs a warning (do **not** raise); `stop_reason` truncation diagnosis + wrap transport errors as `CouncilError` (honour the line-37 docstring); set explicit `max_retries`/`timeout`; confidence synonym map + warning (with the council eval); replace the redundant banner test with a real `report.render` end-to-end test.

## Recorded dissent (kept, not smoothed)

- **YAGNI skeptic:** the noun-anchored backstop risks over-redacting legitimate design language; a widened allowlist alone is simpler for an L0 launch. *Accepted with eyes open:* honesty/fail-closed (Doc 03) outranks precision in the trust core — a false positive degrades a number to a marker (recoverable), a false negative breaks the prime directive (unrecoverable trust loss). Mitigated by the design-vocabulary allow-set + regression tests on the benchmark corpus.
- **Completeness critic:** even the hybrid can be evaded; the only *complete* control is structured numeric output. *Accepted:* recorded as a v2 lever; for L0, hybrid + an honest banner is the truthful posture about residual risk.
- **On the build-ahead-of-loop:** the code was written before this ADR existed. *Accepted:* it sat correctly behind the unchanged interface and defaulted to stub, so no user was exposed and the formal review landed cleanly — but the three MUST-breaks confirm that trust-core code must not be *activated* ahead of Review→Verify, even when built ahead of it.

## Confidence

- **Architecture: HIGH** for the Phase-1 single-region scope.
- **Current guard/gate implementation completeness: LOW** — hence the conditional ratification.
- **Fix direction: HIGH** — every fix is anchored to a reproduced finding with a verified remedy.

## Kill criteria (revisit this ADR if…)

- Any `claude`-provider output reaches a user before the C1/C2/C3 regression tests are green → revert to stub immediately.
- A metric class leaks in the field that the noun-anchored backstop *also* misses → pull the structured-output lever early (v2 → now).
- The backstop's false-positive rate corrupts real design language across the 56-blueprint corpus → re-tune the allow-set or fall back to widen-only and log the residual gap.
- The council eval (Doc 03 §4) shows confidence miscalibration or silent dissent suppression → make dissent preservation / confidence calibration enforced gates.
- The ingestion layer (Task #2) ships before the `_model_brief` data envelope → the injection GAP goes live → block ingestion until it lands.

## Consequences

Board Task #1 moves from "built, IN-REVIEW" to **fix-brief issued (Brief #2 → B)**. B implements the blocking fixes behind the unchanged interface; A re-runs Review→Verify on the fixes; Bifola ratifies this ADR and the fixes together; only then is real-council activation considered. The default end-to-end loop is unchanged (stub). Unblocks ADR-002 to record the `_model_brief` data-envelope obligation for the ingestion layer.

## Implementation & verification (2026-06-17, branch `fix/council-trust-core`)

The BLOCKING fixes were implemented and verified through **three adversarial re-verification rounds** (each ran agents that empirically attacked the on-disk code with `python3`). The rounds earned their keep — each found real defects the previous pass introduced or missed:

- **C1 (high-stakes gate)** — gate is now **Keystone-owned** (`council.py: ensure_high_stakes_gate`): strips any ADR impersonating the reserved area/decision, then unconditionally appends the canonical gate. `report.py` also renders the block straight from `domain_flags` (defence-in-depth). Closes both the `"review"`-substring suppression and a re-verification finding that a chairman could *forge* a "Review gate" ADR carrying "no external review needed". Flags normalised (fails closed on `HIGH_STAKES:`/`high-stakes:`). **Verified undroppable/unforgeable.**
- **C2/C3 + H2 (guard)** — Hybrid guard: unit-anchored patterns (incl. spelled data-rate and spelled multipliers like "2 million rps") + a noun-anchored deny-by-default backstop keyed on engine **outputs**, with a `(?<![\d:/])`-anchored, bounded, non-backtrackable integer `(?:\d{1,3}(?:,\d{3}){1,5}|\d{1,15})(?![\d,])`. Round 2 caught a re-introduced **catastrophic ReDoS** (plain-digit run, ~78 s) and a **leading-digit-eat** (`12 nodes` → `2 nodes`); round 3 caught a **comma-branch ReDoS** (`+` → `{1,5}`) and a duration-carve-out **latency leak**. Final state: ReDoS linear on every vector (≤~250 ms at 16 KB pathological), no digit-eat, ratio operands and workload inputs preserved.
- **H1 (dissent explosion)** — `_as_list` normalisation. **Banner** softened. 42 tests green (was 25); the new tests fail on pre-fix code (non-tautological).

**A keyword carve-out for design durations was tried and removed** — it could not be made leak-safe (latency phrasing via verbs like "served in 50ms" is open-ended). So a configured duration in seconds/ms is **over-redacted** like a latency (the ADR-safe direction).

### Accepted residual leak classes (L0; prompt rule is the primary control)

A regex/heuristic guard for **bare numbers** (no unit) cannot be made complete (round-1 completeness critic). These remain and are accepted for L0, with `_NO_NUMBERS_RULE` as the first-line control and `report.py`'s honest banner:

1. A bare number separated from any engine-output noun by **>22 chars** of prose.
2. Bare single-letter **`s`** latency without a nearby latency noun ("responds in 1.2s") — bare `s` is deliberately unmatched to protect "30s TTL" / "us-east".
3. Spelled magnitudes with **neither a unit nor a noun** ("eight thousand").

**The complete fix is structured output** (the chairman emits any figure only in a typed field that is always stripped) — recorded as the **v2 lever**. Until then the council stays `stub`-gated; activation needs Bifola's ratification of these fixes.
