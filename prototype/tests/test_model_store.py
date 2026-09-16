"""Issue #21 Milestone 5 — StubModelStore: the in-memory default, hermetic (no DB, $0),
matching council.py/ingestion.py's stub-first pattern (ADR-005 §7: "Mirrors ADR-001/002").

This satisfies the milestone's literal "done" gate for the offline path: a model saved then
reloaded comes back identical. Collected by scripts/check.sh's default `unittest discover`
(this file matches the `test*.py` glob, unlike the db_test_*.py files) — needs no
KEYSTONE_TEST_DATABASE_URL, no Postgres, nothing beyond the stdlib.
"""
from __future__ import annotations

import unittest

import copy

from keystone.ingestion import IngestError
from keystone.model import Assumption, Component, ComponentKind, Flow, FlowStep, PricingRates, SystemModel, Workload
from keystone.model_store import Project, StubModelStore, _validate_for_persistence, make_model_store
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


class TestStubModelStoreDeleteProject(unittest.TestCase):
    """Issue #21 Milestone 6 (ADR-005 §5). Stub has no source_document/Storage concept at
    all, so there's nothing to purge and no GAP to report here — that's the real seam,
    tested against SupabaseModelStore instead."""

    def test_delete_removes_all_versions(self):
        store = StubModelStore()
        project = Project(id="proj-1")
        store.save_model(project, _sample_model(name="v1"))
        store.save_model(project, _sample_model(name="v2"))
        result = store.delete_project(project)
        self.assertTrue(result.project_deleted)
        self.assertEqual(result.storage_objects_found, 0)
        self.assertEqual(result.storage_objects_purged, 0)
        self.assertEqual(result.storage_purge_errors, [])
        with self.assertRaises(KeyError):
            store.get_model(project)

    def test_delete_is_idempotent(self):
        """A repeat delete of an already-gone (or never-existed) project must not raise —
        ADR-005 §5 frames this as "erasure," and a second erasure request isn't an error."""
        store = StubModelStore()
        project = Project(id="does-not-exist")
        result = store.delete_project(project)
        self.assertFalse(result.project_deleted)

    def test_delete_does_not_affect_other_projects(self):
        store = StubModelStore()
        a, b = Project(id="proj-a"), Project(id="proj-b")
        store.save_model(a, _sample_model())
        store.save_model(b, _sample_model())
        store.delete_project(a)
        self.assertEqual(store.get_model(b).name, "sample")


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


def _persistable_model() -> SystemModel:
    """A model that must PASS `_validate_for_persistence` — each test below breaks exactly
    one field off a deepcopy of this, to prove the check firing isn't a coincidence from
    some OTHER field already being invalid."""
    model = _sample_model()
    model.assumptions.append(
        Assumption(subject="s", statement="st", confidence="med", source="user", provenance="ASSUMPTION")
    )
    return model


class TestValidateForPersistence(unittest.TestCase):
    """`_validate_for_persistence` had ZERO test coverage before this (Bifola's PR #198
    review, 2026-09-14, proved it empirically: replacing the function's body with a bare
    `return` changed nothing across 541 tests). It's the function that keeps StubModelStore
    and SupabaseModelStore agreeing on what "saveable" means, so each case here breaks
    exactly one field from an otherwise-valid model and expects the same IngestError
    save_model() itself raises."""

    def test_valid_model_passes(self):
        _validate_for_persistence(_persistable_model())   # must not raise

    def test_rejects_invalid_component_provenance(self):
        model = copy.deepcopy(_persistable_model())
        model.components["app"].provenance = "assumption"   # the stale lowercase default, model.py:59
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)

    def test_rejects_flow_share_out_of_range(self):
        model = copy.deepcopy(_persistable_model())
        model.flows[0].share = 1.5
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)

    def test_rejects_flow_step_visit_prob_out_of_range(self):
        model = copy.deepcopy(_persistable_model())
        model.flows[0].path[0].visit_prob = -0.1
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)

    def test_rejects_assumption_invalid_confidence(self):
        model = copy.deepcopy(_persistable_model())
        model.assumptions[0].confidence = "extremely-sure"
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)

    def test_rejects_assumption_invalid_source(self):
        model = copy.deepcopy(_persistable_model())
        model.assumptions[0].source = "vibes"
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)

    def test_rejects_assumption_invalid_provenance(self):
        model = copy.deepcopy(_persistable_model())
        model.assumptions[0].provenance = "assumption"   # the stale lowercase default again
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)

    def test_rejects_non_positive_system_rps(self):
        model = copy.deepcopy(_persistable_model())
        model.workload.system_rps = 0
        with self.assertRaises(IngestError):
            _validate_for_persistence(model)


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
