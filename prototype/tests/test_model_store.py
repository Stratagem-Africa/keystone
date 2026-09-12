"""Issue #21 Milestone 5 — StubModelStore: the in-memory default, hermetic (no DB, $0),
matching council.py/ingestion.py's stub-first pattern (ADR-005 §7: "Mirrors ADR-001/002").

This satisfies the milestone's literal "done" gate for the offline path: a model saved then
reloaded comes back identical. Collected by scripts/check.sh's default `unittest discover`
(this file matches the `test*.py` glob, unlike the db_test_*.py files) — needs no
KEYSTONE_TEST_DATABASE_URL, no Postgres, nothing beyond the stdlib.
"""
from __future__ import annotations

import unittest

from keystone.ingestion import IngestError
from keystone.model import Component, ComponentKind, Flow, FlowStep, PricingRates, SystemModel, Workload
from keystone.model_store import Project, StubModelStore, make_model_store
from keystone.provenance import Citation, Grounding


def _sample_model(*, name: str = "sample") -> SystemModel:
    return SystemModel(
        name=name,
        components={
            "app": Component(
                id="app", kind=ComponentKind.APP_SERVER, name="App server",
                per_instance_rps=100.0, instances=2, base_latency_ms=5.0,
                monthly_cost_per_instance=5000, provenance="ASSUMPTION",
                groundings={
                    "per_instance_rps": Grounding(
                        value=100.0, unit="rps", confidence_low=80.0, confidence_high=120.0,
                        citations=(Citation(source="bench", reference="http://example.com"),),
                    )
                },
            ),
        },
        flows=[Flow(name="main", share=1.0, path=[FlowStep(component_id="app", visit_prob=1.0)])],
        workload=Workload(system_rps=50.0, description="test"),
        pricing=PricingRates(egress_micro_usd_per_gb=123_456),
    )


class TestStubModelStoreRoundTrip(unittest.TestCase):
    def test_save_then_get_head_is_identical(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        model = _sample_model()
        version = store.save_model(project, model)
        self.assertEqual(version, 1, "first save must be version 1")
        reloaded = store.get_model(project, "head")
        self.assertEqual(reloaded, model, "round-trip must reproduce an identical SystemModel")

    def test_save_then_get_by_explicit_version(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        v1_model = _sample_model(name="v1")
        v2_model = _sample_model(name="v2")
        store.save_model(project, v1_model)
        store.save_model(project, v2_model)
        self.assertEqual(store.get_model(project, 1), v1_model)
        self.assertEqual(store.get_model(project, 2), v2_model)
        self.assertEqual(store.get_model(project, "head"), v2_model, "head must be the LATEST version")

    def test_mutating_the_original_after_save_does_not_corrupt_the_store(self):
        """Immutability check: StubModelStore deepcopies on write, so a caller mutating
        their own `model` reference after save_model() returns can't retroactively rewrite
        a version that's supposed to be permanent (ADR-005 §2)."""
        store = StubModelStore()
        project = Project(id="proj-1")
        model = _sample_model()
        store.save_model(project, model)
        model.name = "mutated-after-save"
        self.assertEqual(store.get_model(project, 1).name, "sample")

    def test_mutating_a_returned_model_does_not_corrupt_the_store(self):
        """Same guarantee, the other direction: deepcopies on read too."""
        store = StubModelStore()
        project = Project(id="proj-1")
        store.save_model(project, _sample_model())
        got = store.get_model(project, 1)
        got.name = "mutated-after-read"
        self.assertEqual(store.get_model(project, 1).name, "sample")

    def test_get_model_on_unknown_project_raises(self):
        store = StubModelStore()
        with self.assertRaises(KeyError):
            store.get_model(Project(id="does-not-exist"))

    def test_get_model_on_unknown_version_raises(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        store.save_model(project, _sample_model())
        with self.assertRaises(KeyError):
            store.get_model(project, 99)

    def test_save_model_rejects_invalid_model_before_storing_anything(self):
        """The fail-closed boundary (ADR-005 §6): validate_model runs first, and an invalid
        model is never stored as a version at all — not even a rejected placeholder."""
        store = StubModelStore()
        project = Project(id="proj-1")
        invalid = SystemModel(
            name="broken", components={}, flows=[], workload=Workload(system_rps=10.0)
        )
        with self.assertRaises(IngestError):
            store.save_model(project, invalid)
        with self.assertRaises(KeyError):
            store.get_model(project)   # nothing was ever saved


class TestStubModelStoreListVersionsAndDiff(unittest.TestCase):
    def test_list_versions_reflects_save_order_and_parent_chain(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        store.save_model(project, _sample_model(name="v1"))
        store.save_model(project, _sample_model(name="v2"))
        versions = store.list_versions(project)
        self.assertEqual([v.version for v in versions], [1, 2])
        self.assertEqual([v.parent_version for v in versions], [None, 1])
        self.assertEqual([v.name for v in versions], ["v1", "v2"])

    def test_diff_detects_component_and_flow_changes(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        v1 = _sample_model(name="v1")
        v2 = _sample_model(name="v2")
        v2.components["cache"] = Component(
            id="cache", kind=ComponentKind.CACHE, name="Cache", per_instance_rps=5000.0,
            provenance="ASSUMPTION",
        )
        v2.components["app"].instances = 4   # a changed field on an existing component
        # New flow must reference the new component too, or validate_model's orphan-
        # component check (require_connected=True, the default) correctly rejects it.
        # share must be > 0 (the real schema's CHECK, now also enforced by
        # _validate_for_persistence) — a small positive value keeps the two flows'
        # shares summing within validate_model()'s ~1.0 tolerance.
        v2.flows.append(Flow(name="secondary", share=0.01, path=[FlowStep(component_id="cache")]))
        store.save_model(project, v1)
        store.save_model(project, v2)

        diff = store.diff(project, 1, 2)
        self.assertEqual(diff.components_added, ["cache"])
        self.assertEqual(diff.components_removed, [])
        self.assertEqual(diff.components_changed, ["app"])
        self.assertEqual(diff.flows_added, ["secondary"])
        self.assertFalse(diff.workload_changed)
        self.assertFalse(diff.pricing_changed)

    def test_diff_of_identical_models_is_empty(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        model = _sample_model()
        store.save_model(project, model)
        store.save_model(project, _sample_model())   # a fresh but content-identical model
        diff = store.diff(project, 1, 2)
        self.assertEqual(diff.components_added, [])
        self.assertEqual(diff.components_removed, [])
        self.assertEqual(diff.components_changed, [])
        self.assertEqual(diff.flows_added, [])
        self.assertEqual(diff.flows_removed, [])
        self.assertEqual(diff.flows_changed, [])
        self.assertFalse(diff.workload_changed)
        self.assertFalse(diff.pricing_changed)


class TestMakeModelStore(unittest.TestCase):
    def test_defaults_to_stub(self):
        self.assertIsInstance(make_model_store(), StubModelStore)

    def test_explicit_stub_provider(self):
        self.assertIsInstance(make_model_store("stub"), StubModelStore)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            make_model_store("not-a-real-provider")

    def test_supabase_provider_without_access_token_raises(self):
        with self.assertRaises(ValueError):
            make_model_store("supabase")


if __name__ == "__main__":
    unittest.main()
