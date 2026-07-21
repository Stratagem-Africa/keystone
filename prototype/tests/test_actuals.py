"""Tests for observed-actuals reconciliation (keystone.actuals).

Covers fail-closed parsing, the verdict logic (MATCH / soft+hard DIVERGE / NO_PREDICTION)
against the real url_shortener simulation, the prime-directive boundary (the engine result
is only read — never mutated, no Metric built), unit-mismatch honesty, calibration capture,
and deterministic rendering.
"""
import copy
import dataclasses
import unittest

from keystone.actuals import (DIVERGE, MATCH, NO_PREDICTION, Observation,
                             observed_from_records, reconcile_observed,
                             render_actuals_section)
from keystone.blueprints import url_shortener
from keystone.simulation import ComponentResult, simulate


def _sim():
    return simulate(url_shortener.build(system_rps=10_000, cache_hit_rate=0.90))


def _obs(metric, value, *, component_id=None, unit="ratio"):
    return Observation(metric=metric, value=value, unit=unit, source="src",
                          window="win", component_id=component_id)


class TestParsing(unittest.TestCase):
    def test_valid_records(self):
        recs = [{"metric": "utilization", "value": 0.7, "unit": "ratio",
                 "source": "Datadog", "window": "2026-07", "component_id": "app"}]
        out = observed_from_records(recs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].component_id, "app")
        self.assertEqual(out[0].value, 0.7)

    def test_missing_required_field_fails_closed(self):
        with self.assertRaises(ValueError):
            observed_from_records([{"metric": "utilization", "value": 0.7, "unit": "ratio",
                                    "source": "Datadog"}])  # no 'window'

    def test_non_numeric_value_rejected(self):
        with self.assertRaises(ValueError):
            observed_from_records([{"metric": "x", "value": "high", "unit": "ratio",
                                    "source": "s", "window": "w"}])

    def test_bool_value_rejected(self):
        with self.assertRaises(ValueError):
            observed_from_records([{"metric": "x", "value": True, "unit": "ratio",
                                    "source": "s", "window": "w"}])

    def test_missing_component_id_is_system_level(self):
        out = observed_from_records([{"metric": "p99_ms", "value": 100, "unit": "ms",
                                      "source": "s", "window": "w"}])
        self.assertIsNone(out[0].component_id)


class TestVerdicts(unittest.TestCase):
    def setUp(self):
        self.sim = _sim()

    def test_component_match_within_tolerance(self):
        pred = self.sim.components["app"].utilization
        out = reconcile_observed(self.sim, [_obs("utilization", pred * 1.05, component_id="app")])
        self.assertEqual(out.rows[0].verdict, MATCH)

    def test_soft_divergence(self):
        pred = self.sim.components["app"].utilization
        out = reconcile_observed(self.sim, [_obs("utilization", pred * 1.30, component_id="app")])
        self.assertEqual(out.rows[0].verdict, DIVERGE)
        self.assertEqual(out.rows[0].severity, "soft")

    def test_hard_divergence(self):
        pred = self.sim.components["cache"].utilization
        out = reconcile_observed(self.sim, [_obs("utilization", pred * 3.0, component_id="cache")])
        self.assertEqual(out.rows[0].verdict, DIVERGE)
        self.assertEqual(out.rows[0].severity, "hard")
        self.assertEqual(len(out.hard_divergences), 1)

    def test_system_metric_resolves(self):
        pred = self.sim.metrics["p99_ms"].value
        out = reconcile_observed(self.sim, [_obs("p99_ms", pred * 1.02, unit="ms")])
        self.assertEqual(out.rows[0].verdict, MATCH)
        self.assertAlmostEqual(out.rows[0].predicted, pred)

    def test_unknown_component_is_no_prediction(self):
        out = reconcile_observed(self.sim, [_obs("utilization", 0.5, component_id="ghost")])
        self.assertEqual(out.rows[0].verdict, NO_PREDICTION)
        self.assertIsNone(out.rows[0].predicted)

    def test_unmodeled_field_is_no_prediction(self):
        out = reconcile_observed(self.sim, [_obs("error_rate", 0.02, component_id="app")])
        self.assertEqual(out.rows[0].verdict, NO_PREDICTION)

    def test_unknown_system_metric_is_no_prediction(self):
        out = reconcile_observed(self.sim, [_obs("apdex", 0.9, unit="ratio")])
        self.assertEqual(out.rows[0].verdict, NO_PREDICTION)

    def test_zero_prediction_compared_absolutely(self):
        # Swap in a component whose utilisation is 0 so predicted <= 0 branch runs.
        zero = ComponentResult(id="z", name="z", arrival_rps=0.0, capacity_rps=100.0,
                               utilization=0.0, mean_latency_ms=0.0, saturated=False)
        sim0 = dataclasses.replace(self.sim, components={"z": zero})
        self.assertEqual(reconcile_observed(sim0, [_obs("utilization", 0.0, component_id="z")]).rows[0].verdict, MATCH)
        self.assertEqual(reconcile_observed(sim0, [_obs("utilization", 0.5, component_id="z")]).rows[0].verdict, DIVERGE)

    def test_unit_mismatch_is_flagged_not_converted(self):
        # utilisation supplied as "%" (72) vs engine ratio — must be flagged, never converted.
        out = reconcile_observed(self.sim, [_obs("utilization", 72, component_id="app", unit="%")])
        self.assertIn("unit", out.rows[0].note.lower())


class TestPrimeDirectiveBoundary(unittest.TestCase):
    def test_engine_result_is_not_mutated(self):
        sim = _sim()
        before = copy.deepcopy(sim)
        pred = sim.components["app"].utilization
        reconcile_observed(sim, [_obs("utilization", pred * 5, component_id="app")])
        # The engine's numbers are untouched — actuals are evidence, not corrections.
        self.assertEqual(sim.components["app"].utilization, before.components["app"].utilization)
        self.assertEqual({k: v.value for k, v in sim.metrics.items()},
                         {k: v.value for k, v in before.metrics.items()})

    def test_outcome_holds_no_metric_objects(self):
        # A PredictionVsActual carries plain floats — the module never builds a Metric.
        out = reconcile_observed(_sim(), [_obs("utilization", 0.7, component_id="app")])
        self.assertIsInstance(out.rows[0].predicted, float)
        self.assertNotIn("Metric", type(out.rows[0].predicted).__name__)

    def test_deterministic(self):
        obs = [_obs("utilization", 0.7, component_id="app"), _obs("p99_ms", 180, unit="ms")]
        a = reconcile_observed(_sim(), obs)
        b = reconcile_observed(_sim(), obs)
        self.assertEqual([(r.verdict, r.gap_ratio) for r in a.rows],
                         [(r.verdict, r.gap_ratio) for r in b.rows])


class TestCalibrationAndRender(unittest.TestCase):
    def setUp(self):
        self.sim = _sim()
        self.obs = [
            _obs("utilization", self.sim.components["app"].utilization, component_id="app"),  # match
            _obs("utilization", self.sim.components["cache"].utilization * 3, component_id="cache"),  # hard
            _obs("error_rate", 0.02, component_id="app"),  # no prediction
        ]
        self.out = reconcile_observed(self.sim, self.obs)

    def test_calibration_pairs_exclude_no_prediction(self):
        pairs = self.out.calibration_pairs()
        self.assertEqual(len(pairs), 2)  # the 2 predicted rows, not the NO_PREDICTION one
        self.assertIn("predicted", pairs[0])
        self.assertIn("observed", pairs[0])
        self.assertIn("source", pairs[0])   # provenance carried for calibration

    def test_render_contains_findings_and_boundary(self):
        md = render_actuals_section(self.out)
        self.assertIn("Model vs observed reality", md)
        self.assertIn("HARD", md)                       # hard divergence banner
        self.assertIn("Predicted", md)
        self.assertIn("Observed", md)
        self.assertIn("prime directive", md.lower())    # the boundary note
        self.assertIn("never auto-resolved", md.lower())

    def test_render_empty(self):
        self.assertIn("No observed metrics", render_actuals_section(reconcile_observed(self.sim, [])))


if __name__ == "__main__":
    unittest.main()
