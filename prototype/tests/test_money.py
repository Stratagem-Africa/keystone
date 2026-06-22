"""ADR-008 — money is integer minor units (USD cents), never float (harm floor).

Makes "no float money" structural: `Component` rejects a non-int cost at construction, every
seed cost in the corpus is integer cents, and the engine's summed cost stays an int.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import ticket_booking, url_shortener
from keystone.model import Component, ComponentKind
from keystone.simulation import simulate


class TestMoney(unittest.TestCase):

    def test_component_rejects_float_money(self):
        Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, monthly_cost_per_instance=2500)  # ok: cents
        with self.assertRaises(TypeError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, monthly_cost_per_instance=25.0)
        with self.assertRaises(TypeError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, monthly_cost_per_instance=True)
        with self.assertRaises(ValueError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, monthly_cost_per_instance=-1)

    def test_corpus_costs_are_integer_cents(self):
        models = [fn() for _k, fn, _r in REFERENCE_MODELS] + [url_shortener.build(), ticket_booking.build()]
        for m in models:
            for c in m.components.values():
                self.assertIsInstance(c.monthly_cost_per_instance, int)
                self.assertNotIsInstance(c.monthly_cost_per_instance, bool)
                self.assertGreaterEqual(c.monthly_cost_per_instance, 0)
                self.assertIsInstance(c.monthly_cost, int)  # per-instance × instances stays int

    def test_engine_cost_is_integer_minor_units(self):
        sim = simulate(url_shortener.build())
        self.assertIsInstance(sim.monthly_cost, int)
        self.assertEqual(sim.metrics["monthly_cost"].unit, "usd_minor_per_month")
        self.assertEqual(sim.metrics["monthly_cost"].value, sim.monthly_cost)


if __name__ == "__main__":
    unittest.main()
