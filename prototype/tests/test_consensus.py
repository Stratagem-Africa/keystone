"""Multi-model consensus (ADR-010) — the cross-vendor consensus layer + the OpenAI-compatible transport.

All offline / $0: the primary is the deterministic stub and the voters are injected fake LLMs, so no
network/key is touched. Locks the trust-critical guarantees: every voter's free text is scrubbed by the
prime-directive guard (no model can leak a number), a flaky voter never kills the design, and the
single-model path is unchanged.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from keystone.blueprints import url_shortener
from keystone.consensus import ConsensusCouncil, Voter, make_consensus_council
from keystone.council import make_council
from keystone.llm import LLMError, OpenAICompatibleLLM, make_llm
from keystone.report import render
from keystone.simulation import simulate


class _FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    def complete(self, *, label, system, user, max_tokens):
        self.calls += 1
        return self.reply


def _stub_primary():
    return make_council("stub")


class TestConsensusCouncil(unittest.TestCase):
    def setUp(self):
        self.model = url_shortener.build()
        self.adrs = _stub_primary().design(self.model)   # 3 stub ADRs (Datastore/Caching/Resilience)

    def test_votes_annotate_each_adr_with_a_summary_and_per_model_lines(self):
        v1 = Voter("openai gpt-5-mini", _FakeLLM('[{"index":1,"verdict":"AGREE","reason":"sound"}]'))
        v2 = Voter("ollama llama3", _FakeLLM('[{"index":1,"verdict":"DISAGREE","reason":"too risky"}]'))
        adrs = ConsensusCouncil(_stub_primary(), [v1, v2]).design(self.model)
        self.assertEqual(len(adrs), len(self.adrs))
        c = adrs[0].consensus
        self.assertEqual(c[0], "Cross-model consensus: 1/2 models agree (dissent recorded)")
        self.assertIn("openai gpt-5-mini: AGREE — sound", c)
        self.assertIn("ollama llama3: DISAGREE — too risky", c)

    def test_prime_directive_guard_scrubs_numbers_in_votes(self):
        # A voter that leaks an engine-owned figure must have it redacted before it reaches the ADR.
        v = Voter("gpt", _FakeLLM('[{"index":1,"verdict":"DISAGREE","reason":"the db at 8000 rps saturates"}]'))
        adrs = ConsensusCouncil(_stub_primary(), [v]).design(self.model)
        joined = " ".join(adrs[0].consensus)
        self.assertNotIn("8000 rps", joined)
        self.assertIn("[engine-owned metric removed]", joined)

    def test_full_agreement_summary_has_no_dissent_tail(self):
        v1 = Voter("a", _FakeLLM('[{"index":1,"verdict":"AGREE","reason":"yes"}]'))
        v2 = Voter("b", _FakeLLM('[{"index":1,"verdict":"AGREE","reason":"agreed"}]'))
        adrs = ConsensusCouncil(_stub_primary(), [v1, v2]).design(self.model)
        self.assertEqual(adrs[0].consensus[0], "Cross-model consensus: 2/2 models agree")

    def test_flaky_voter_is_skipped_not_fatal(self):
        class _Boom:
            def complete(self, **k):
                raise RuntimeError("provider down")
        good = Voter("good", _FakeLLM('[{"index":1,"verdict":"AGREE","reason":"ok"}]'))
        adrs = ConsensusCouncil(_stub_primary(), [Voter("flaky", _Boom()), good]).design(self.model)
        self.assertEqual(len(adrs), len(self.adrs))           # design still produced
        self.assertIn("good: AGREE — ok", adrs[0].consensus)  # the working voter still counted
        self.assertTrue(adrs[0].consensus[0].endswith("1/1 models agree"))  # only the live voter tallied

    def test_no_voters_is_a_passthrough(self):
        adrs = ConsensusCouncil(_stub_primary(), []).design(self.model)
        self.assertTrue(all(not a.consensus for a in adrs))   # single-model path unchanged

    def test_bad_verdict_defaults_to_caveat_and_nondict_items_skipped(self):
        v = Voter("x", _FakeLLM('["junk", {"index":1,"verdict":"MAYBE","reason":"unsure"}]'))
        adrs = ConsensusCouncil(_stub_primary(), [v]).design(self.model)
        self.assertIn("x: CAVEAT — unsure", adrs[0].consensus)

    def test_report_renders_the_consensus_section(self):
        v = Voter("openai gpt", _FakeLLM('[{"index":1,"verdict":"AGREE","reason":"sound"}]'))
        adrs = ConsensusCouncil(_stub_primary(), [v]).design(self.model)
        md = render(self.model, adrs, simulate(self.model))
        self.assertIn("**Cross-model consensus:**", md)
        self.assertIn("openai gpt: AGREE", md)

    def test_make_consensus_council_with_injected_voters(self):
        cc = make_consensus_council(primary=_stub_primary(),
                                    voters=[Voter("v", _FakeLLM('[{"index":1,"verdict":"AGREE","reason":"k"}]'))])
        self.assertIsInstance(cc, ConsensusCouncil)
        self.assertTrue(cc.design(self.model)[0].consensus)


class TestOpenAICompatibleTransport(unittest.TestCase):
    def test_complete_builds_request_and_parses_content(self):
        llm = OpenAICompatibleLLM("gpt-x", base_url="https://api.openai.com/v1", api_key_env=None)
        captured = {}

        class _Resp:
            def __enter__(self_): return self_
            def __exit__(self_, *a): return False
            def read(self_): return json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()

        def _fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            return _Resp()

        with mock.patch("keystone.llm.urllib.request.urlopen", _fake_urlopen):
            out = llm.complete(label="t", system="sys", user="usr", max_tokens=42)
        self.assertEqual(out, "hi")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(captured["body"]["model"], "gpt-x")
        self.assertEqual(captured["body"]["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(captured["body"]["messages"][1], {"role": "user", "content": "usr"})

    def test_bad_response_shape_fails_loud(self):
        llm = OpenAICompatibleLLM("m", base_url="http://x/v1", api_key_env=None)

        class _Resp:
            def __enter__(self_): return self_
            def __exit__(self_, *a): return False
            def read(self_): return b'{"unexpected": true}'

        with mock.patch("keystone.llm.urllib.request.urlopen", lambda *a, **k: _Resp()):
            with self.assertRaises(LLMError):
                llm.complete(label="t", system="s", user="u", max_tokens=1)

    def test_make_llm_factory(self):
        self.assertIsInstance(make_llm("ollama", "llama3"), OpenAICompatibleLLM)   # local, no key
        with self.assertRaises(LLMError):
            make_llm("bogus", "m")
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("OPENAI_API_KEY", None)
            with self.assertRaises(LLMError):                                       # hosted provider needs a key
                make_llm("openai", "gpt-5-mini")


if __name__ == "__main__":
    unittest.main()
