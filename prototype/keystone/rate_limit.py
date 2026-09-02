"""A tiny, stdlib-only request-rate limiter — a spend/runaway-loop backstop for LLM calls.

Blocks (sleeps) rather than raising: a legitimate burst just slows down instead of failing
outright, while a bug that fires far more calls than any real workflow needs gets throttled
hard. Thread-naive by design, matching `cost_meter.CostMeter`'s own note — build one per
transport instance; a single report's calls are sequential.
"""
from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    """Allows at most `max_calls` calls per rolling `period_seconds` window."""

    def __init__(self, max_calls: int, period_seconds: float = 60.0) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        self._max_calls = max_calls
        self._period = period_seconds
        self._call_times: deque[float] = deque()

    def acquire(self) -> None:
        """Block until another call is allowed within the rolling window, then record it."""
        now = time.monotonic()
        self._evict(now)
        if len(self._call_times) >= self._max_calls:
            wait = self._period - (now - self._call_times[0])
            if wait > 0:
                time.sleep(wait)
            now = time.monotonic()
            self._evict(now)
        self._call_times.append(now)

    def _evict(self, now: float) -> None:
        while self._call_times and now - self._call_times[0] >= self._period:
            self._call_times.popleft()
