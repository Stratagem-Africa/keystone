"""Deterministic tests for the simulation engine (stdlib unittest, no deps).

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import random
import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import ticket_booking, url_shortener
from keystone.model import Component, ComponentKind, Flow, FlowStep, SystemModel, Workload
from keystone.simulation import simulate, SAFE_UTILIZATION


def _random_model(rng: random.Random) -> SystemModel:
    """A random-but-valid SystemModel for property-fuzzing engine invariants (prior art: DST
    seeded input-space search, docs/13). Every component lands on >=1 flow so it sees load."""
    kinds = list(ComponentKind)
    ids = [f"c{i}" for i in range(rng.randint(2, 6))]
    comps = {
        cid: Component(
            cid, rng.choice(kinds), f"C{cid}",
            per_instance_rps=rng.uniform(100.0, 50_000.0),
            instances=rng.randint(1, 8),
            base_latency_ms=rng.uniform(0.1, 50.0),
            monthly_cost_per_instance=rng.randint(0, 50_000),  # integer minor units (cents, ADR-008)
        )
        for cid in ids
    }
    raw = [rng.random() + 0.01 for _ in range(rng.randint(1, 2))]
    total = sum(raw)
    flows, covered = [], set()
    for i, w in enumerate(raw):
        path_ids = rng.sample(ids, rng.randint(1, len(ids)))
        covered.update(path_ids)
        flows.append(Flow(f"f{i}", w / total, [FlowStep(c, visit_prob=rng.uniform(0.1, 1.0)) for c in path_ids]))
    missing = [c for c in ids if c not in covered]
    if missing:
        flows[0].path.extend(FlowStep(c) for c in missing)
    return SystemModel(name="fuzz", components=comps, flows=flows,
                       workload=Workload(system_rps=rng.uniform(100.0, 100_000.0)))


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

    def test_derivation_names_the_bottleneck_and_is_deterministic(self):
        # The generated "show your work" trace records the actual computed bottleneck and is
        # reproducible. It is provenance, not a metric source -- it only restates engine output.
        sim = simulate(url_shortener.build(system_rps=10_000, cache_hit_rate=0.90))
        self.assertTrue(sim.derivation)
        joined = "\n".join(sim.derivation)
        self.assertIn("Bottleneck", joined)
        self.assertIn(sim.bottleneck_name, joined)
        self.assertEqual(sim.derivation, simulate(url_shortener.build(
            system_rps=10_000, cache_hit_rate=0.90)).derivation)

    def test_derivation_handles_no_bottleneck(self):
        # Degenerate zero-load model: nothing sees arrivals, so there is no bottleneck. The trace
        # must still render (omitting the bottleneck line) and never raise (the `if bn:` branch).
        sim = simulate(url_shortener.build(system_rps=0))
        self.assertTrue(sim.derivation)
        self.assertNotIn("Bottleneck =", "\n".join(sim.derivation))

    def test_determinism_corpus_wide(self):
        # Run the WHOLE reference corpus twice and assert byte-identical results, failing AT the
        # diverging model (prior art: madsim — fail at the source, not on a rolled-up scalar). This
        # strengthens the single-blueprint 3-scalar check above to full-result equality everywhere.
        for key, build_fn, _ref_rps in REFERENCE_MODELS:  # build_fn is a 0-arg thunk
            model = build_fn()
            self.assertEqual(simulate(model), simulate(model),
                             f"non-deterministic engine output for reference model {key!r}")
        for label, model in (("url_shortener", url_shortener.build()),
                             ("ticket_booking", ticket_booking.build())):
            self.assertEqual(simulate(model), simulate(model),
                             f"non-deterministic engine output for blueprint {label!r}")

    def test_engine_invariants_property_fuzz(self):
        # Seeded property-fuzz over random valid models (prior art: DST multi-seed input search).
        # Fixed seed -> deterministic gate; on failure we print the seed+iteration to reproduce.
        SEED = 20260622
        rng = random.Random(SEED)
        for i in range(200):
            model = _random_model(rng)
            try:
                sim = simulate(model)
                for cid, r in sim.components.items():
                    self.assertTrue(math.isfinite(r.utilization) and r.utilization >= 0.0)
                    self.assertTrue(math.isfinite(r.mean_latency_ms) and r.mean_latency_ms >= 0.0)
                self.assertLessEqual(sim.p50_ms, sim.p95_ms)
                self.assertLessEqual(sim.p95_ms, sim.p99_ms)
                if sim.bottleneck_id is not None:
                    self.assertIn(sim.bottleneck_id, model.components)
                # breakpoint is load-invariant in an open network: doubling load must not move it.
                sim2 = simulate(model.scaled(model.workload.system_rps * 2))
                if math.isfinite(sim.breakpoint_rps_safe) and sim.breakpoint_rps_safe > 0:
                    self.assertAlmostEqual(sim.breakpoint_rps_safe / sim2.breakpoint_rps_safe, 1.0, places=6)
            except AssertionError:
                print(f"\n[property-fuzz] invariant FAILED at SEED={SEED} iteration={i}\n  model={model}")
                raise


class TestEngineAuditFixes(unittest.TestCase):
    """Fixes from the engine correctness audit: reject physically-impossible inputs; disclose the
    dominant-flow latency simplification."""

    def test_rejects_non_positive_capacity(self):
        for bad in (0, -100.0):
            with self.assertRaises(ValueError):
                Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=bad)
        with self.assertRaises(ValueError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=float("inf"))
        with self.assertRaises(TypeError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=True)

    def test_rejects_negative_latency(self):
        with self.assertRaises(ValueError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, base_latency_ms=-1.0)
        with self.assertRaises(ValueError):
            Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, base_latency_ms=float("nan"))
        Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0, base_latency_ms=0.0)  # 0 is OK

    def test_multi_flow_report_caveats_dominant_flow_latency(self):
        c = Component("c", ComponentKind.APP_SERVER, "C", per_instance_rps=1000.0)
        two = SystemModel(name="m", components={"c": c}, workload=Workload(100.0),
                          flows=[Flow("big", 0.9, [FlowStep("c")]), Flow("small", 0.1, [FlowStep("c")])])
        self.assertTrue(any("DOMINANT flow" in cav for cav in simulate(two).caveats))
        one = SystemModel(name="m", components={"c": c}, workload=Workload(100.0),
                          flows=[Flow("only", 1.0, [FlowStep("c")])])
        self.assertFalse(any("DOMINANT flow" in cav for cav in simulate(one).caveats))


if __name__ == "__main__":
    unittest.main()
