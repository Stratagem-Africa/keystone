"""ADR-009 Tier 1 — usage-based cost (egress / storage / requests).

The engine computes usage cost ON TOP of per-instance compute, in integer cents (harm floor,
ADR-008), from each component's declared monthly volumes × the model's per-unit rates. Default
volumes are 0, so existing (compute-only) models are unchanged — that regression guard is here too.
"""
from __future__ import annotations

import unittest

from keystone.blueprints import url_shortener
from keystone.model import Component, ComponentKind as K, Flow, FlowStep, PricingRates, SystemModel, Workload
from keystone.simulation import simulate


def _model(**usage) -> SystemModel:
    c = Component("c", K.APP_SERVER, "C", per_instance_rps=1000.0, instances=1,
                  monthly_cost_per_instance=5000, **usage)   # $50/mo compute
    return SystemModel(name="u", components={"c": c},
                       flows=[Flow("f", 1.0, [FlowStep("c")])], workload=Workload(1000.0))


class TestUsageCost(unittest.TestCase):
    def test_default_rates_compute_known_usage_cost(self):
        # GROUNDED rates (grounded_pricing_rates.json): egress $0.09/GB, storage $0.021/GB-mo, requests $3.00/1M
        sim = simulate(_model(egress_gb_per_month=1000, storage_gb=500, requests_per_month=10_000_000))
        bd = sim.cost_breakdown
        self.assertEqual(bd["compute"], 5000)      # $50.00
        self.assertEqual(bd["egress"], 9000)       # 1000 × $0.09   = $90.00
        self.assertEqual(bd["storage"], 1050)      # 500  × $0.021  = $10.50
        self.assertEqual(bd["requests"], 3000)     # 10M  × $3/M    = $30.00
        self.assertEqual(sim.monthly_cost, 5000 + 9000 + 1050 + 3000)   # $180.50
        self.assertIsInstance(sim.monthly_cost, int)   # harm floor: integer cents

    def test_no_usage_is_compute_only(self):
        sim = simulate(_model())   # all volumes default to 0
        self.assertEqual((sim.cost_breakdown["egress"], sim.cost_breakdown["storage"],
                          sim.cost_breakdown["requests"]), (0, 0, 0))
        self.assertEqual(sim.monthly_cost, sim.cost_breakdown["compute"])

    def test_breakdown_always_sums_to_total(self):
        sim = simulate(_model(egress_gb_per_month=333, storage_gb=77, requests_per_month=1_234_567))
        self.assertEqual(sum(sim.cost_breakdown.values()), sim.monthly_cost)

    def test_existing_blueprint_is_compute_only(self):
        # a shipped blueprint declares no usage → cost stays compute-only (regression guard)
        sim = simulate(url_shortener.build())
        self.assertEqual(sim.cost_breakdown["egress"], 0)
        self.assertEqual(sim.monthly_cost, sim.cost_breakdown["compute"])

    def test_usage_volumes_reject_float_and_negative(self):
        for bad in (dict(egress_gb_per_month=1.5), dict(storage_gb=-1), dict(requests_per_month=True)):
            with self.assertRaises((TypeError, ValueError)):
                Component("c", K.APP_SERVER, "C", per_instance_rps=1.0, **bad)

    def test_rates_reject_float_money(self):
        with self.assertRaises(ValueError):
            PricingRates(egress_micro_usd_per_gb=0.5)   # rates are integer micro-USD


if __name__ == "__main__":
    unittest.main()
