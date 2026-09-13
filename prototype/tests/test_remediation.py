"""Tests for the capacity remediation planner.

The guards that matter: the plan must be minimal (one instance fewer must fail), it must never
recommend adding instances to a component type where that is a category error, every figure must
come from the two real engine runs, and it must stay deterministic and pure.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import url_shortener
from keystone.model import ComponentKind
from keystone.remediation import (
    BLOCKED_KINDS, SCALE_OUT_KINDS, SCALING_LIMITS, plan_capacity,
)
from keystone.simulation import SAFE_UTILIZATION, simulate


def _with_instances(model, cid, n):
    comps = dict(model.components)
    comps[cid] = dataclasses.replace(comps[cid], instances=n)
    return dataclasses.replace(model, components=comps)


def _at(model, rps):
    return dataclasses.replace(model, workload=dataclasses.replace(model.workload, system_rps=rps))


class PolicyTest(unittest.TestCase):
    def test_scale_out_and_blocked_kinds_are_disjoint_and_cover_the_enum(self):
        overlap = SCALE_OUT_KINDS & set(BLOCKED_KINDS)
        self.assertFalse(overlap, f"a kind cannot be both scalable and blocked: {overlap}")
        covered = SCALE_OUT_KINDS | set(BLOCKED_KINDS)
        missing = set(ComponentKind) - covered
        self.assertFalse(missing, f"every ComponentKind needs a declared lever policy; missing {missing}")

    def test_single_writer_and_third_party_are_never_scaled_out(self):
        """The two answers a naive capacity tool gets wrong."""
        self.assertNotIn(ComponentKind.SQL_DB, SCALE_OUT_KINDS)
        self.assertNotIn(ComponentKind.EXTERNAL_API, SCALE_OUT_KINDS)

    def test_every_blocker_carries_real_guidance(self):
        for kind, why in BLOCKED_KINDS.items():
            with self.subTest(kind.value):
                self.assertGreater(len(why), 80, "a blocker must explain the options, not just refuse")

    def test_limits_are_published(self):
        self.assertGreaterEqual(len(SCALING_LIMITS), 4)
        joined = " ".join(SCALING_LIMITS).lower()
        self.assertIn("linear", joined, "the linear-capacity assumption must be disclosed")


class PlanCorrectnessTest(unittest.TestCase):
    def setUp(self):
        self.model = url_shortener.build()

    def test_no_change_when_the_design_already_holds(self):
        plan = plan_capacity(self.model)   # design load, comfortably under the ceiling
        self.assertEqual(plan.remedies, [])
        self.assertEqual(plan.blockers, [])
        self.assertTrue(plan.holds)
        self.assertEqual(plan.monthly_cost_delta_cents, 0)

    def test_the_20k_case_holds_after_scaling_out(self):
        plan = plan_capacity(self.model, 20_000)
        self.assertTrue(plan.holds)
        self.assertTrue(plan.remedies)
        self.assertLessEqual(plan.after.bottleneck_utilization, SAFE_UTILIZATION)
        self.assertGreater(plan.monthly_cost_delta_cents, 0, "more instances must cost more")

    def test_the_plan_is_minimal(self):
        """One instance fewer on any remedy must break the ceiling — otherwise it over-provisioned."""
        plan = plan_capacity(self.model, 60_000)
        self.assertTrue(plan.remedies)
        for r in plan.remedies:
            with self.subTest(r.component_id):
                self.assertGreater(r.to_instances, r.from_instances)
                trimmed = _at(self.model, 60_000)
                for other in plan.remedies:
                    trimmed = _with_instances(trimmed, other.component_id, other.to_instances)
                trimmed = _with_instances(trimmed, r.component_id, r.to_instances - 1)
                worst = simulate(trimmed).components[r.component_id].utilization
                self.assertGreater(
                    worst, SAFE_UTILIZATION,
                    f"{r.component_name} at {r.to_instances - 1} would still hold — plan is not minimal")

    def test_sizing_matches_the_stated_formula(self):
        plan = plan_capacity(self.model, 60_000)
        for r in plan.remedies:
            with self.subTest(r.component_id):
                arrival = plan.after.components[r.component_id].arrival_rps
                per = self.model.components[r.component_id].per_instance_rps
                self.assertEqual(r.to_instances,
                                 max(1, math.ceil(arrival / (per * SAFE_UTILIZATION))))

    def test_a_single_writer_wall_is_reported_not_papered_over(self):
        model = _with_instances(self.model, "db", 1)
        comps = dict(model.components)
        comps["db"] = dataclasses.replace(comps["db"], per_instance_rps=300.0)
        model = dataclasses.replace(model, components=comps)

        plan = plan_capacity(model, 20_000)
        self.assertFalse(plan.holds)
        self.assertTrue(plan.blockers)
        db = next(b for b in plan.blockers if b.component_id == "db")
        self.assertEqual(db.kind, "sql_db")
        self.assertIn("single writer", db.guidance)
        self.assertFalse([r for r in plan.remedies if r.component_id == "db"],
                         "the planner must not add instances to a relational primary")

    def test_verdict_names_the_blocker_when_it_cannot_hold(self):
        comps = dict(self.model.components)
        comps["db"] = dataclasses.replace(comps["db"], per_instance_rps=300.0)
        plan = plan_capacity(dataclasses.replace(self.model, components=comps), 20_000)
        self.assertIn("architectural change", plan.verdict)
        self.assertIn("PostgreSQL", plan.verdict)


class PrimeDirectiveTest(unittest.TestCase):
    """Every figure in a plan is one of the two engine runs, or their difference."""

    def setUp(self):
        self.model = url_shortener.build()

    def test_cost_delta_is_the_difference_of_two_engine_runs(self):
        plan = plan_capacity(self.model, 60_000)
        self.assertEqual(plan.monthly_cost_delta_cents,
                         plan.after.monthly_cost - plan.before.monthly_cost)
        self.assertIsInstance(plan.monthly_cost_delta_cents, int, "money stays integer (ADR-008)")

    def test_holds_is_read_off_the_after_run(self):
        for target in (20_000, 200_000):
            with self.subTest(target):
                plan = plan_capacity(self.model, target)
                expected = all(c.utilization <= plan.ceiling for c in plan.after.components.values())
                self.assertEqual(plan.holds, expected)

    def test_before_matches_a_plain_simulate_at_the_target(self):
        plan = plan_capacity(self.model, 20_000)
        direct = simulate(_at(self.model, 20_000))
        self.assertEqual(plan.before.mean_latency_ms, direct.mean_latency_ms)
        self.assertEqual(plan.before.monthly_cost, direct.monthly_cost)

    def test_plan_shows_its_working(self):
        plan = plan_capacity(self.model, 20_000)
        joined = "\n".join(plan.derivation)
        self.assertIn("Baseline", joined)
        self.assertIn("Re-simulated", joined)
        self.assertIn("Monthly cost", joined)


class PurityAndDeterminismTest(unittest.TestCase):
    def test_input_model_is_not_mutated(self):
        model = url_shortener.build()
        before = copy.deepcopy(model)
        plan_capacity(model, 200_000)
        self.assertEqual(model, before)

    def test_deterministic(self):
        model = url_shortener.build()
        a, b = plan_capacity(model, 60_000), plan_capacity(model, 60_000)
        self.assertEqual([r.to_dict() for r in a.remedies], [r.to_dict() for r in b.remedies])
        self.assertEqual(a.monthly_cost_delta_cents, b.monthly_cost_delta_cents)
        self.assertEqual(a.verdict, b.verdict)


class CorpusTest(unittest.TestCase):
    def test_planner_runs_on_every_reference_model_under_heavy_load(self):
        checked = 0
        for name, builder, rps in REFERENCE_MODELS:
            model = builder()
            with self.subTest(name):
                plan = plan_capacity(model, model.workload.system_rps * 5)
                self.assertTrue(plan.verdict)
                # Never a scale-out on a blocked kind, on any model in the corpus.
                for r in plan.remedies:
                    kind = model.components[r.component_id].kind
                    self.assertIn(kind, SCALE_OUT_KINDS, f"{name}: {kind.value} is not scalable")
                # If it claims to hold, the after-run must actually be under the ceiling.
                if plan.holds:
                    self.assertLessEqual(
                        max(c.utilization for c in plan.after.components.values()), plan.ceiling)
                checked += 1
        self.assertGreater(checked, 30)


if __name__ == "__main__":
    unittest.main()
