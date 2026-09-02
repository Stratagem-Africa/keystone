"""Tests for keystone.rate_limit.RateLimiter — the LLM-call spend/runaway-loop backstop.

Uses a tiny period_seconds (never real minutes) so the whole file stays fast.
"""
import time
import unittest

from keystone.rate_limit import RateLimiter


class TestRateLimiterConstruction(unittest.TestCase):
    def test_rejects_non_positive_max_calls(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_calls=0)
        with self.assertRaises(ValueError):
            RateLimiter(max_calls=-1)

    def test_rejects_non_positive_period(self):
        with self.assertRaises(ValueError):
            RateLimiter(max_calls=5, period_seconds=0)
        with self.assertRaises(ValueError):
            RateLimiter(max_calls=5, period_seconds=-1)


class TestRateLimiterBehavior(unittest.TestCase):
    def test_calls_within_the_cap_do_not_block(self):
        limiter = RateLimiter(max_calls=5, period_seconds=60.0)  # generous — should never sleep
        start = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        self.assertLess(time.monotonic() - start, 0.5)   # effectively instant

    def test_exceeding_the_cap_blocks_until_the_window_clears(self):
        period = 0.15
        limiter = RateLimiter(max_calls=2, period_seconds=period)
        start = time.monotonic()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()   # third call within the window — must wait out the period
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, period * 0.9)   # small tolerance for scheduling jitter

    def test_calls_after_the_window_expires_do_not_wait(self):
        period = 0.05
        limiter = RateLimiter(max_calls=1, period_seconds=period)
        limiter.acquire()
        time.sleep(period * 2)   # let the window fully clear
        start = time.monotonic()
        limiter.acquire()
        self.assertLess(time.monotonic() - start, 0.05)   # no wait needed — window already clear


if __name__ == "__main__":
    unittest.main()
