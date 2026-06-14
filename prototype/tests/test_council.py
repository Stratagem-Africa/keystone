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
import unittest
from unittest import mock

from keystone.blueprints import url_shortener
from keystone.council import make_council, DeterministicStubCouncil
from keystone.claude_council import (
    ClaudeCouncil, CouncilError, _REDACTION, _extract_json, _redact_engine_metrics,
)

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
        with self.assertRaises(ValueError):
            make_council("openrouter")

    def test_claude_provider_with_injected_client(self):
        council = make_council("claude", model="test-model", client=FakeLLM())
        self.assertIsInstance(council, ClaudeCouncil)


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


if __name__ == "__main__":
    unittest.main()
