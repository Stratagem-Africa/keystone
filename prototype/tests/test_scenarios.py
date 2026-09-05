"""Deterministic tests for the chaos/event scenario layer (stdlib unittest, no deps).

The load-bearing guards here are the trust ones: a scenario must never author a number, must be
pure, must be deterministic, and must fail closed rather than silently no-op.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import dataclasses
import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import ticket_booking, url_shortener
from keystone.model import ComponentKind
from keystone.scenarios import (
    CATALOGUE, UNMODELLED, ScenarioResult, apply_scenario, available, get, run_scenario,
)
from keystone.simulation import SAFE_UTILIZATION, simulate


class CatalogueTest(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [s.id for s in CATALOGUE]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_scenario_declares_a_caveat_and_a_question(self):
        """Honesty contract: a scenario that cannot say what it does NOT model does not ship."""
        for s in CATALOGUE:
            with self.subTest(s.id):
                self.assertTrue(s.question.strip(), f"{s.id} has no question")
                self.assertTrue(s.caveat.strip(), f"{s.id} has no caveat")
                self.assertIn(s.category, {"traffic", "capacity", "data", "dependency"})

    def test_unmodelled_register_is_populated(self):
        """The list of things we deliberately refuse to fake must stay non-empty and explained."""
        self.assertGreaterEqual(len(UNMODELLED), 4)
        for key, why in UNMODELLED.items():
            with self.subTest(key):
                self.assertGreater(len(why), 60, f"{key} needs a real explanation, not a stub")

    def test_to_dict_is_serialisable_and_drops_the_callable(self):
        import json
        for s in CATALOGUE:
            with self.subTest(s.id):
                payload = s.to_dict()
                self.assertNotIn("apply", payload)
                self.assertNotIn("precondition", payload)
                json.loads(json.dumps(payload))   # raises if not serialisable

    def test_get_fails_closed_on_unknown_id(self):
        with self.assertRaises(ValueError):
            get("no_such_scenario")


class PurityAndDeterminismTest(unittest.TestCase):
    def setUp(self):
        self.model = url_shortener.build()

    def test_apply_does_not_mutate_the_input_model(self):
        before = copy.deepcopy(self.model)
        for scenario, target in available(self.model):
            with self.subTest(scenario.id, target=target):
                apply_scenario(self.model, scenario.id, target)
        self.assertEqual(self.model, before)

    def test_run_scenario_is_deterministic(self):
        for scenario, target in available(self.model):
            with self.subTest(scenario.id, target=target):
                a = run_scenario(self.model, scenario.id, target)
                b = run_scenario(self.model, scenario.id, target)
                self.assertEqual(a.perturbed.mean_latency_ms, b.perturbed.mean_latency_ms)
                self.assertEqual(a.perturbed.bottleneck_utilization,
                                 b.perturbed.bottleneck_utilization)
                self.assertEqual(a.perturbed.monthly_cost, b.perturbed.monthly_cost)
                self.assertEqual(a.verdict, b.verdict)

    def test_baseline_matches_a_plain_simulate_run(self):
        """The baseline side must be the engine's own untouched answer — not a re-derivation."""
        direct = simulate(self.model)
        result = run_scenario(self.model, "traffic_spike")
        self.assertEqual(result.baseline.mean_latency_ms, direct.mean_latency_ms)
        self.assertEqual(result.baseline.bottleneck_id, direct.bottleneck_id)
        self.assertEqual(result.baseline.monthly_cost, direct.monthly_cost)


class PrimeDirectiveTest(unittest.TestCase):
    """Every derived field must be arithmetic over the two engine runs — never a fresh estimate."""

    def setUp(self):
        self.model = url_shortener.build()

    def test_derived_fields_reduce_to_the_two_engine_runs(self):
        for scenario, target in available(self.model):
            with self.subTest(scenario.id, target=target):
                r = run_scenario(self.model, scenario.id, target)
                self.assertAlmostEqual(
                    r.latency_multiple,
                    r.perturbed.mean_latency_ms / r.baseline.mean_latency_ms, places=9)
                self.assertAlmostEqual(
                    r.utilization_delta,
                    r.perturbed.bottleneck_utilization - r.baseline.bottleneck_utilization,
                    places=9)
                self.assertEqual(r.bottleneck_moved,
                                 r.perturbed.bottleneck_id != r.baseline.bottleneck_id)
                self.assertEqual(r.survives,
                                 r.perturbed.bottleneck_utilization <= SAFE_UTILIZATION)

    def test_perturbed_side_carries_its_own_confidence_and_caveats(self):
        """A chaos result inherits the honesty apparatus; it is a full SimulationResult, not a number."""
        r = run_scenario(self.model, "traffic_spike")
        self.assertTrue(r.perturbed.confidence)
        self.assertTrue(r.perturbed.derivation, "perturbed run must keep its derivation trace")
        self.assertIn("saturated", r.perturbed.confidence.lower())

    def test_derivation_shows_its_working(self):
        r = run_scenario(self.model, "traffic_spike")
        joined = "\n".join(r.derivation)
        self.assertIn("baseline", joined)
        self.assertIn("perturbed", joined)
        self.assertIn("latency_multiple", joined)


class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.model = url_shortener.build()
        self.cache = next(cid for cid, c in self.model.components.items()
                          if c.kind is ComponentKind.CACHE)
        self.db = next(cid for cid, c in self.model.components.items()
                       if c.kind is ComponentKind.SQL_DB)

    def test_unknown_scenario_raises(self):
        with self.assertRaises(ValueError):
            apply_scenario(self.model, "nope")

    def test_missing_target_raises(self):
        with self.assertRaises(ValueError):
            apply_scenario(self.model, "cache_cold")

    def test_unknown_target_raises(self):
        with self.assertRaises(ValueError):
            apply_scenario(self.model, "cache_cold", "not_a_component")

    def test_wrong_kind_target_raises(self):
        """cache_cold on a database is a category error, not a silent no-op."""
        with self.assertRaises(ValueError):
            apply_scenario(self.model, "cache_cold", self.db)

    def test_cache_cold_refuses_a_cache_with_no_miss_path(self):
        """A canvas topology wires every step at certainty — a cold cache there changes nothing,
        so the scenario must be withheld rather than reported as 'survived'."""
        from keystone.topology import build_model_from_topology
        drawn = build_model_from_topology({
            "name": "drawn", "system_rps": 10_000,
            "nodes": [{"id": "lb", "kind": "load_balancer", "name": "LB"},
                      {"id": "app", "kind": "app_server", "name": "App"},
                      {"id": "ch", "kind": "cache", "name": "Cache"},
                      {"id": "db", "kind": "sql_db", "name": "DB"}],
            "edges": [["lb", "app"], ["app", "ch"], ["ch", "db"]]})
        self.assertTrue(all(s.visit_prob == 1.0 for f in drawn.flows for s in f.path))
        offered = {s.id for s, _ in available(drawn)}
        self.assertNotIn("cache_cold", offered)
        with self.assertRaises(ValueError):
            apply_scenario(drawn, "cache_cold", "ch")

    def test_instance_loss_refuses_a_single_instance_tier(self):
        """Losing the last instance is a hard failure the model cannot express — refuse, don't fake."""
        self.assertEqual(self.model.components[self.db].instances, 1)
        with self.assertRaises(ValueError):
            apply_scenario(self.model, "instance_loss", self.db)

    def test_available_never_offers_a_scenario_that_then_raises(self):
        """The catalogue the UI renders must be exactly what the engine will accept."""
        for model in (url_shortener.build(), ticket_booking.build()):
            for scenario, target in available(model):
                with self.subTest(model.name, scenario=scenario.id, target=target):
                    apply_scenario(model, scenario.id, target)   # must not raise


class PerturbationSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.model = url_shortener.build()
        self.cache = next(cid for cid, c in self.model.components.items()
                          if c.kind is ComponentKind.CACHE)
        self.app = next(cid for cid, c in self.model.components.items()
                        if c.kind is ComponentKind.APP_SERVER)

    def test_cache_cold_raises_the_miss_path_to_certainty(self):
        before = [s.visit_prob for f in self.model.flows for s in f.path if s.visit_prob < 1.0]
        self.assertTrue(before, "fixture must have a miss path below 1.0 to be meaningful")
        cold = apply_scenario(self.model, "cache_cold", self.cache)
        for flow in cold.flows:
            ids = [s.component_id for s in flow.path]
            if self.cache not in ids:
                continue
            after = ids.index(self.cache)
            for i, step in enumerate(flow.path):
                if i > after:
                    self.assertEqual(step.visit_prob, 1.0)

    def test_cache_cold_moves_the_bottleneck_to_the_datastore(self):
        """The signature result: the constraint relocates. This is what the panel exists to show."""
        r = run_scenario(self.model, "cache_cold", self.cache)
        self.assertTrue(r.bottleneck_moved)
        self.assertFalse(r.survives)
        self.assertGreater(r.latency_multiple, 10.0)

    def test_capacity_halved_halves_capacity(self):
        out = apply_scenario(self.model, "capacity_halved", self.app)
        self.assertAlmostEqual(out.components[self.app].per_instance_rps,
                               self.model.components[self.app].per_instance_rps * 0.5)
        self.assertEqual(out.components[self.app].instances,
                         self.model.components[self.app].instances)

    def test_instance_loss_removes_exactly_one(self):
        out = apply_scenario(self.model, "instance_loss", self.app)
        self.assertEqual(out.components[self.app].instances,
                         self.model.components[self.app].instances - 1)

    def test_slow_dependency_moves_latency_but_not_utilisation(self):
        """Service time inflates while capacity holds — so rho must not move."""
        r = run_scenario(self.model, "slow_dependency", self.app)
        self.assertAlmostEqual(r.utilization_delta, 0.0, places=9)
        self.assertGreater(r.latency_multiple, 1.0)

    def test_traffic_scenarios_scale_only_the_workload(self):
        out = apply_scenario(self.model, "traffic_spike")
        self.assertAlmostEqual(out.workload.system_rps, self.model.workload.system_rps * 10.0)
        self.assertEqual(out.components, self.model.components)
        self.assertEqual(out.flows, self.model.flows)


class CorpusRobustnessTest(unittest.TestCase):
    """Every offered scenario must run cleanly on every reference model in the corpus."""

    def test_all_scenarios_run_on_all_reference_models(self):
        checked = 0
        self.assertGreater(len(REFERENCE_MODELS), 30, "corpus should carry the v1-scope references")
        for name, builder, _rps in REFERENCE_MODELS:
            model = builder()
            for scenario, target in available(model):
                with self.subTest(model=name, scenario=scenario.id, target=target):
                    result = run_scenario(model, scenario.id, target)
                    self.assertIsInstance(result, ScenarioResult)
                    self.assertTrue(result.verdict)
                    self.assertGreaterEqual(result.perturbed.mean_latency_ms, 0.0)
                    checked += 1
        self.assertGreater(checked, 20, "corpus sweep should cover a meaningful number of runs")


if __name__ == "__main__":
    unittest.main()
