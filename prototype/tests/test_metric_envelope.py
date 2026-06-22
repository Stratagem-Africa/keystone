"""ADR-007 — the output `Metric` envelope + its prime-directive invariant.

The load-bearing test is `test_only_engine_constructs_metric`: a `Metric` (a self-describing
output number) may be built ONLY by `simulation.py`. The council / report / ingestion / KB may
read one, never author one — that IS the prime directive ("the engine is the sole producer of
numbers"), enforced structurally rather than by goodwill.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import pathlib
import unittest

from keystone import simulation
from keystone.blueprints import url_shortener
from keystone.simulation import Metric, simulate

_KEYSTONE = pathlib.Path(simulation.__file__).parent


class TestMetricEnvelope(unittest.TestCase):

    def test_only_engine_constructs_metric(self):
        # Scan the package: the `Metric(` constructor may appear ONLY in simulation.py.
        offenders = []
        for p in sorted(_KEYSTONE.rglob("*.py")):
            if p.name == "simulation.py":
                continue
            if "Metric(" in p.read_text(encoding="utf-8"):
                offenders.append(str(p.relative_to(_KEYSTONE)))
        self.assertEqual(
            offenders, [],
            f"Metric constructed outside simulation.py: {offenders} — prime-directive breach "
            "(only the deterministic engine may author a number).")

    def test_metric_validation(self):
        Metric(1.0, "ms", "model", "conf")             # ok
        Metric(float("inf"), "rps", "unbounded", "c")  # inf is a legitimate 'unbounded' result
        Metric(5.0, "ms", "m", "c", low=4.0, high=6.0)  # an earned, bracketing band is allowed
        with self.assertRaises(ValueError):
            Metric(float("nan"), "ms", "m", "c")        # NaN forbidden
        with self.assertRaises(ValueError):
            Metric(1.0, "ms", "   ", "c")               # model (the formula) is required
        with self.assertRaises(ValueError):
            Metric(1.0, "ms", "m", "c", low=0.5)        # half a band
        with self.assertRaises(ValueError):
            Metric(5.0, "ms", "m", "c", low=1.0, high=2.0)  # band must bracket value (no fabrication)

    def test_metric_is_frozen(self):
        m = Metric(1.0, "ms", "model", "conf")
        with self.assertRaises(Exception):
            m.value = 2.0  # frozen — a consumer cannot mutate a number

    def test_simulate_populates_envelope_consistently(self):
        sim = simulate(url_shortener.build())
        for key in ("bottleneck_utilization", "breakpoint_rps_safe", "p99_ms", "monthly_cost"):
            self.assertIn(key, sim.metrics)
            m = sim.metrics[key]
            self.assertTrue(m.model.strip())   # carries the formula that produced it
            self.assertIsNone(m.low)           # no fabricated numeric band at L0
            self.assertIsNone(m.high)
        # the envelope value must equal the flat field (one source of truth — the engine)
        self.assertEqual(sim.metrics["p99_ms"].value, sim.p99_ms)
        self.assertEqual(sim.metrics["monthly_cost"].value, sim.monthly_cost)
        self.assertEqual(sim.metrics["breakpoint_rps_safe"].value, sim.breakpoint_rps_safe)
        self.assertFalse(math.isnan(sim.metrics["bottleneck_utilization"].value))


if __name__ == "__main__":
    unittest.main()
