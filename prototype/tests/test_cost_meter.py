"""Tests for the operational API-cost meter (keystone.cost_meter).

Covers the money invariants (integer µUSD, round-half-up not banker's), honest
handling of $0 / unknown / missing-usage, the prime-directive boundary (the meter
never touches a product number; the stub path records nothing), and end-to-end
usage capture through the OpenAI-compatible transport with a faked HTTP response.
"""
import json
import unittest
from unittest import mock

from keystone.cost_meter import CostMeter, anthropic_usage, openai_usage
from keystone.council import make_council
from keystone.llm import OpenAICompatibleLLM, make_llm
from keystone.blueprints import url_shortener


class TestCostMeterMath(unittest.TestCase):
    def test_known_model_exact_micro_usd(self):
        m = CostMeter()
        # kimi-k3 = 3,000,000 µUSD/M in · 15,000,000 µUSD/M out
        m.record("openrouter", "moonshotai/kimi-k3", 43210, 8905)
        # in: 43210*3 = 129,630 ; out: 8905*15 = 133,575
        self.assertEqual(m.total_micro_usd(), 129_630 + 133_575)
        self.assertIsInstance(m.total_micro_usd(), int)

    def test_round_half_up_not_bankers(self):
        m = CostMeter()
        # kimi-k2.5 input = 375,000 µUSD/M → 12 tokens = 4.5 µUSD → half-up = 5 (banker's would give 4)
        m.record("openrouter", "moonshotai/kimi-k2.5", 12, 0)
        self.assertEqual(m.total_micro_usd(), 5)

    def test_sub_micro_rounds_to_zero(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k2.5", 1, 0)  # 0.375 µUSD → 0
        self.assertEqual(m.total_micro_usd(), 0)

    def test_money_total_is_integer(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", 1_000_000, 1_000_000)
        self.assertEqual(m.total_micro_usd(), 3_000_000 + 15_000_000)  # $18.00
        self.assertIsInstance(m.total_micro_usd(), int)


class TestHonestZeroAndUnknown(unittest.TestCase):
    def test_free_providers_are_known_zero_not_unknown(self):
        m = CostMeter()
        m.record("ollama", "qwen2.5:7b", 5000, 5000)              # local
        m.record("github", "openai/gpt-4o-mini", 5000, 5000)     # GitHub Models free tier
        m.record("openrouter", "meta-llama/llama-3.3-70b-instruct:free", 5000, 5000)  # :free slug
        self.assertEqual(m.total_micro_usd(), 0)
        self.assertEqual(m.unpriced_models, set())               # $0, NOT "unknown"

    def test_unknown_model_flagged_not_faked_zero(self):
        m = CostMeter()
        m.record("openai", "gpt-4o", 1000, 1000)                 # no cited price → unknown
        self.assertEqual(m.total_micro_usd(), 0)                 # excluded from the total…
        self.assertEqual(m.unpriced_models, {"gpt-4o"})          # …but surfaced, not hidden
        self.assertIn("unpriced", m.summary())

    def test_unknown_does_not_swallow_priced(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", 1000, 0)    # 3000 µUSD
        m.record("openai", "gpt-4o", 1000, 1000)                 # unknown → 0
        self.assertEqual(m.total_micro_usd(), 3000)
        self.assertEqual(m.unpriced_models, {"gpt-4o"})


class TestMissingAndBadUsage(unittest.TestCase):
    def test_missing_usage_counted_and_safe(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", None, None)
        self.assertEqual(m.calls_missing_usage, 1)
        self.assertEqual(m.total_micro_usd(), 0)

    def test_partial_usage_is_not_missing(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", 100, None)  # input present
        self.assertEqual(m.calls_missing_usage, 0)
        self.assertEqual(m.total_micro_usd(), 300)               # 100*3

    def test_bool_is_not_a_token_count(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", True, 5)    # True must NOT count as 1 token
        self.assertEqual(m.total_micro_usd(), 75)                # only 5*15 = 75


class TestSummary(unittest.TestCase):
    def test_empty_meter_reports_zero_no_calls(self):
        self.assertIn("no live LLM calls", CostMeter().summary())
        self.assertIn("$0.00", CostMeter().summary())

    def test_summary_carries_snapshot_and_tokens(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", 1000, 500)
        s = m.summary()
        self.assertIn("snapshot", s)
        self.assertIn("1,000 in / 500 out", s)


class TestUsageParsers(unittest.TestCase):
    def test_openai_usage(self):
        self.assertEqual(openai_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 20}}), (10, 20))
        self.assertEqual(openai_usage({"usage": {}}), (None, None))
        self.assertEqual(openai_usage({}), (None, None))
        self.assertEqual(openai_usage("garbage"), (None, None))

    def test_anthropic_usage(self):
        class _U:
            input_tokens, output_tokens = 7, 9

        class _R:
            usage = _U()
        self.assertEqual(anthropic_usage(_R()), (7, 9))
        self.assertEqual(anthropic_usage(object()), (None, None))


class TestWiring(unittest.TestCase):
    def test_make_llm_attaches_meter_and_provider(self):
        m = CostMeter()
        # ollama needs no API key, so this exercises the make_llm→transport wiring hermetically.
        llm = make_llm("ollama", "qwen2.5:7b", meter=m)
        self.assertIs(llm._meter, m)
        self.assertEqual(llm._provider, "ollama")

    def test_stub_council_records_nothing(self):
        # Prime-directive boundary: the stub makes no LLM calls, so the meter stays empty.
        m = CostMeter()
        council = make_council("stub", meter=m)
        council.design(url_shortener.build(system_rps=10_000, cache_hit_rate=0.90))
        self.assertEqual(len(m.calls), 0)
        self.assertIn("no live LLM calls", m.summary())


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTransportCapturesUsage(unittest.TestCase):
    def test_openai_compatible_records_usage_into_meter(self):
        m = CostMeter()
        llm = OpenAICompatibleLLM("moonshotai/kimi-k3", base_url="https://example.test",
                                  api_key_env=None, meter=m, provider="openrouter")
        payload = {"choices": [{"message": {"content": "hi"}}],
                   "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            out = llm.complete(label="t", system="s", user="u", max_tokens=16)
        self.assertEqual(out, "hi")
        self.assertEqual(len(m.calls), 1)
        # 100*3 + 50*15 = 1050 µUSD
        self.assertEqual(m.total_micro_usd(), 1050)


if __name__ == "__main__":
    unittest.main()
