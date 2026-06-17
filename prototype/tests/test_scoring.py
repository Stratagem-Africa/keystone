"""Tests for the engine scoring harness (docs/11, board #5).

These regression-test the SCORING METHOD and the engine's L0 properties across the
reference models — so accuracy / honesty can't silently regress. Deterministic; no LLM.
"""
from __future__ import annotations

import unittest

from keystone.benchmarks import syssimulator_blueprints as corpus
from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.benchmarks.scoring import _cost_verdict, render_scorecard, score_all


class TestCostVerdict(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(_cost_verdict(100, 50, 150), ("in-band", 1.0))
        self.assertEqual(_cost_verdict(300, 50, 150)[0], "near")   # 2× over high
        self.assertEqual(_cost_verdict(1000, 50, 150)[0], "oom")   # ~6.7× over
        self.assertEqual(_cost_verdict(5000, 50, 150)[0], "off")   # >10×
        self.assertEqual(_cost_verdict(10, 50, 150)[0], "oom")     # 50/10 = 5× under low
        # under-band factor
        v, f = _cost_verdict(25, 50, 150)
        self.assertEqual(v, "near")  # 50/25 = 2×
        self.assertAlmostEqual(f, 2.0)


class TestEngineL0Properties(unittest.TestCase):
    """Every in-scope reference model must hold the reliable L0 properties."""

    def setUp(self):
        self.cards = score_all()

    def test_one_card_per_reference_model(self):
        self.assertEqual(len(self.cards), len(REFERENCE_MODELS))

    def test_bottleneck_identified_for_all(self):
        self.assertTrue(all(c.bottleneck_ok for c in self.cards),
                        f"bottleneck not identified: {[c.name for c in self.cards if not c.bottleneck_ok]}")

    def test_breakpoint_stable_and_deterministic(self):
        self.assertTrue(all(c.breakpoint_stable for c in self.cards),
                        f"breakpoint not load-invariant: {[c.name for c in self.cards if not c.breakpoint_stable]}")
        self.assertTrue(all(c.deterministic for c in self.cards))

    def test_cost_within_order_of_magnitude(self):
        # L0 acceptance: every reference model is at least within an order of magnitude
        # of its band (in-band / near / oom — never wildly 'off').
        off = [c.name for c in self.cards if c.cost_verdict == "off"]
        self.assertEqual(off, [], f"cost wildly off-band (>10×): {off}")

    def test_majority_in_band(self):
        in_band = sum(c.cost_verdict == "in-band" for c in self.cards)
        self.assertGreaterEqual(in_band, len(self.cards) // 2 + 1,
                                "fewer than half the reference models hit their cost band")


class TestScorecardHonesty(unittest.TestCase):
    def setUp(self):
        self.md = render_scorecard(score_all())

    def test_has_where_this_is_wrong(self):
        self.assertIn("Where this is wrong", self.md)
        self.assertIn("L0 (Directional)", self.md)

    def test_states_coverage_gap(self):
        # must honestly report it scored only a subset of the in-scope corpus
        self.assertLess(len(REFERENCE_MODELS), len(corpus.in_scope()))
        self.assertIn("in-scope blueprints", self.md)
        self.assertIn("GAP", self.md)


if __name__ == "__main__":
    unittest.main()
