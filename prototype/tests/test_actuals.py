"""Tests for observed-actuals reconciliation (keystone.actuals).

Covers fail-closed parsing, the verdict logic (MATCH / soft+hard DIVERGE / NO_PREDICTION)
against the real url_shortener simulation, the prime-directive boundary (the engine result
is only read — never mutated, no Metric built), unit-mismatch honesty, calibration capture,
and deterministic rendering.
"""
import copy
import dataclasses
import json
import os
import unittest

from keystone.actuals import (DIVERGE, MATCH, NO_PREDICTION, UNIT_MISMATCH, Observation,
                             observed_from_csv, observed_from_records, reconcile_observed,
                             render_actuals_section)
from keystone.blueprints import url_shortener
from keystone.simulation import ComponentResult, simulate

_OBSERVED_DIR = os.path.join(os.path.dirname(__file__), "..", "observed")


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

    def test_non_finite_value_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                observed_from_records([{"metric": "x", "value": bad, "unit": "ratio",
                                        "source": "s", "window": "w"}])

    def test_blank_provenance_rejected(self):
        for src, win in (("", "w"), ("s", ""), ("   ", "w"), ("s", "\t")):
            with self.assertRaises(ValueError):
                observed_from_records([{"metric": "x", "value": 1.0, "unit": "ratio",
                                        "source": src, "window": win}])

    def test_untrusted_fields_sanitised_and_bounded(self):
        [o] = observed_from_records([{"metric": "utilization", "value": 0.7, "unit": "ratio",
                                      "source": "A" * 50000, "window": "w1\nw2\t| x |",
                                      "context": "c"}])
        self.assertLessEqual(len(o.source), 200)          # length-bounded
        self.assertNotIn("\n", o.window)                  # newline collapsed
        self.assertNotIn("\t", o.window)

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

    def test_unit_mismatch_is_own_verdict_not_a_false_match(self):
        # utilisation observed as 0.70 with unit "%" (wrong) vs predicted ~0.694: raw numbers
        # are close, but the units are incomparable — must be UNIT_MISMATCH, never a false MATCH.
        out = reconcile_observed(self.sim, [_obs("utilization", 0.70, component_id="app", unit="%")])
        self.assertEqual(out.rows[0].verdict, UNIT_MISMATCH)
        self.assertIsNone(out.rows[0].gap_ratio)           # no fabricated gap
        self.assertEqual(out.matched, [])                  # excluded from matched…
        self.assertEqual(out.diverged, [])                 # …and diverged counts
        self.assertEqual(len(out.unit_mismatched), 1)

    def test_non_finite_prediction_is_no_prediction(self):
        # A saturated component (capacity 0) gives utilisation = inf in the engine; reconcile
        # must not compute a nan% gap — it routes to NO_PREDICTION.
        sat = ComponentResult(id="s", name="s", arrival_rps=10.0, capacity_rps=0.0,
                              utilization=float("inf"), mean_latency_ms=float("inf"), saturated=True)
        sim = dataclasses.replace(self.sim, components={"s": sat})
        out = reconcile_observed(sim, [_obs("utilization", 0.9, component_id="s")])
        self.assertEqual(out.rows[0].verdict, NO_PREDICTION)
        self.assertIsNone(out.rows[0].gap_ratio)


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
        self.assertIn("unit", pairs[0])     # unit carried so downstream can re-verify comparability
        self.assertIn("source", pairs[0])   # provenance carried for calibration

    def test_calibration_excludes_unit_mismatch(self):
        # A unit-mismatched row must NOT seed the calibration store (would poison the flywheel).
        out = reconcile_observed(self.sim, [
            _obs("utilization", self.sim.components["app"].utilization, component_id="app"),  # match
            _obs("utilization", 72, component_id="cache", unit="%"),                          # unit mismatch
        ])
        pairs = out.calibration_pairs()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["component_id"], "app")

    def test_render_neutralises_injection(self):
        # An untrusted field with a newline + pipes must not forge a row or a heading.
        evil = Observation(metric="utilization", value=0.7, unit="ratio",
                           source="ok\n## FAKE HEADING\n| forged | row | 0 | 0 | 0 | MATCH | x",
                           window="w", component_id="app")
        md = render_actuals_section(reconcile_observed(self.sim, [evil]))
        # The payload survives only as inert inline text in ONE cell — it must not break out
        # into a heading line or forge an extra table row.
        self.assertFalse(any(ln.lstrip().startswith("## FAKE") for ln in md.splitlines()),
                         "payload forged a heading line")
        self.assertNotIn("\n## ", md)                    # no heading at a line start but the real one
        # exactly: header + separator + 1 data row = 3 table lines (no forged extra row)
        self.assertEqual(sum(1 for ln in md.splitlines() if ln.startswith("|")), 3)

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


class TestCsvAdapter(unittest.TestCase):
    _CSV = ("component_id,metric,value,unit,source,window,context\n"
            "app,utilization,0.72,ratio,Datadog,2026-07,prod\n"
            ",p99_ms,180,ms,Datadog,2026-07,e2e\n")

    def test_parses_canonical_csv(self):
        out = observed_from_csv(self._CSV)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].component_id, "app")
        self.assertEqual(out[0].value, 0.72)          # coerced from the CSV string
        self.assertIsInstance(out[0].value, float)

    def test_blank_component_id_is_system_level(self):
        out = observed_from_csv(self._CSV)
        self.assertIsNone(out[1].component_id)         # empty component_id column → system metric

    def test_missing_required_column_fails_closed(self):
        with self.assertRaises(ValueError):
            observed_from_csv("metric,value,unit,source\napp,0.7,ratio,x\n")  # no 'window'

    def test_no_header_fails_closed(self):
        with self.assertRaises(ValueError):
            observed_from_csv("")

    def test_non_numeric_value_fails_closed(self):
        with self.assertRaises(ValueError):
            observed_from_csv("metric,value,unit,source,window\nx,high,ratio,s,w\n")

    def test_non_finite_value_fails_closed(self):
        with self.assertRaises(ValueError):
            observed_from_csv("metric,value,unit,source,window\nx,inf,ratio,s,w\n")

    def test_extra_columns_ignored(self):
        out = observed_from_csv("metric,value,unit,source,window,junk\n"
                                "utilization,0.7,ratio,s,w,ignored\n")
        self.assertEqual(len(out), 1)

    def test_header_only_is_empty(self):
        self.assertEqual(observed_from_csv("metric,value,unit,source,window\n"), [])

    def test_ragged_row_rejected_not_given_fake_provenance(self):
        # A short row → DictReader fills missing cells with None; those must NOT become the
        # string "None" and smuggle blank provenance past the fail-closed check.
        with self.assertRaises(ValueError):
            observed_from_csv("metric,value,unit,source,window\nutil,0.72,ratio\n")

    def test_csv_demo_matches_json_demo(self):
        # The committed CSV demo must yield the SAME Observations as the JSON demo.
        with open(os.path.join(_OBSERVED_DIR, "url_shortener_actuals.csv")) as f:
            from_csv = observed_from_csv(f.read())
        with open(os.path.join(_OBSERVED_DIR, "url_shortener_actuals.json")) as f:
            from_json = observed_from_records(json.load(f))
        self.assertEqual(from_csv, from_json)


class TestBoundaryGuard(unittest.TestCase):
    def test_engine_modules_do_not_import_actuals(self):
        # Structural prime-directive guard: the engine/model/pure views must never depend on the
        # actuals layer — observed evidence flows IN to be compared, never back into a number.
        # (arch_map is a pure engine view; the actuals coupling lives in audit_map, a deliverable.)
        import pathlib
        from keystone import simulation
        pkg = pathlib.Path(simulation.__file__).parent
        for name in ("simulation.py", "model.py", "report.py", "confidence_bands.py", "arch_map.py"):
            src = (pkg / name).read_text(encoding="utf-8")
            self.assertNotIn("keystone.actuals", src, f"{name} imports keystone.actuals")
            self.assertNotIn("import actuals", src, f"{name} imports actuals")


if __name__ == "__main__":
    unittest.main()
