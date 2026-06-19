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


class TestReferenceModelHygiene(unittest.TestCase):
    """Structural well-formedness of every reference model — catches a malformed
    new model (bad flow shares, dangling component ref, non-positive capacity)
    before it reaches the scorer, where it would silently distort the scorecard."""

    def test_every_model_is_a_real_in_scope_blueprint(self):
        keys = {b[0] for b in corpus.in_scope()}
        for key, _build, _rps in REFERENCE_MODELS:
            self.assertIn(key, keys, f"{key!r} is not an in-scope blueprint")

    def test_registry_rps_matches_model_default(self):
        # the displayed reference rps must equal the load the model is actually built at
        for key, build, rps in REFERENCE_MODELS:
            m = build()
            self.assertEqual(m.workload.system_rps, rps,
                             f"{key}: registry rps {rps} != model rps {m.workload.system_rps}")

    def test_flow_shares_sum_to_one(self):
        for key, build, _rps in REFERENCE_MODELS:
            total = sum(f.share for f in build().flows)
            self.assertAlmostEqual(total, 1.0, places=6,
                                   msg=f"{key}: flow shares sum to {total}, not 1.0")

    def test_flow_steps_reference_real_components(self):
        for key, build, _rps in REFERENCE_MODELS:
            m = build()
            for f in m.flows:
                for step in f.path:
                    self.assertIn(step.component_id, m.components,
                                  f"{key}: flow {f.name!r} references unknown component {step.component_id!r}")

    def test_capacities_and_costs_are_sane(self):
        for key, build, _rps in REFERENCE_MODELS:
            for cid, c in build().components.items():
                self.assertGreater(c.per_instance_rps, 0, f"{key}.{cid}: non-positive capacity")
                self.assertGreaterEqual(c.instances, 1, f"{key}.{cid}: <1 instance")
                self.assertGreaterEqual(c.monthly_cost_per_instance, 0, f"{key}.{cid}: negative cost")

    def test_coverage_did_not_regress(self):
        # the expansion to 14 in-scope reference models must not silently shrink
        self.assertGreaterEqual(len(REFERENCE_MODELS), 14)


if __name__ == "__main__":
    unittest.main()
