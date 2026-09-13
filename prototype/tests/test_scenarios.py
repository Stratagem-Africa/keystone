"""Deterministic tests for the chaos/event scenario layer (stdlib unittest, no deps).

The load-bearing guards here are the trust ones: a scenario must never author a number, must be
pure, must be deterministic, and must fail closed rather than silently no-op.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import dataclasses
import math
import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import ticket_booking, url_shortener
from keystone.model import ComponentKind
from keystone.scenarios import (
    CATALOGUE, UNMODELLED, ScenarioResult, ScenarioSpec, apply_scenario, available, get,
    run_compound, run_scenario,
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
        result = run_scenario(self.model, "traffic_surge", None, 10.0)
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
                # `latency_multiple` is a RATIO OF TWO FINITE LATENCIES or it is nothing. When the
                # scenario pushes the design past rho=1 the perturbed latency is unbounded and the
                # ratio is undefined — None, not a number. It used to be a float always, because
                # the engine clamped rho at 0.999 and manufactured a finite latency; this test
                # passed on that artifact.
                if math.isfinite(r.perturbed.mean_latency_ms):
                    self.assertAlmostEqual(
                        r.latency_multiple,
                        r.perturbed.mean_latency_ms / r.baseline.mean_latency_ms, places=9)
                else:
                    self.assertIsNone(r.latency_multiple,
                                      "an overloaded perturbed system has no latency multiple")
                    self.assertFalse(r.survives)
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
        r = run_scenario(self.model, "traffic_surge", None, 10.0)
        self.assertTrue(r.perturbed.confidence)
        self.assertTrue(r.perturbed.derivation, "perturbed run must keep its derivation trace")
        self.assertIn("saturated", r.perturbed.confidence.lower())

    def test_derivation_shows_its_working(self):
        r = run_scenario(self.model, "traffic_surge", None, 10.0)
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
        # Losing the cache drives this design past rho=1, so latency is unbounded and there is no
        # multiple. That is a STRONGER statement than "more than 10x worse", which is what this
        # asserted while the engine was clamping. Assert the real finding, not the artifact.
        self.assertIsNone(r.latency_multiple)
        self.assertEqual(r.perturbed.mean_latency_ms, math.inf)
        self.assertGreaterEqual(r.perturbed.bottleneck_utilization, 1.0)

    def test_capacity_degraded_scales_the_service_rate(self):
        out = apply_scenario(self.model, "capacity_degraded", self.app, 0.5)
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
        r = run_scenario(self.model, "slow_dependency", self.app, 10.0)
        self.assertAlmostEqual(r.utilization_delta, 0.0, places=9)
        # A slow dependency inflates service time, not capacity, so rho is unchanged and the system
        # stays stable — which is exactly why a finite multiple is meaningful HERE and is not in the
        # cache_cold case above.
        self.assertIsNotNone(r.latency_multiple, "rho did not move, so latency must stay finite")
        self.assertGreater(r.latency_multiple, 1.0)

    def test_traffic_scenarios_scale_only_the_workload(self):
        out = apply_scenario(self.model, "traffic_surge", None, 10.0)
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


class MagnitudeTest(unittest.TestCase):
    """Severity is a declared, closed set — a UI cannot invent one the catalogue never offered."""

    def setUp(self):
        self.model = url_shortener.build()

    def test_declared_magnitudes_are_ordered_and_usable(self):
        for s in CATALOGUE:
            if not s.magnitudes:
                continue
            with self.subTest(s.id):
                self.assertTrue(s.magnitude_unit, f"{s.id} must say what its magnitude means")
                self.assertEqual(s.default_magnitude, s.magnitudes[0])
                self.assertEqual(len(set(s.magnitudes)), len(s.magnitudes))

    def test_an_undeclared_magnitude_is_refused(self):
        with self.assertRaises(ValueError):
            apply_scenario(self.model, "traffic_surge", None, 7.0)

    def test_severity_moves_the_answer_monotonically(self):
        """A bigger dial must not produce a smaller effect — the whole point of parameterising."""
        latencies = [
            run_scenario(self.model, "slow_dependency", "db", m).perturbed.mean_latency_ms
            for m in (2.0, 10.0, 100.0, 1000.0)
        ]
        self.assertEqual(latencies, sorted(latencies), f"latency should rise with severity: {latencies}")

    def test_binary_scenarios_ignore_magnitude(self):
        a = run_scenario(self.model, "cache_cold", "cache")
        b = run_scenario(self.model, "cache_cold", "cache", 99.0)
        self.assertEqual(a.perturbed.mean_latency_ms, b.perturbed.mean_latency_ms)

    def test_instance_loss_precondition_respects_the_magnitude(self):
        """Losing 5 of 12 is fine; losing 5 of 3 would empty the tier and must be refused."""
        apply_scenario(self.model, "instance_loss", "app", 5.0)
        thin = dataclasses.replace(
            self.model,
            components={**self.model.components,
                        "app": dataclasses.replace(self.model.components["app"], instances=3)})
        with self.assertRaises(ValueError):
            apply_scenario(thin, "instance_loss", "app", 5.0)


class CompoundTest(unittest.TestCase):
    def setUp(self):
        self.model = url_shortener.build()

    def test_compound_is_simulated_once_on_the_composed_model(self):
        """The composed model carries BOTH perturbations, and is simulated, not combined."""
        both = run_compound(self.model, [
            ScenarioSpec("cache_cold", "cache"),
            ScenarioSpec("slow_dependency", "db", 100.0),
        ])
        self.assertEqual(len(both.applied), 2)
        self.assertIn("+", both.scenario_name)
        cold = run_scenario(self.model, "cache_cold", "cache")
        slow = run_scenario(self.model, "slow_dependency", "db", 100.0)
        # NEVER BETTER than either part alone. This was `assertGreater`, which passed only because
        # the old rho=0.999 clamp gave every overloaded run a slightly different finite number to
        # compare. Losing the cache already saturates this design, so the honest relation is
        # >=: unbounded is not "worse than" unbounded, it is the same statement.
        self.assertGreaterEqual(both.perturbed.mean_latency_ms, cold.perturbed.mean_latency_ms)
        self.assertGreaterEqual(both.perturbed.mean_latency_ms, slow.perturbed.mean_latency_ms)
        self.assertGreaterEqual(both.perturbed.bottleneck_utilization,
                                cold.perturbed.bottleneck_utilization)

    def test_composition_is_additive_while_stable_and_breaks_at_saturation(self):
        """WHY composition is simulated rather than added up — stated accurately.

        This test used to claim "compound is NOT the sum of its parts" and assert it with
        `assertNotAlmostEqual` on cache_cold + slow_dependency(100x). That claim is FALSE for this
        engine in the stable region, and the test only passed because the old rho=0.999 clamp handed
        every saturated run a slightly different finite number. Measured across every stable pair in
        the catalogue, compound latency equals the sum of the parts to the last decimal place — and
        it must, because path latency here is a SUM of per-component sojourns, so two perturbations
        aimed at DIFFERENT components that leave rho alone cannot interact.

        The real reason to simulate the composed model is the OTHER regime: perturbations that move
        rho compose non-linearly through 1/(1-rho), and a compound can cross saturation. Adding
        stored per-scenario results could never produce "unbounded" from two finite parts. Both
        halves are asserted below, so neither can rot into the other.
        """
        # 1. STABLE + DISJOINT -> additive, exactly. Asserting the true identity documents the limit.
        base = simulate(self.model).mean_latency_ms
        a = run_scenario(self.model, "slow_dependency", "app", 10.0)
        b = run_scenario(self.model, "capacity_degraded", "db", 0.5)
        both = run_compound(self.model, [ScenarioSpec("slow_dependency", "app", 10.0),
                                         ScenarioSpec("capacity_degraded", "db", 0.5)])
        for label, v in (("a", a.perturbed.mean_latency_ms), ("b", b.perturbed.mean_latency_ms),
                         ("both", both.perturbed.mean_latency_ms), ("base", base)):
            self.assertTrue(math.isfinite(v), f"{label} must stay stable for this half to mean anything")
        self.assertAlmostEqual(
            both.perturbed.mean_latency_ms,
            a.perturbed.mean_latency_ms + b.perturbed.mean_latency_ms - base, places=6,
            msg="disjoint perturbations that do not move rho ARE additive in this engine")

        # 2. SATURATING -> the compound is unbounded, which no arithmetic over finite parts reaches.
        hard = run_compound(self.model, [ScenarioSpec("cache_cold", "cache"),
                                         ScenarioSpec("slow_dependency", "db", 100.0)])
        self.assertEqual(hard.perturbed.mean_latency_ms, math.inf)
        self.assertIsNone(hard.latency_multiple)
        self.assertFalse(hard.survives)

    def test_aiming_twice_at_the_same_component_is_refused(self):
        with self.assertRaises(ValueError):
            run_compound(self.model, [
                ScenarioSpec("cache_cold", "cache"), ScenarioSpec("cache_cold", "cache")])

    def test_empty_compound_is_refused(self):
        with self.assertRaises(ValueError):
            run_compound(self.model, [])

    def test_compound_is_deterministic_and_order_stable(self):
        specs = [ScenarioSpec("traffic_surge", None, 5.0), ScenarioSpec("capacity_degraded", "app", 0.5)]
        a, b = run_compound(self.model, specs), run_compound(self.model, specs)
        self.assertEqual(a.perturbed.mean_latency_ms, b.perturbed.mean_latency_ms)
        self.assertEqual(a.verdict, b.verdict)

    def test_single_run_reports_one_applied_entry(self):
        r = run_scenario(self.model, "traffic_surge", None, 10.0)
        self.assertEqual(len(r.applied), 1)
        self.assertEqual(r.applied[0]["magnitude"], 10.0)


if __name__ == "__main__":
    unittest.main()
