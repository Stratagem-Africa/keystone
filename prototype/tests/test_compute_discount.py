"""ADR-009 Tier 2 — compute pricing discount lever (on_demand / reserved / spot).

Real deployments rarely pay on-demand list price; a 1–3yr commitment or interruptible spot cuts the
compute bill 40–90%. The engine applies a single discount to COMPUTE ONLY, in pure-integer cents
(harm floor, ADR-008). `on_demand` (the default) is a no-op, so every existing cost number is
byte-for-byte unchanged — that regression guard is here too.
"""
from __future__ import annotations

import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import url_shortener
from keystone.model import (Component, ComponentKind as K, Flow, FlowStep,
                            PricingRates, SystemModel, Workload)
from keystone.simulation import simulate


def _model(pricing: str = "on_demand", **usage) -> SystemModel:
    # $100/mo compute (10_000 cents), one instance.
    c = Component("c", K.APP_SERVER, "C", per_instance_rps=1000.0, instances=1,
                  monthly_cost_per_instance=10_000, **usage)
    return SystemModel(name="u", components={"c": c},
                       flows=[Flow("f", 1.0, [FlowStep("c")])], workload=Workload(1000.0),
                       pricing=PricingRates(compute_pricing=pricing))


class TestComputeDiscount(unittest.TestCase):
    def test_on_demand_is_a_no_op(self):
        sim = simulate(_model("on_demand"))
        self.assertEqual(sim.cost_breakdown["compute"], 10_000)   # list price unchanged
        self.assertEqual(sim.compute_list_cents, 10_000)
        self.assertEqual(sim.monthly_cost, 10_000)

    def test_published_range_discounts(self):
        # list $100 → GROUNDED: reserved_1yr 30% off, reserved_3yr 55% off, spot 77% off (bp retained)
        for pricing, expected in (("reserved_1yr", 7_000), ("reserved_3yr", 4_500), ("spot", 2_300)):
            sim = simulate(_model(pricing))
            self.assertEqual(sim.cost_breakdown["compute"], expected, pricing)
            self.assertEqual(sim.compute_list_cents, 10_000, pricing)   # list always the un-discounted price
            self.assertEqual(sim.compute_pricing, pricing)
            self.assertIsInstance(sim.cost_breakdown["compute"], int)   # harm floor: integer cents

    def test_discount_touches_compute_only(self):
        # same usage, two pricing models → egress/storage/requests identical; only compute moves
        kw = dict(egress_gb_per_month=1000, storage_gb=500, requests_per_month=10_000_000)
        on, spot = simulate(_model("on_demand", **kw)), simulate(_model("spot", **kw))
        for line in ("egress", "storage", "requests"):
            self.assertEqual(on.cost_breakdown[line], spot.cost_breakdown[line], line)
        self.assertLess(spot.cost_breakdown["compute"], on.cost_breakdown["compute"])

    def test_breakdown_still_sums_to_total(self):
        sim = simulate(_model("reserved_3yr", egress_gb_per_month=333, storage_gb=77,
                              requests_per_month=1_234_567))
        self.assertEqual(sum(sim.cost_breakdown.values()), sim.monthly_cost)

    def test_rounding_is_half_up_integer(self):
        # list = 10_003 cents, reserved_3yr (×0.45 retained) = 4501.35 → 4501; pure-integer, no float drift
        c = Component("c", K.APP_SERVER, "C", per_instance_rps=1.0, monthly_cost_per_instance=10_003)
        m = SystemModel("u", {"c": c}, [Flow("f", 1.0, [FlowStep("c")])], Workload(1.0),
                        pricing=PricingRates(compute_pricing="reserved_3yr"))
        self.assertEqual(simulate(m).cost_breakdown["compute"], 4501)

    def test_unknown_pricing_model_rejected(self):
        with self.assertRaises(ValueError):
            PricingRates(compute_pricing="free_lunch")

    def test_all_reference_models_unchanged_under_default(self):
        # every runnable reference model defaults to on_demand → compute line == raw list, total unchanged
        for key, build_fn, _rps in REFERENCE_MODELS:
            sim = simulate(build_fn())
            list_compute = sum(c.monthly_cost for c in build_fn().components.values())
            self.assertEqual(sim.cost_breakdown["compute"], list_compute, key)
            self.assertEqual(sim.compute_list_cents, list_compute, key)
            self.assertEqual(sim.compute_pricing, "on_demand", key)

    def test_url_shortener_regression(self):
        sim = simulate(url_shortener.build())
        self.assertEqual(sim.compute_pricing, "on_demand")
        self.assertEqual(sim.cost_breakdown["compute"], sim.compute_list_cents)


if __name__ == "__main__":
    unittest.main()
