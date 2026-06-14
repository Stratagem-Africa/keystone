# Keystone B (Builder) — status

**Lane state:** handing back (work on disk, uncommitted)
**Last changed:** 2026-06-14

**What changed — Brief #1: real Claude council** (all in B's lane, `prototype/**`):
- `keystone/claude_council.py` (new) — `ClaudeCouncil` behind the existing
  `Council` interface. Three stages (independent design → blind peer review →
  chairman synthesis), one Claude model + 7 persona system-prompts (Doc 02 §4).
  Includes `AnthropicLLM` transport (lazy SDK import), the prime-directive guard
  `_redact_engine_metrics`, tolerant JSON parsing, and a deterministic
  high-stakes review gate (Doc 03 §6 MUST).
- `keystone/council.py` — added `make_council()` factory (env-driven, defaults
  to stub, lazy `claude_council` import) + `DEFAULT_COUNCIL_MODEL`.
- `run_url_shortener.py` — wired to `make_council()`; defaults to stub, so NO
  behaviour change without `COUNCIL_PROVIDER=claude` + `ANTHROPIC_API_KEY`.
- `tests/test_council.py` (new) — offline tests (injected fake client, $0).

**Prime directive held:** the engine stays the only number producer. The council
is blocked at the prompt AND scrubbed at the output — every free-text ADR field
incl. the `area` header. 25/25 tests green; stub-mode loop output unchanged.

**Self-verification:** ran a 3-lens adversarial Review→Verify (24 agents) and
applied all 8 confirmed findings — high-stakes gate regression vs the stub,
JSON-parser fragility on a trailing same-type bracket, and guard false-negatives
(`8k rps`, `$2.5k/mo`, `millis`/`ns`, non-USD symbols, unscrubbed `area`).
Declined "minutes"/bare-`s`/bare-`us` matching (collides with TTLs / `us-east` /
cron intervals) — documented in the guard comment.

**Authorization note:** implemented on Adam's direct instruction, AHEAD of the
A/B loop (Brief #1 is still PROPOSED; ADR-001 not yet written). The code sits
behind the unchanged `Council` interface so A's ADR-001 + formal Review→Verify
and any fix-briefs land cleanly.

**For A (open items / ADR-001 should record):**
1. Adaptive thinking for Opus-tier councils — omitted now (`effort` 400s on Haiku
   4.5; adaptive is a 4.6+ mode). Enable behind a model-capability check.
2. Guard policy: redact-and-flag (current) vs fail-closed/raise on a leaked metric.
3. `openrouter` / `ollama` providers — factory raises (v2 lever, Doc 02 §4).
4. Per-persona proposal/review text is not scrubbed — only the final ADRs are
   (verifier rated low; confirm acceptable since only ADRs reach the report).

**Blocker:** none. Awaiting Adam's go to commit (and the ADR-001 number to cite).
