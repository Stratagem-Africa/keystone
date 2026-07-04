"""Tests for the council layer — the real ClaudeCouncil, the prime-directive
guard, the provider factory, and tolerant JSON parsing.

All offline: the Claude path is driven by an injected FakeLLM, so these run green
with no API key and at $0 (CLAUDE.md cost rule). The LLM is non-deterministic in
production, so we test the ORCHESTRATION and the INVARIANTS (3 stages, source
tagging, no numbers leak), not model output.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import time
import unittest
from unittest import mock

from keystone.blueprints import url_shortener
from keystone.council import (
    make_council, DeterministicStubCouncil, ensure_high_stakes_gate,
    is_high_stakes, HIGH_STAKES_DECISION, HIGH_STAKES_AREA,
)
from keystone.claude_council import (
    ClaudeCouncil, CouncilError, _REDACTION, _as_list, _extract_json,
    _redact_engine_metrics,
)
from keystone.llm import LLMError
from keystone.report import render
from keystone.simulation import simulate

# A valid chairman reply with clean (numberless) ADRs.
_CLEAN_CHAIRMAN = json.dumps([
    {
        "area": "Datastore",
        "decision": "Single relational primary for the mapping table.",
        "rationale": "Boring, reliable default for a key->value workload.",
        "dissent": ["Data engineer: a KV store scales writes more cheaply at very high create volume."],
        "confidence": "high",
        "kill_criteria": ["Create traffic dominates the workload"],
    },
])


class FakeLLM:
    """Records every call's label and returns canned JSON per stage."""

    def __init__(self, *, chairman_json: str = _CLEAN_CHAIRMAN) -> None:
        self.calls: list[str] = []
        self._chairman_json = chairman_json

    def complete(self, *, label, system, user, max_tokens):
        self.calls.append(label)
        if label.startswith("design:"):
            return ('[{"area": "Datastore", "position": "Postgres primary", '
                    '"rationale": "boring reliable default", "risk": "write scaling"}]')
        if label.startswith("review:"):
            return '[{"target": "P1", "concern": "cache stampede risk", "severity": "high"}]'
        if label == "chairman":
            return self._chairman_json
        raise AssertionError(f"unexpected council label: {label}")


class TestFactory(unittest.TestCase):

    def test_explicit_stub_provider(self):
        self.assertIsInstance(make_council("stub"), DeterministicStubCouncil)

    def test_defaults_to_stub_with_no_env(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsInstance(make_council(), DeterministicStubCouncil)

    def test_unknown_provider_raises(self):
        # A genuinely unknown provider fails loudly (LLMError from the transport factory).
        with self.assertRaises(LLMError):
            make_council("bogus", model="m")

    def test_non_claude_provider_needs_an_explicit_model(self):
        # openrouter/gemini/groq/ollama are valid primaries now, but require COUNCIL_MODEL
        # (no sensible cross-vendor default). Cleared env → no COUNCIL_MODEL → ValueError.
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                make_council("gemini")

    def test_claude_provider_with_injected_client(self):
        council = make_council("claude", model="test-model", client=FakeLLM())
        self.assertIsInstance(council, ClaudeCouncil)

    def test_provider_agnostic_primary_with_injected_client(self):
        # ANY provider drives the REAL council when a client is injected (ADR-010 vendor-neutrality):
        # gemini/groq/openrouter/ollama all run the same 3-stage council, tagged non-stub, guard intact.
        model = url_shortener.build()
        for prov in ("gemini", "groq", "openrouter", "ollama"):
            fake = FakeLLM()
            council = make_council(prov, model="some-model", client=fake)
            self.assertIsInstance(council, ClaudeCouncil)
            adrs = council.design(model)
            self.assertTrue(adrs, f"{prov}: no ADRs")
            self.assertTrue(all(a.source != "stub" for a in adrs), f"{prov}: real council must not tag stub")


class TestClaudeCouncilOrchestration(unittest.TestCase):

    def setUp(self):
        self.model = url_shortener.build()

    def test_runs_all_three_stages(self):
        fake = FakeLLM()
        adrs = make_council("claude", model="m", client=fake).design(self.model)
        # 7 personas design + 7 personas review + 1 chairman = 15 calls.
        self.assertEqual(sum(c.startswith("design:") for c in fake.calls), 7)
        self.assertEqual(sum(c.startswith("review:") for c in fake.calls), 7)
        self.assertEqual(fake.calls.count("chairman"), 1)
        self.assertTrue(adrs)

    def test_adrs_are_tagged_claude(self):
        adrs = make_council("claude", model="m", client=FakeLLM()).design(self.model)
        self.assertTrue(all(a.source == "claude" for a in adrs))

    def test_report_banner_keys_off_source(self):
        # report.py shows the STUB banner only when adrs[0].source == "stub".
        adrs = make_council("claude", model="m", client=FakeLLM()).design(self.model)
        self.assertNotEqual(adrs[0].source, "stub")

    def test_empty_chairman_reply_raises(self):
        fake = FakeLLM(chairman_json="[]")
        with self.assertRaises(CouncilError):
            make_council("claude", model="m", client=fake).design(self.model)


class TestPrimeDirectiveGuard(unittest.TestCase):
    """The LLM must never produce a number; the guard scrubs any that leak."""

    def test_redacts_pure_metrics_with_no_residue(self):
        # Whole-string metrics must collapse to exactly the marker — no dangling
        # 'k', '/mo', or 'nth' fragment (the bug class the verification caught).
        for bad in ["50ms", "120 ms", "8000 rps", "300 qps", "2.5 seconds",
                    "300 msec", "5 secs", "$420/month", "$8k", "8k rps",
                    "1.2M rps", "8K QPS", "5k ms", "50 millis", "20 ns",
                    "100 microseconds", "€500/month", "£500 per month",
                    "$2.5k/mo", "$1,200 per month", "500 dollars", "0.5 cents"]:
            clean, n = _redact_engine_metrics(bad)
            self.assertEqual(clean, _REDACTION, f"residue left for {bad!r}: {clean!r}")
            self.assertGreaterEqual(n, 1)

    def test_redacts_metrics_embedded_in_prose(self):
        cases = {
            "p99 is 50ms": "50ms",
            "costs 500$": "500",
            "$2.5k/mo for compute": "k/mo",
            "0.5 cents per request": "0.5",
        }
        for text, leak in cases.items():
            clean, n = _redact_engine_metrics(text)
            self.assertGreaterEqual(n, 1, f"should have redacted: {text!r}")
            self.assertIn(_REDACTION, clean)
            self.assertNotIn(leak, clean, f"leak {leak!r} survived in {clean!r}")

    def test_keeps_legitimate_design_language(self):
        # Ratios, counts, percentages, region labels, TTLs, and durations are
        # design vocabulary the engine does NOT own — must pass untouched.
        for ok in ["90% of traffic is reads", "99:1 read:write ratio",
                   "shard into 4 partitions", "t4g.medium x12 instances",
                   "cache-aside on the read path", "add a read replica",
                   "90/10 read:write split", "30s TTL on the cache",
                   "deploy to 5 us-east regions", "recovery target of 5 minutes",
                   "PostgreSQL version 16"]:
            clean, n = _redact_engine_metrics(ok)
            self.assertEqual(n, 0, f"should NOT have redacted: {ok!r}")
            self.assertEqual(clean, ok)

    def test_guard_scrubs_and_flags_chairman_adr(self):
        dirty = json.dumps([{
            "area": "Caching (handles 8k rps)",        # metric in the report header
            "decision": "Cache-aside, targeting p99 under 5ms.",
            "rationale": "Shields the DB; serves 9000 rps comfortably.",
            "dissent": ["SRE: cold-cache stampede risk."],
            "confidence": "high",
            "kill_criteria": ["hit-rate below 70%", "cost exceeds $2.5k/mo"],
        }])
        adrs = make_council("claude", model="m", client=FakeLLM(chairman_json=dirty)).design(
            url_shortener.build())
        adr = adrs[0]
        # area (the section header) is scrubbed, not just the body.
        self.assertNotIn("8k rps", adr.area)
        self.assertIn(_REDACTION, adr.area)
        self.assertNotIn("5ms", adr.decision)
        self.assertNotIn("9000 rps", adr.rationale)
        self.assertIn(_REDACTION, adr.decision)
        self.assertIn("Prime-directive guard", adr.rationale)   # transparency flag fired
        # Percentage is legitimate design language and is preserved.
        self.assertIn("70%", adr.kill_criteria[0])
        # The $/month figure is scrubbed whole — no "k/mo" residue.
        self.assertNotIn("k/mo", adr.kill_criteria[1])
        self.assertNotIn("2.5", adr.kill_criteria[1])
        self.assertEqual(adr.source, "claude")

    def test_real_council_enforces_high_stakes_gate(self):
        # Doc 03 §6 MUST: the mandatory expert-review block must appear even when
        # the LLM (here, the fake chairman) does not produce one itself.
        model = url_shortener.build()
        model.domain_flags = ["high_stakes:payments"]
        adrs = make_council("claude", model="m", client=FakeLLM()).design(model)
        gates = [a for a in adrs if "review" in a.area.lower()]
        self.assertTrue(gates, "real council dropped the mandatory high-stakes review gate")
        self.assertEqual(gates[0].source, "claude")


class TestTolerantJsonParsing(unittest.TestCase):

    def test_tolerates_code_fences_and_prose(self):
        fenced = 'Sure!\n```json\n[{"a": 1}]\n```\nDone.'
        self.assertEqual(_extract_json(fenced, expect="array"), [{"a": 1}])
        prosey = 'Here is the object: {"x": 2} — hope that helps'
        self.assertEqual(_extract_json(prosey, expect="object"), {"x": 2})

    def test_tolerates_trailing_same_type_brackets(self):
        # A real LLM reply often follows the JSON with an aside containing the
        # same bracket char (a footnote [2], "[like this]"). Must not break.
        self.assertEqual(
            _extract_json('Here: [{"area":"DB"}]. Note: arrays [like this] are fine.', expect="array"),
            [{"area": "DB"}])
        self.assertEqual(
            _extract_json('[{"a":1}]\n\nCaveat: see point [2] above.', expect="array"),
            [{"a": 1}])
        self.assertEqual(
            _extract_json('Result: {"x":1}. Aside: use {braces} sparingly.', expect="object"),
            {"x": 1})

    def test_raises_on_no_json(self):
        with self.assertRaises(CouncilError):
            _extract_json("there is no json here", expect="array")


class TestStubCouncilUnchanged(unittest.TestCase):

    def test_stub_tags_source_stub(self):
        adrs = DeterministicStubCouncil().design(url_shortener.build())
        self.assertTrue(adrs)
        self.assertTrue(all(a.source == "stub" for a in adrs))

    def test_stub_high_stakes_appends_review_gate(self):
        model = url_shortener.build()
        model.domain_flags = ["high_stakes:payments"]
        adrs = DeterministicStubCouncil().design(model)
        self.assertTrue(any("review" in a.area.lower() for a in adrs))


# --------------------------------------------------------------------------- #
# ADR-001 regression tests — each FAILS on the pre-fix code (finding H3: the old
# guard tests were tautological, only feeding strings the regex already matched).
# --------------------------------------------------------------------------- #

class TestGuardClosesADR001Leaks(unittest.TestCase):
    """C2/C3: metric families the OLD unit-allowlist silently passed (n=0)."""

    LEAKS = [
        # throughput synonyms / per-minute / bare per-second / scientific (C2)
        "8000 requests/second", "8000 transactions/second", "500 reqs/sec",
        "9000 ops/sec", "450 calls per second", "12000 requests per minute",
        "5000 writes per second", "8000/s", "5e3 rps", "1.2e6 qps", "50000 IOPS",
        # data-rate / volume (C2) incl. spelled-out forms (re-verify residual leak)
        "10 GB/s", "10Gbps", "5 Gbit/s", "100 MB/s", "1.5 Mbps", "40 Mbps", "2 TB/day",
        "10 gigabit per second", "10 gigabytes per second", "500 megabytes/second", "2 terabytes/day",
        # currency word-before-number / bare cost-per-period (C2)
        "USD 500", "EUR 500", "500 EUR", "USD 5/month",
        "costs roughly 4200 per month", "budget of 4200 monthly",
        # engine-owned percentages (C3)
        "92 percent utilisation", "92% utilisation", "utilisation of 92%",
        "99.99 percent availability", "95% saturated", "availability of 99.99%",
        # engine LATENCY in s/ms is always redacted — incl. latency phrased with a
        # verb and no noun (re-verify caught a carve-out that leaked these); a config
        # duration in s/ms is over-redacted too (accepted safe direction, ADR-001 L).
        "p99 latency of 50 ms", "response time 200 ms", "cold start 2 seconds",
        "retry; served in 50ms", "After backoff the call returns in 80ms",
        "poll done; answers in 40ms", "in the steady-state window p99 is 50ms",
        "TTL of 300 seconds", "connection timeout of 30 seconds",
        # bare magnitudes adjacent to engine-output nouns (backstop)
        "throughput hit 12000", "cost of 4200 monthly", "utilisation around 92%",
        # bare engine OUTPUTS stated with a connective (re-verify: 12-char gap leaked these)
        "the breakpoint sits at roughly 9500", "throughput tops out near 8000",
        "utilisation settles at around 95", "the cost works out to about 420",
        "p95 increases by some 25%", "latency overhead of 20%",
        # spelled-out multiplier with a unit
        "2 million requests per second", "5 thousand qps", "10 million ops/sec", "3 million rps",
        # bare cost-rate per billing period
        "around 8k/mo", "8000/mo", "8k per month",
    ]

    def test_each_leak_class_redacts_and_flags(self):
        for s in self.LEAKS:
            clean, n = _redact_engine_metrics(s)
            self.assertGreaterEqual(n, 1, f"LEAK survived guard (prime-directive break): {s!r} -> {clean!r}")
            self.assertIn(_REDACTION, clean, f"no marker for {s!r}: {clean!r}")

    def test_whole_number_redacted_no_stray_digit(self):
        # Re-verify finding: a backtracking lookahead must not redact only the leading
        # digit of a multi-digit metric ("12000" -> "[marker]0").
        for s in ["throughput hit 12000", "utilisation of 9200%", "cost of 4200 monthly"]:
            clean, n = _redact_engine_metrics(s)
            self.assertGreaterEqual(n, 1)
            self.assertNotRegex(clean, r"\]\d", f"stray digit after marker (partial redaction): {clean!r}")

    def test_range_and_approx_collapse_whole_no_surviving_bound(self):
        # ADR-001 L: a range's lower bound must not survive ("50-[marker]").
        for s in ["50-100ms", "50 to 100 ms", "~50ms", "sub-50ms", "200-300 qps"]:
            clean, _ = _redact_engine_metrics(s)
            self.assertEqual(clean, _REDACTION, f"lower bound/residue survived for {s!r}: {clean!r}")

    def test_end_to_end_dirty_chairman_flags_every_field(self):
        dirty = json.dumps([{
            "area": "Throughput (10 Gbps backbone)",
            "decision": "Provision 50000 IOPS; serve 9000 requests/second.",
            "rationale": "Sustains 1.2e6 qps at 92% utilisation; cost about USD 500 per month.",
            "dissent": ["SRE: cold-cache risk."], "confidence": "high",
            "kill_criteria": ["availability below 99.9%"],
        }])
        adr = make_council("claude", model="m", client=FakeLLM(chairman_json=dirty)).design(
            url_shortener.build())[0]
        for field in (adr.area, adr.decision, adr.rationale):
            for leak in ["10 Gbps", "50000 IOPS", "9000 requests/second", "1.2e6 qps",
                         "92% utilisation", "USD 500"]:
                self.assertNotIn(leak, field, f"leak survived: {leak!r} in {field!r}")
        self.assertIn("Prime-directive guard", adr.rationale)  # transparency flag fired


class TestGuardKeepsDesignLanguage(unittest.TestCase):
    """The noun-anchored backstop must NOT corrupt legitimate design vocabulary."""

    KEEPS = [
        "90% of traffic is reads", "30% of reads", "99:1 read:write ratio",
        "90/10 read:write split", "shard into 4 partitions", "shard into 4",
        "t4g.medium x12 instances", "add a read replica", "scale to 5 replicas",
        "use 3 nodes", "deploy to 5 us-east regions", "3 availability zones",
        "30s TTL on the cache", "recovery target of 5 minutes", "PostgreSQL version 16",
        "version 16", "retain logs for 30 days", "RPO of 24 hours",
        "rotate keys every 12 months", "16 GB memory per node",
        # design counts sitting NEAR an engine-metric noun must still survive
        "reduce cost; we have 3 replicas", "to lower cost we run 5 nodes",
        "throughput aside, use 8 partitions", "the cost of running 2 regions",
        "availability needs 3 zones",
        # cache hit-rate / split are model INPUTS, not engine outputs
        "hit-rate below 70%", "cache hit rate of 90%",
        # multi-digit design counts sitting next to an engine noun must survive WHOLE
        # (re-verify: the backstop ate the leading digit -> "12 nodes" became "2 nodes")
        "cost: 12 nodes", "scale the app tier to 12 instances", "budget for 24 workers",
        "16 cache clusters",
        # design-count nouns the allow-list was missing (re-verify)
        "latency across 3 tiers", "cost of 3 brokers", "throughput across 8 queues",
        "deploy 4 gateways", "spend on 2 machines",
        # durations the guard does NOT match (bare single-letter 's', and minutes/
        # hours/days units) survive; s/ms durations are intentionally over-redacted.
        "30s TTL", "session timeout 30 minutes", "token expiry 15 minutes",
        "cache TTL of 5 minutes", "retry after 1 hour", "rotate every 90 days",
        # grouped multi-digit design counts near an engine noun survive whole
        "cost: 1,200 nodes", "sharded across 16 brokers",
        # ratio operands (re-verify: the right operand was over-redacted)
        "a 90/10 split keeps cost down", "split 70/30 to balance throughput", "latency ratio 99/1",
        # workload INPUTS (users/DAU/customers) are not engine outputs
        "cost model assumes 50000 users", "1 million users", "DAU of 50000",
        "throughput sized for 100000 customers",
        # version numbers and a bill-noun near a design count
        "PostgreSQL 14.2", "Kafka 3.6", "bill of materials for 3 services",
        "billing service runs 2 replicas",
    ]

    def test_design_language_is_preserved(self):
        for s in self.KEEPS:
            clean, n = _redact_engine_metrics(s)
            self.assertEqual(n, 0, f"OVER-REDACTED design language: {s!r} -> {clean!r}")
            self.assertEqual(clean, s)

    def test_guard_is_redos_bounded(self):
        # ADR-001 H2 + re-verify: prior code backtracked catastrophically — plain run
        # ~78s, plain-comma run ~9.4s, grouped-comma run ~9.1s@16KB. The bounded,
        # non-backtrackable _INT makes every vector roughly linear (each payload below
        # is ~8KB and runs well under 0.5s here). A regression would be many SECONDS,
        # so a 2s bound cleanly separates linear from catastrophic without flaking under
        # CI/dev load (the decimal-dense recall vector is the slowest, ~0.3-0.8s).
        payloads = [
            ("1," * 4000) + "x ms",              # plain comma run (original H2)
            ",".join(["123"] * 2666) + " rps",    # grouped-comma run (v2 regression canary)
            ("9" * 4000) + " utilisation",        # plain digit run next to a noun
            (".1" * 4000) + " ms",                # decimal-dense
        ]
        for payload in payloads:
            start = time.perf_counter()
            _redact_engine_metrics(payload)
            elapsed = time.perf_counter() - start
            self.assertLess(elapsed, 2.0,
                            f"guard too slow ({elapsed:.3f}s) on {payload[:24]!r} — ReDoS regression")


def _chairman_with_area(area):
    return json.dumps([{
        "area": area, "decision": "Use PR-based code review.",
        "rationale": "Catches defects.", "dissent": [], "confidence": "high",
        "kill_criteria": [],
    }])


class TestHighStakesGateADR001(unittest.TestCase):
    """C1: the mandatory expert-review block must be undroppable."""

    def test_review_substring_does_not_suppress_mandatory_gate(self):
        model = url_shortener.build()
        model.domain_flags = ["high_stakes:payments"]
        for area in ["Code review process", "Peer review cadence", "Security review"]:
            adrs = make_council("claude", model="m",
                                client=FakeLLM(chairman_json=_chairman_with_area(area))).design(model)
            gate = [a for a in adrs if a.decision.strip() == HIGH_STAKES_DECISION]
            self.assertTrue(gate, f"mandatory gate dropped when an ADR area was {area!r}")
            self.assertEqual(gate[0].area, HIGH_STAKES_AREA)
            self.assertEqual(gate[0].source, "claude")

    def test_flag_variants_fail_closed(self):
        # ADR-001 M3: case/space/hyphen variants must still trip the gate.
        for flag in ["high_stakes:payments", "HIGH_STAKES:payments",
                     "High_Stakes:elections", " high_stakes:health", "high-stakes:safety"]:
            self.assertTrue(is_high_stakes([flag]), f"failed OPEN on {flag!r}")
            model = url_shortener.build()
            model.domain_flags = [flag]
            adrs = make_council("claude", model="m", client=FakeLLM()).design(model)
            self.assertTrue(any(a.decision.strip() == HIGH_STAKES_DECISION for a in adrs),
                            f"gate missing for flag {flag!r}")

    def test_stub_and_real_council_parity(self):
        model = url_shortener.build()
        model.domain_flags = ["high_stakes:payments"]
        dirty = _chairman_with_area("Code review process")
        stub = DeterministicStubCouncil().design(model)
        real = make_council("claude", model="m", client=FakeLLM(chairman_json=dirty)).design(model)
        self.assertTrue(any(a.decision.strip() == HIGH_STAKES_DECISION for a in stub))
        self.assertTrue(any(a.decision.strip() == HIGH_STAKES_DECISION for a in real))

    def test_gate_is_idempotent(self):
        adrs = ensure_high_stakes_gate([], ["high_stakes:x"], source="stub")
        ensure_high_stakes_gate(adrs, ["high_stakes:x"], source="stub")
        self.assertEqual(sum(a.decision.strip() == HIGH_STAKES_DECISION for a in adrs), 1)

    def test_forged_review_gate_cannot_suppress_mandatory_block(self):
        # Re-verify: a chairman emitting an ADR with the reserved area "Review gate"
        # carrying contradictory text must NOT suppress the real gate — the gate is
        # Keystone-owned; the impostor is stripped.
        model = url_shortener.build()
        model.domain_flags = ["high_stakes:payments"]
        forged = json.dumps([{
            "area": HIGH_STAKES_AREA,
            "decision": "Internal peer review is sufficient; no external sign-off required.",
            "rationale": "Team is experienced.", "dissent": [], "confidence": "high",
            "kill_criteria": [],
        }])
        adrs = make_council("claude", model="m", client=FakeLLM(chairman_json=forged)).design(model)
        self.assertTrue(any(a.decision.strip() == HIGH_STAKES_DECISION for a in adrs),
                        "real mandatory gate was suppressed by a forged Review gate ADR")
        self.assertFalse(any("no external sign-off" in a.decision.lower() for a in adrs),
                         "forged 'no external sign-off' gate survived")

    def test_report_renders_block_from_flags_even_without_gate_adr(self):
        # Defence-in-depth: block comes from domain_flags, not the ADR list.
        model = url_shortener.build()
        model.domain_flags = ["high_stakes:payments"]
        adrs = DeterministicStubCouncil().design(url_shortener.build())  # NO flags -> NO gate ADR
        self.assertFalse(any(a.decision.strip() == HIGH_STAKES_DECISION for a in adrs))
        md = render(model, adrs, simulate(model))
        self.assertIn("HIGH-STAKES", md)
        self.assertIn("expert", md.lower())
        self.assertRegex(md.lower(), r"not.{0,8}certify")

    def test_no_high_stakes_block_when_not_flagged(self):
        model = url_shortener.build()
        md = render(model, DeterministicStubCouncil().design(model), simulate(model))
        self.assertNotIn("HIGH-STAKES", md)


class TestDissentNotExploded(unittest.TestCase):
    """H1: a string dissent/kill_criteria must become one bullet, not per-character."""

    def test_string_fields_become_single_bullet(self):
        dirty = json.dumps([{
            "area": "Datastore", "decision": "Use Postgres.", "rationale": "Reliable.",
            "dissent": "No major dissent", "confidence": "high", "kill_criteria": "none",
        }])
        adr = make_council("claude", model="m", client=FakeLLM(chairman_json=dirty)).design(
            url_shortener.build())[0]
        self.assertEqual(adr.dissent, ["No major dissent"])
        self.assertEqual(adr.kill_criteria, ["none"])

    def test_as_list_helper(self):
        self.assertEqual(_as_list("none"), ["none"])
        self.assertEqual(_as_list(["a", "b"]), ["a", "b"])
        self.assertEqual(_as_list(None), [])


class TestReportBannerHonesty(unittest.TestCase):
    """The report must not claim more than the guard can prove (ADR-001 §3)."""

    def setUp(self):
        self.model = url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)
        self.sim = simulate(self.model)

    def test_stub_banner_present_only_for_stub(self):
        stub = DeterministicStubCouncil().design(self.model)
        claude = make_council("claude", model="m", client=FakeLLM()).design(self.model)
        self.assertIn("DETERMINISTIC STUB", render(self.model, stub, self.sim))
        self.assertNotIn("DETERMINISTIC STUB", render(self.model, claude, self.sim))

    def test_banner_makes_no_absolute_guarantee(self):
        md = render(self.model, DeterministicStubCouncil().design(self.model), self.sim)
        self.assertNotIn("produced by the deterministic engine, not the LLM", md)


if __name__ == "__main__":
    unittest.main()
