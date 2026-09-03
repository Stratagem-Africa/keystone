"""Tests for the operational API-cost meter (keystone.cost_meter).

Covers the money invariants (integer µUSD, round-half-up not banker's), honest
handling of $0 / unknown / missing-usage, the prime-directive boundary (the meter
never touches a product number; the stub path records nothing), and end-to-end
usage capture through the OpenAI-compatible transport with a faked HTTP response.
"""
import json
import unittest
from unittest import mock

from keystone.cost_meter import BudgetExceededError, CostMeter, anthropic_usage, openai_usage
from keystone.council import make_council
from keystone.llm import OpenAICompatibleLLM, make_llm
from keystone.rate_limit import RateLimiter
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
        s = m.summary()
        self.assertIn("not fully priceable", s)                  # never a precise fake $0
        self.assertNotIn("$0.0000", s)
        self.assertIn("unpriced", s)

    def test_unknown_does_not_swallow_priced_shows_floor(self):
        m = CostMeter()
        m.record("openrouter", "moonshotai/kimi-k3", 1000, 0)    # 3000 µUSD
        m.record("openai", "gpt-4o", 1000, 1000)                 # unknown → 0
        self.assertEqual(m.total_micro_usd(), 3000)
        self.assertEqual(m.unpriced_models, {"gpt-4o"})
        s = m.summary()
        self.assertIn("≥ $", s)                                  # a floor, not a complete total…
        self.assertIn("PARTIAL", s)
        self.assertIn("unpriced", s)

    def test_default_claude_haiku_is_priced(self):
        # The default council model (.env.example) must price honestly, not read as $0.
        m = CostMeter()
        m.record("claude", "claude-haiku-4-5-20251001", 1_000_000, 500_000)  # $1/M in, $5/M out
        self.assertEqual(m.total_micro_usd(), 1_000_000 + 2_500_000)         # $3.50
        self.assertEqual(m.unpriced_models, set())
        self.assertIn("≈ $3.5000", m.summary())

    def test_qwen_models_are_priced(self):
        # Qwen (Alibaba) fallback-provider models must price honestly like Kimi's, not
        # read as "unknown" the moment someone swaps COUNCIL_MODEL to a Qwen slug.
        m = CostMeter()
        # qwen3-coder = 300,000 µUSD/M in · 1,000,000 µUSD/M out
        m.record("openrouter", "qwen/qwen3-coder", 1_000_000, 500_000)
        self.assertEqual(m.total_micro_usd(), 300_000 + 500_000)
        self.assertEqual(m.unpriced_models, set())

    def test_qwen_free_slug_would_still_be_honest_zero_if_one_existed(self):
        # No ':free' Qwen slug exists on OpenRouter as of this snapshot (verified against
        # the live model list) — but the generic ':free' suffix rule already covers one
        # the moment it does, same as any other vendor's free tier.
        m = CostMeter()
        m.record("openrouter", "qwen/qwen3-30b-a3b:free", 5000, 5000)
        self.assertEqual(m.total_micro_usd(), 0)
        self.assertEqual(m.unpriced_models, set())


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


class TestBudgetGuard(unittest.TestCase):
    """check_budget() — the pre-flight spend cap, distinct from record()'s after-the-fact tally."""

    def test_uncapped_meter_never_raises(self):
        m = CostMeter()   # max_micro_usd unset — the existing, backward-compatible default
        m.record("openrouter", "moonshotai/kimi-k3", 10_000_000, 10_000_000)  # plenty of $ spent
        m.check_budget()   # must not raise — no cap configured

    def test_raises_once_total_reaches_cap(self):
        m = CostMeter(max_micro_usd=3000)
        m.record("openrouter", "moonshotai/kimi-k3", 1000, 0)   # exactly 3000 µUSD
        with self.assertRaises(BudgetExceededError):
            m.check_budget()

    def test_does_not_raise_below_cap(self):
        m = CostMeter(max_micro_usd=5000)
        m.record("openrouter", "moonshotai/kimi-k3", 1000, 0)   # 3000 µUSD, under the 5000 cap
        m.check_budget()   # must not raise

    def test_unpriced_calls_are_invisible_to_the_cap(self):
        # Documented caveat: check_budget() can only see PRICED spend (total_micro_usd()
        # excludes unpriced models), so a cap is only a real backstop when the model in use
        # has a known price — confirmed here rather than just asserted in a comment.
        m = CostMeter(max_micro_usd=1)
        m.record("openai", "gpt-4o", 1_000_000, 1_000_000)   # no cited price -> $0 counted
        m.check_budget()   # does not raise, even though real spend may be nonzero


class TestBudgetAndRateLimitWiredIntoTransport(unittest.TestCase):
    """The guards must actually run inside complete(), not just exist as standalone methods."""

    def test_over_budget_blocks_the_call_before_any_http_request(self):
        m = CostMeter(max_micro_usd=1)
        m.record("openrouter", "moonshotai/kimi-k3", 1000, 0)  # already over the 1 µUSD cap
        llm = OpenAICompatibleLLM("moonshotai/kimi-k3", base_url="https://example.test",
                                  api_key_env=None, meter=m, provider="openrouter")
        with mock.patch("urllib.request.urlopen") as fake_urlopen:
            with self.assertRaises(BudgetExceededError):
                llm.complete(label="t", system="s", user="u", max_tokens=16)
        fake_urlopen.assert_not_called()   # the cap must stop the call, not just log after it

    def test_rate_limiter_acquire_is_called_before_the_http_request(self):
        fake_limiter = mock.Mock(spec=RateLimiter)
        llm = OpenAICompatibleLLM("moonshotai/kimi-k3", base_url="https://example.test",
                                  api_key_env=None, rate_limiter=fake_limiter, provider="openrouter")
        payload = {"choices": [{"message": {"content": "hi"}}], "usage": {}}
        with mock.patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
            llm.complete(label="t", system="s", user="u", max_tokens=16)
        fake_limiter.acquire.assert_called_once()

    def test_default_rate_limiter_is_configured_from_env(self):
        with mock.patch.dict("os.environ", {"LLM_MAX_REQUESTS_PER_MINUTE": "7"}):
            llm = OpenAICompatibleLLM("moonshotai/kimi-k3", base_url="https://example.test",
                                      api_key_env=None, provider="openrouter")
        self.assertEqual(llm._rate_limiter._max_calls, 7)


if __name__ == "__main__":
    unittest.main()
