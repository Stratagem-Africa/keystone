"""Deterministic tests for the simulation engine (stdlib unittest, no deps).

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from keystone.blueprints import url_shortener
from keystone.simulation import simulate, SAFE_UTILIZATION


class TestSimulation(unittest.TestCase):

    def test_determinism(self):
        a = simulate(url_shortener.build())
        b = simulate(url_shortener.build())
        self.assertEqual(a.bottleneck_id, b.bottleneck_id)
        self.assertAlmostEqual(a.bottleneck_utilization, b.bottleneck_utilization)
        self.assertAlmostEqual(a.p99_ms, b.p99_ms)

    def test_app_is_bottleneck_at_baseline(self):
        sim = simulate(url_shortener.build(system_rps=10_000, cache_hit_rate=0.90))
        # App tier (12 x 1200 = 14,400 rps cap) carries all 10k -> ~69% util, the max.
        self.assertEqual(sim.bottleneck_id, "app")
        self.assertAlmostEqual(sim.bottleneck_utilization, 10_000 / 14_400, places=3)

    def test_cache_protects_the_db(self):
        warm = simulate(url_shortener.build(system_rps=10_000, cache_hit_rate=0.90))
        cold = simulate(url_shortener.build(system_rps=10_000, cache_hit_rate=0.0))
        # With a warm cache the DB is well under capacity; cold, it saturates and
        # becomes the bottleneck. This is the load-bearing lesson the demo proves.
        self.assertLess(warm.components["db"].utilization, 0.5)
        self.assertGreaterEqual(cold.components["db"].utilization, 1.0)
        self.assertEqual(cold.bottleneck_id, "db")

    def test_breakpoint_scales_linearly(self):
        low = simulate(url_shortener.build(system_rps=10_000))
        high = simulate(url_shortener.build(system_rps=20_000))
        # Doubling load halves headroom but the safe breakpoint is load-invariant
        # (open network): same architecture -> same max sustainable rps.
        self.assertAlmostEqual(low.breakpoint_rps_safe, high.breakpoint_rps_safe, places=0)

    def test_breakpoint_is_safe_ceiling_over_utilization(self):
        sim = simulate(url_shortener.build(system_rps=10_000))
        expected = 10_000 * (SAFE_UTILIZATION / sim.bottleneck_utilization)
        self.assertAlmostEqual(sim.breakpoint_rps_safe, expected, places=0)

    def test_percentiles_ordered(self):
        sim = simulate(url_shortener.build())
        self.assertLess(sim.p50_ms, sim.p95_ms)
        self.assertLess(sim.p95_ms, sim.p99_ms)

    def test_spof_detection(self):
        sim = simulate(url_shortener.build())
        # Single primary DB and single cache are SPOFs.
        self.assertIn("PostgreSQL primary (r7g.large)", sim.spofs)
        self.assertIn("Redis cache (r7g.large)", sim.spofs)


if __name__ == "__main__":
    unittest.main()
