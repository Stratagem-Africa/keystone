"""Output confidence bands (keystone/confidence_bands.py).

Locks the honesty + correctness contract: bands come ONLY from cited input uncertainty, NEVER change a
computed number (prime directive), bracket the point value, are deterministic, fail closed when nothing
is grounded, ignore RECONCILE inputs, and keep money integer (harm floor).
"""
from __future__ import annotations

import unittest

from keystone.confidence_bands import _variant, has_grounded_in_band, simulate_with_confidence
from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
from keystone.provenance import Citation, Grounding
from keystone.simulation import simulate


def _cite():
    return Citation(source="bench", reference="https://example.com/b/1")


def _grounded_model(*, cap=8000.0, g_value=None, cap_band=(6000.0, 10000.0)):
    """One-component model whose capacity (per_instance_rps) carries a grounding. The grounding's own
    value (g_value, default = cap) must sit in its band; the COMPONENT'S value (cap) may differ — when
    cap falls outside the cited band that is the RECONCILE case (in_band = False, held constant)."""
    gv = cap if g_value is None else g_value
    c = Component("app", K.APP_SERVER, "App", per_instance_rps=cap, instances=1,
                  base_latency_ms=5.0, monthly_cost_per_instance=5000,
                  groundings={"per_instance_rps": Grounding(
                      value=gv, unit="rps", confidence_low=cap_band[0], confidence_high=cap_band[1],
                      citations=[_cite()])})
    return SystemModel(name="g", components={"app": c},
                       flows=[Flow("f", 1.0, [FlowStep("app")])], workload=Workload(5000.0))


def _plain_model():
    c = Component("app", K.APP_SERVER, "App", per_instance_rps=8000.0, instances=1,
                  base_latency_ms=5.0, monthly_cost_per_instance=5000)
    return SystemModel(name="p", components={"app": c},
                       flows=[Flow("f", 1.0, [FlowStep("app")])], workload=Workload(5000.0))


class TestConfidenceBands(unittest.TestCase):
    def test_no_groundings_no_bands(self):
        # Honest fail-closed: nothing grounded → no bands (L0 point state), identical to simulate().
        m = _plain_model()
        self.assertFalse(has_grounded_in_band(m))
        r = simulate_with_confidence(m)
        self.assertTrue(all(mm.low is None and mm.high is None for mm in r.metrics.values()))

    def test_grounded_in_band_produces_bracketing_band(self):
        r = simulate_with_confidence(_grounded_model())
        banded = [k for k, mm in r.metrics.items() if mm.low is not None]
        self.assertTrue(banded, "expected at least one banded metric")
        for k in banded:
            mm = r.metrics[k]
            self.assertLessEqual(mm.low, mm.value)      # band brackets the point value (Metric guard)
            self.assertLessEqual(mm.value, mm.high)
            self.assertLess(mm.low, mm.high)            # only emitted when there is real spread

    def test_values_identical_to_plain_simulate(self):
        # PRIME DIRECTIVE: bands NEVER change a computed number — only add low/high.
        m = _grounded_model()
        plain, banded = simulate(m), simulate_with_confidence(m)
        self.assertEqual(plain.breakpoint_rps_safe, banded.breakpoint_rps_safe)
        self.assertEqual(plain.monthly_cost, banded.monthly_cost)
        self.assertEqual(plain.p99_ms, banded.p99_ms)
        for k, mm in plain.metrics.items():
            self.assertEqual(mm.value, banded.metrics[k].value)

    def test_deterministic(self):
        m = _grounded_model()
        a, b = simulate_with_confidence(m), simulate_with_confidence(m)
        self.assertEqual({k: (mm.low, mm.high) for k, mm in a.metrics.items()},
                         {k: (mm.low, mm.high) for k, mm in b.metrics.items()})

    def test_worst_variant_uses_low_capacity_and_raises_utilization(self):
        # monotonic-direction sanity: capacity's pessimistic endpoint is LOW → higher utilisation.
        m = _grounded_model()
        worst = _variant(m, worst=True)
        self.assertEqual(worst.components["app"].per_instance_rps, 6000.0)
        self.assertGreater(simulate(worst).bottleneck_utilization, simulate(m).bottleneck_utilization)

    def test_reconcile_input_is_held_constant(self):
        # modeler value OUTSIDE the cited band (RECONCILE) is NOT a source of uncertainty → no bands.
        m = _grounded_model(cap=20000.0, g_value=8000.0, cap_band=(6000.0, 10000.0))   # comp 20000 ∉ [6000,10000]
        self.assertFalse(has_grounded_in_band(m))
        r = simulate_with_confidence(m)
        self.assertTrue(all(mm.low is None for mm in r.metrics.values()))

    def test_saturating_input_range_omits_bands_with_caveat(self):
        # When a grounded input's CITED band is wide enough to push a scenario past saturation, numeric
        # bands are omitted (no false precision like a "250-second" range) and a caveat explains why.
        c = Component("api", K.EXTERNAL_API, "Rate-limited API", per_instance_rps=100.0, instances=1,
                      base_latency_ms=140.0, monthly_cost_per_instance=0,
                      groundings={"per_instance_rps": Grounding(
                          value=100, unit="rps", confidence_low=7, confidence_high=140, citations=[_cite()])})
        m = SystemModel(name="sat", components={"api": c},
                        flows=[Flow("f", 1.0, [FlowStep("api")])], workload=Workload(64.0))
        r = simulate_with_confidence(m)
        self.assertTrue(all(mm.low is None for mm in r.metrics.values()))   # no numeric bands
        self.assertTrue(any("Confidence bands omitted" in cav for cav in r.caveats))

    def test_grounded_cost_variant_stays_integer(self):
        # Harm floor: a grounded monthly_cost variant keeps integer cents (cited band is whole cents).
        c = Component("app", K.APP_SERVER, "App", per_instance_rps=8000.0, instances=1,
                      base_latency_ms=5.0, monthly_cost_per_instance=5000,
                      groundings={"monthly_cost_per_instance": Grounding(
                          value=5000, unit="usd_minor_per_month", confidence_low=4000,
                          confidence_high=6000, citations=[_cite()])})
        m = SystemModel(name="c", components={"app": c},
                        flows=[Flow("f", 1.0, [FlowStep("app")])], workload=Workload(5000.0))
        worst = _variant(m, worst=True)
        cost = worst.components["app"].monthly_cost_per_instance
        self.assertIsInstance(cost, int)
        self.assertEqual(cost, 6000)   # high endpoint = worst for cost


if __name__ == "__main__":
    unittest.main()
