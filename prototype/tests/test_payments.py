"""Payments / Checkout (worked case #3) — high-stakes gate + the rate-limited gateway as the constraint."""
from __future__ import annotations

import unittest

from keystone.blueprints import payments
from keystone.council import HIGH_STAKES_AREA, is_high_stakes, make_council
from keystone.simulation import simulate


class TestPayments(unittest.TestCase):
    def test_baseline_bottleneck_is_the_payment_gateway(self):
        # The realistic finding: the external rate-limited gateway, not your own infra, is the constraint.
        sim = simulate(payments.build())
        self.assertEqual(sim.bottleneck_id, "gateway")
        self.assertGreater(sim.bottleneck_utilization, 0.5)   # clearly the binding resource
        self.assertLess(sim.bottleneck_utilization, 1.0)      # but below its ceiling at baseline

    def test_money_movement_triggers_expert_review_gate(self):
        model = payments.build()
        self.assertTrue(is_high_stakes(model.domain_flags))
        adrs = make_council().design(model)   # stub council
        self.assertTrue(any(a.area == HIGH_STAKES_AREA for a in adrs),
                        "a money-movement domain must carry the mandatory expert-review gate")

    def test_sale_drives_gateway_past_its_rate_limit(self):
        base = simulate(payments.build())
        sale = simulate(payments.sale())
        self.assertEqual(sale.bottleneck_id, "gateway")
        self.assertGreater(sale.bottleneck_utilization, 1.0)              # over the rate limit (429 regime)
        self.assertLess(sale.breakpoint_rps_safe, base.breakpoint_rps_safe)  # safe load collapses

    def test_cost_is_integer_and_gateway_has_no_infra_cost(self):
        m = payments.build()
        self.assertIsInstance(simulate(m).monthly_cost, int)          # harm floor
        self.assertEqual(m.components["gateway"].monthly_cost_per_instance, 0)  # external, usage-priced


if __name__ == "__main__":
    unittest.main()
