"""Issue #21 Milestone 5 — SupabaseModelStore's PYTHON PLUMBING, hermetic (mocked
`supabase.create_client`, no network, no DB). This is the only place that class's actual
code gets exercised: db_test_model_store_roundtrip.py drives Postgres via raw SQL (through
the tenant_isolation_test_helpers.py harness), never through this class, so it proves the
RPC function is correct but says nothing about whether SupabaseModelStore builds the right
payload or reconstructs a SystemModel correctly from a row. This file is that other half.

Collected by scripts/check.sh's default `unittest discover` (matches `test*.py`) — needs no
DB, no KEYSTONE_TEST_DATABASE_URL, no real Supabase project.
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from keystone.ingestion import IngestError
from keystone.model import Component, ComponentKind, Flow, FlowStep, PricingRates, SystemModel, Workload
from keystone.model_store import Project
from keystone.provenance import Citation, Grounding
from keystone import supabase_model_store
from keystone.supabase_model_store import StorageNotConfiguredError, SupabaseModelStore


class _FakeQuery:
    """Stands in for supabase-py's chained query builder. Every filter method (`select`,
    `eq`, `order`, `single`) just returns self, so any chain SupabaseModelStore builds
    works regardless of exact call order — only the final `.execute().data` matters."""

    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _FakeClient:
    """Stands in for the supabase-py client. `table_data` maps table name -> the `.data`
    that table's query should return; `rpc_result` is what `.rpc(...).execute().data`
    returns. Records every `.rpc()` call (name + payload) so tests can assert on it."""

    def __init__(self, table_data: dict, rpc_result=None):
        self._table_data = table_data
        self._rpc_result = rpc_result
        self.rpc_calls: list[tuple[str, dict]] = []
        self.postgrest = SimpleNamespace(auth=lambda token: None)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._table_data[name])

    def rpc(self, name: str, payload: dict) -> _FakeQuery:
        self.rpc_calls.append((name, payload))
        return _FakeQuery(self._rpc_result)


def _make_store(fake_client: _FakeClient) -> SupabaseModelStore:
    # SupabaseModelStore.__init__ does `from supabase import create_client` LAZILY, precisely
    # so importing keystone (or this test module) never pulls the optional `db` extra
    # (pyproject.toml) into the base install. `patch("supabase.create_client", ...)` would
    # undo that: to patch an attribute, mock has to import the real module first, which
    # crashes this file with ModuleNotFoundError on any machine without the extra — that
    # was the merge-gate blocker (Bifola's PR #198 review, 2026-09-14). The fix is to hand
    # the lazy import a FAKE module to find instead of skipping these tests wherever the
    # extra is missing: `sys.modules["supabase"]` becomes a stand-in with just the one
    # attribute (`create_client`) the lazy import touches, so all 8 tests below keep
    # actually running, on every machine, with nothing installed (verified by Bifola on a
    # scratch copy: 541 tests OK, no skips).
    fake_module = types.ModuleType("supabase")
    fake_module.create_client = lambda *a, **k: fake_client
    with patch.dict(os.environ, {"SUPABASE_URL": "http://example.test", "SUPABASE_ANON_KEY": "anon-key"}):
        with patch.dict(sys.modules, {"supabase": fake_module}):
            return SupabaseModelStore(access_token="fake-jwt")


def _sample_model() -> SystemModel:
    return SystemModel(
        name="payload-test",
        components={
            "app": Component(
                id="app", kind=ComponentKind.APP_SERVER, name="App", per_instance_rps=100.0,
                monthly_cost_per_instance=5000, provenance="ASSUMPTION",
                groundings={"per_instance_rps": Grounding(
                    value=100.0, unit="rps", confidence_low=90.0, confidence_high=110.0,
                    citations=(Citation(source="s", reference="r"),),
                )},
            ),
        },
        flows=[Flow(name="main", share=1.0, path=[FlowStep(component_id="app")])],
        workload=Workload(system_rps=10.0),
        pricing=PricingRates(),
    )


class TestSaveModelPayload(unittest.TestCase):
    def test_calls_rpc_with_project_id_and_expected_fields(self):
        client = _FakeClient(table_data={}, rpc_result=1)
        store = _make_store(client)
        store.save_model(Project(id="proj-1"), _sample_model())

        self.assertEqual(len(client.rpc_calls), 1)
        name, payload = client.rpc_calls[0]
        self.assertEqual(name, "keystone_save_system_model")
        self.assertEqual(payload["p_project_id"], "proj-1")
        self.assertEqual(payload["p_name"], "payload-test")
        self.assertEqual(len(payload["p_components"]), 1)
        self.assertEqual(payload["p_components"][0]["id"], "app")
        self.assertEqual(len(payload["p_flows"]), 1)
        self.assertEqual(payload["p_flows"][0]["path"][0]["component_id"], "app")
        # Grounding must already be JSON-plain (no Grounding/Citation objects left) —
        # the RPC receives raw jsonb-shaped dicts, not Python dataclasses.
        g = payload["p_components"][0]["groundings"]["per_instance_rps"]
        self.assertIsInstance(g["value"], float)
        self.assertEqual(g["citations"], [{"source": "s", "reference": "r", "note": ""}])

    def test_rejects_invalid_model_without_ever_calling_rpc(self):
        """The fail-closed boundary: validate_model runs before the network call — an
        invalid model must not even reach Postgres, let alone be stored."""
        client = _FakeClient(table_data={}, rpc_result=1)
        store = _make_store(client)
        invalid = SystemModel(name="broken", components={}, flows=[], workload=Workload(system_rps=1.0))
        with self.assertRaises(IngestError):
            store.save_model(Project(id="proj-1"), invalid)
        self.assertEqual(client.rpc_calls, [], "no RPC call should be made for an invalid model")

    def test_unwraps_bare_int_response(self):
        client = _FakeClient(table_data={}, rpc_result=7)
        store = _make_store(client)
        self.assertEqual(store.save_model(Project(id="p"), _sample_model()), 7)

    def test_unwraps_list_wrapped_response(self):
        client = _FakeClient(table_data={}, rpc_result=[7])
        store = _make_store(client)
        self.assertEqual(store.save_model(Project(id="p"), _sample_model()), 7)

    def test_unwraps_dict_wrapped_response(self):
        client = _FakeClient(table_data={}, rpc_result=[{"keystone_save_system_model": 7}])
        store = _make_store(client)
        self.assertEqual(store.save_model(Project(id="p"), _sample_model()), 7)


class TestGetModel(unittest.TestCase):
    def _table_data(self) -> dict:
        return {
            "project": {"head_model_version": 3},
            "system_model": {
                "name": "reloaded", "domain_flags": ["high_stakes:elections"],
                "system_rps": 42.0, "workload_description": "peak",
                "egress_micro_usd_per_gb": 90_000, "storage_micro_usd_per_gb_month": 21_000,
                "request_micro_usd_per_thousand": 3_000, "llm_input_micro_usd_per_1k_tokens": 500,
                "llm_output_micro_usd_per_1k_tokens": 4_000, "compute_pricing": "on_demand",
                "pricing_groundings": {},
            },
            "component": [
                {
                    "id": "app", "kind": "app_server", "name": "App", "per_instance_rps": 100.0,
                    "instances": 2, "base_latency_ms": 5.0, "monthly_cost_per_instance": 5000,
                    "egress_gb_per_month": 0, "storage_gb": 0, "requests_per_month": 0,
                    "llm_input_tokens_per_month": 0, "llm_output_tokens_per_month": 0,
                    "provenance": "ASSUMPTION", "groundings": {}, "match_context": {},
                },
            ],
            "flow": [{"id": "flow-uuid-1", "name": "main", "share": 1.0}],
            "flow_step": [{"flow_id": "flow-uuid-1", "component_id": "app", "step_order": 0, "visit_prob": 1.0}],
            "assumption": [
                {"subject": "s", "statement": "st", "confidence": "med", "source": "user", "provenance": "ASSUMPTION"},
            ],
        }

    def test_head_looks_up_project_first_then_that_version(self):
        client = _FakeClient(table_data=self._table_data())
        store = _make_store(client)
        model = store.get_model(Project(id="proj-1"), "head")
        self.assertEqual(model.name, "reloaded")

    def test_reconstructs_components_flows_workload_pricing_assumptions(self):
        client = _FakeClient(table_data=self._table_data())
        store = _make_store(client)
        model = store.get_model(Project(id="proj-1"), 3)

        self.assertEqual(set(model.components), {"app"})
        self.assertEqual(model.components["app"].kind, ComponentKind.APP_SERVER)
        self.assertEqual(model.components["app"].instances, 2)

        self.assertEqual(len(model.flows), 1)
        self.assertEqual(model.flows[0].name, "main")
        self.assertEqual(model.flows[0].path[0].component_id, "app")

        self.assertEqual(model.workload.system_rps, 42.0)
        self.assertEqual(model.domain_flags, ["high_stakes:elections"])

        self.assertEqual(model.pricing.egress_micro_usd_per_gb, 90_000)
        self.assertEqual(model.pricing.compute_pricing, "on_demand")

        self.assertEqual(len(model.assumptions), 1)
        self.assertEqual(model.assumptions[0].subject, "s")

    def test_flow_steps_are_grouped_by_flow_and_sorted_by_step_order_independently(self):
        """The specific bug this guards against: a single global ORDER BY step_order would
        NOT correctly interleave two flows' paths, since step_order resets to 0 per flow.
        Two flows, each with 2 steps, deliberately returned out of order from the fake
        table to prove the grouping+sort happens in Python, not assumed from row order."""
        data = self._table_data()
        data["flow"] = [
            {"id": "flow-a", "name": "A", "share": 0.5},
            {"id": "flow-b", "name": "B", "share": 0.5},
        ]
        data["component"].append({
            "id": "db", "kind": "sql_db", "name": "DB", "per_instance_rps": 500.0,
            "instances": 1, "base_latency_ms": 1.0, "monthly_cost_per_instance": 0,
            "egress_gb_per_month": 0, "storage_gb": 0, "requests_per_month": 0,
            "llm_input_tokens_per_month": 0, "llm_output_tokens_per_month": 0,
            "provenance": "ASSUMPTION", "groundings": {}, "match_context": {},
        })
        # Deliberately interleaved / out-of-order rows across both flows.
        data["flow_step"] = [
            {"flow_id": "flow-b", "component_id": "db", "step_order": 1, "visit_prob": 1.0},
            {"flow_id": "flow-a", "component_id": "db", "step_order": 1, "visit_prob": 1.0},
            {"flow_id": "flow-a", "component_id": "app", "step_order": 0, "visit_prob": 1.0},
            {"flow_id": "flow-b", "component_id": "app", "step_order": 0, "visit_prob": 1.0},
        ]
        client = _FakeClient(table_data=data)
        store = _make_store(client)
        model = store.get_model(Project(id="proj-1"), 3)

        flow_a = next(f for f in model.flows if f.name == "A")
        flow_b = next(f for f in model.flows if f.name == "B")
        self.assertEqual([s.component_id for s in flow_a.path], ["app", "db"])
        self.assertEqual([s.component_id for s in flow_b.path], ["app", "db"])


class TestDeleteProject(unittest.TestCase):
    """Issue #21 Milestone 6 (ADR-005 §5). `delete_project` calls `keystone_delete_project`
    (0006) — ONE RPC, not a select-then-delete pair — precisely because two separate
    PostgREST calls leave a race where a source_document inserted between them is
    cascade-deleted without ever being read (found by independent review of the earlier
    two-call version). `_purge_storage_objects` is a deliberate GAP (see its docstring) —
    no Storage/R2 client exists anywhere in this repo yet — so these tests assert the SEAM
    (the RPC call, error containment, the DB-row purge already having happened by the time
    Storage cleanup is even attempted), not a real Storage call."""

    def test_calls_the_rpc_with_project_id(self):
        client = _FakeClient(
            table_data={},
            rpc_result={"project_deleted": True, "source_document_uris": []},
        )
        store = _make_store(client)
        store.delete_project(Project(id="proj-1"))
        self.assertEqual(len(client.rpc_calls), 1)
        name, payload = client.rpc_calls[0]
        self.assertEqual(name, "keystone_delete_project")
        self.assertEqual(payload, {"p_project_id": "proj-1"})

    def test_reports_uris_the_rpc_collected_before_deleting(self):
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": True,
            "source_document_uris": ["t1/p1/a.txt", "t1/p1/b.txt"],
        })
        store = _make_store(client)
        result = store.delete_project(Project(id="proj-1"))

        self.assertTrue(result.project_deleted)
        self.assertEqual(result.storage_objects_found, 2)
        self.assertEqual(result.storage_objects_purged, 0, "no Storage client is wired up yet")
        self.assertEqual(len(result.storage_purge_errors), 1)
        self.assertIn("2 source_document object(s)", result.storage_purge_errors[0])

    def test_storage_gap_does_not_block_the_db_row_purge(self):
        """The DB erasure half is already done by the time Storage cleanup is even
        attempted (both happened inside the RPC's own transaction) — see DeletionResult's
        docstring for why that ordering is the deliberate priority."""
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": True, "source_document_uris": ["t1/p1/a.txt"],
        })
        store = _make_store(client)
        result = store.delete_project(Project(id="proj-1"))
        self.assertTrue(result.project_deleted)

    def test_a_real_storage_failure_is_recorded_not_raised(self):
        """Finding from independent review: the original narrow `except
        StorageNotConfiguredError` would let ANY other exception a real Storage/R2
        implementation raises propagate out of delete_project — but the DB row is already
        gone by then (the RPC already committed), so that would misreport a successful
        erasure as a total failure. Must be caught broadly and recorded instead."""
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": True, "source_document_uris": ["t1/p1/a.txt"],
        })
        store = _make_store(client)
        with patch.object(store, "_purge_storage_objects", side_effect=RuntimeError("bucket unreachable")):
            result = store.delete_project(Project(id="proj-1"))
        self.assertTrue(result.project_deleted, "DB erasure must not be reported as failed")
        self.assertEqual(result.storage_purge_errors, ["bucket unreachable"])

    def test_no_source_documents_means_no_gap_reported(self):
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": True, "source_document_uris": [],
        })
        store = _make_store(client)
        result = store.delete_project(Project(id="proj-1"))
        self.assertEqual(result.storage_objects_found, 0)
        self.assertEqual(result.storage_purge_errors, [])

    def test_empty_list_response_raises_instead_of_reporting_not_deleted(self):
        """Third independent review finding: the RPC always returns a well-formed object
        (even for a legitimate no-op — see test_no_matching_project_row_reports_not_deleted
        below), so an EMPTY response means something went wrong at the transport/PostgREST
        layer, not "nothing to delete." Silently reporting that as `project_deleted=False`
        would look identical to a real no-op and mask a genuine failure — must raise
        instead, matching save_model's existing fail-closed handling of the same shape."""
        client = _FakeClient(table_data={}, rpc_result=[])
        store = _make_store(client)
        with self.assertRaises(RuntimeError):
            store.delete_project(Project(id="proj-1"))

    def test_unwraps_dict_wrapped_response(self):
        """Same wire-shape ambiguity save_model's `test_unwraps_dict_wrapped_response`
        guards — a second independent review caught that the first version of this method
        only handled the list-wrapped case, not this one."""
        client = _FakeClient(table_data={}, rpc_result={
            "keystone_delete_project": {"project_deleted": True, "source_document_uris": ["a.txt"]},
        })
        store = _make_store(client)
        result = store.delete_project(Project(id="proj-1"))
        self.assertTrue(result.project_deleted)
        self.assertEqual(result.storage_objects_found, 1)

    def test_no_matching_project_row_reports_not_deleted(self):
        """Cross-tenant / already-deleted / unknown project: RLS makes the RPC's own DELETE
        match zero rows rather than raise (verified directly against real Postgres) — the
        client distinguishes this via `project_deleted`, not an exception."""
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": False, "source_document_uris": [],
        })
        store = _make_store(client)
        result = store.delete_project(Project(id="not-mine"))
        self.assertFalse(result.project_deleted)

    def test_failed_purge_keeps_every_uri_and_logs_them(self):
        """Bifola's PR #200 review, finding 1: by the time a purge fails the source_document
        rows are already cascade-deleted, so the uri strings exist nowhere else. They must
        come back on the result AND be logged (so they survive a caller that drops it)."""
        uris = ["t1/p1/a.txt", "t1/p1/b.txt"]
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": True, "source_document_uris": uris,
        })
        store = _make_store(client)
        with self.assertLogs("keystone.supabase_model_store", level="WARNING") as logs:
            result = store.delete_project(Project(id="proj-1"))
        self.assertTrue(result.project_deleted)
        self.assertEqual(result.unpurged_uris, uris)
        joined = "\n".join(logs.output)
        self.assertIn("t1/p1/a.txt", joined)
        self.assertIn("t1/p1/b.txt", joined)

    def _store_with_uris(self, uris):
        client = _FakeClient(table_data={}, rpc_result={"project_deleted": True, "source_document_uris": uris})
        return _make_store(client)

    def test_partial_purge_is_not_silent(self):
        """Bifola's PR #200 re-review, #4. A seam returning 2 of 3 used to give purged=2,
        errors=[], unpurged_uris=[] -- no error, no log, and the third object's source_document
        row already cascade-deleted. Anything not reported purged is unpurged, exception or not."""
        uris = ["t/p/a", "t/p/b", "t/p/c"]
        store = self._store_with_uris(uris)
        with patch.object(store, "_purge_storage_objects", return_value=["t/p/a", "t/p/c"]):
            with patch.object(supabase_model_store.logger, "warning") as warn:
                result = store.delete_project(Project(id="proj-1"))
        self.assertTrue(result.project_deleted)
        self.assertEqual(result.storage_objects_found, 3)
        self.assertEqual(result.storage_objects_purged, 2)
        self.assertEqual(result.unpurged_uris, ["t/p/b"])
        self.assertEqual(len(result.storage_purge_errors), 1, "a shortfall must never come back with no error")
        self.assertIn("1 of 3", result.storage_purge_errors[0])
        warn.assert_called_once()
        self.assertEqual(result.storage_objects_purged + len(result.unpurged_uris), result.storage_objects_found)

    def test_zero_purged_without_raising_is_worded_correctly(self):
        """Line-by-line review: the seam's contract permits returning `[]` (purged nothing)
        WITHOUT raising -- the original wording always said '...for the rest', which is false
        when nothing was purged at all."""
        uris = ["t/p/a", "t/p/b"]
        store = self._store_with_uris(uris)
        with patch.object(store, "_purge_storage_objects", return_value=[]):
            result = store.delete_project(Project(id="proj-1"))
        self.assertEqual(result.storage_objects_purged, 0)
        self.assertEqual(result.unpurged_uris, uris)
        self.assertEqual(len(result.storage_purge_errors), 1)
        self.assertNotIn("for the rest", result.storage_purge_errors[0])
        self.assertIn("no successes", result.storage_purge_errors[0])

    def test_full_purge_reports_no_error_and_no_log(self):
        uris = ["t/p/a", "t/p/b"]
        store = self._store_with_uris(uris)
        with patch.object(store, "_purge_storage_objects", return_value=list(uris)):
            with patch.object(supabase_model_store.logger, "warning") as warn:
                result = store.delete_project(Project(id="proj-1"))
        self.assertEqual(result.storage_objects_purged, 2)
        self.assertEqual(result.unpurged_uris, [])
        self.assertEqual(result.storage_purge_errors, [])
        warn.assert_not_called()

    def test_a_seam_returning_the_wrong_shape_is_recorded_as_a_failure(self):
        """The seam's contract is 'return the list of uris you purged'. A count (the old
        int contract), or uris that were never passed in, is a broken seam: recorded as a
        failed purge with every uri kept -- never a crash after the rows are already gone."""
        for label, bad in {"old int contract": 2, "uri never passed in": ["t/p/zzz"], "None": None}.items():
            with self.subTest(label):
                store = self._store_with_uris(["t/p/a", "t/p/b"])
                with patch.object(store, "_purge_storage_objects", return_value=bad):
                    result = store.delete_project(Project(id="proj-1"))
                self.assertTrue(result.project_deleted)
                self.assertEqual(result.storage_objects_purged, 0)
                self.assertEqual(result.unpurged_uris, ["t/p/a", "t/p/b"])
                self.assertEqual(len(result.storage_purge_errors), 1)

    def test_no_uris_means_nothing_unpurged_and_nothing_logged(self):
        client = _FakeClient(table_data={}, rpc_result={
            "project_deleted": True, "source_document_uris": [],
        })
        store = _make_store(client)
        # NOT `assertNoLogs`: that is Python 3.10+, and the merge gate can run on an older
        # interpreter (Bifola's macOS stock python3 is 3.9.6, below our own requires-python).
        # Patching THIS module's logger is portable and asserts something sharper: that this
        # logger stayed silent, not merely that no WARNING reached a logger of that name.
        with patch.object(supabase_model_store.logger, "warning") as warn:
            result = store.delete_project(Project(id="proj-1"))
        warn.assert_not_called()
        self.assertEqual(result.unpurged_uris, [])

    def test_dict_shaped_junk_responses_fail_closed(self):
        """Bifola's PR #200 review, finding 2. The RPC ALWAYS returns
        {'project_deleted': bool, 'source_document_uris': [str, ...]}, so each of these is a
        malformed response and must raise -- NOT degrade into a `project_deleted=False` that
        looks like a legitimate "not your project" no-op (or, for "false", into True)."""
        junk = {
            "list-wrapped empty dict": [{}],
            "empty dict": {},
            "unrelated keys": {"foo": 1},
            "missing uris key": {"project_deleted": True},
            "missing project_deleted key": {"source_document_uris": []},
            "truthy string project_deleted": {"project_deleted": "false", "source_document_uris": []},
            "int project_deleted": {"project_deleted": 1, "source_document_uris": []},
            "string instead of uri list": {"project_deleted": True, "source_document_uris": "s3://a"},
            "None uri list": {"project_deleted": True, "source_document_uris": None},
            "non-string uri element": {"project_deleted": True, "source_document_uris": ["ok", 7]},
            "empty-string uri": {"project_deleted": True, "source_document_uris": [""]},
            "not deleted yet carries uris": {"project_deleted": False, "source_document_uris": ["a.txt"]},
            "duplicate uri": {"project_deleted": True, "source_document_uris": ["a.txt", "a.txt"]},
        }
        for label, response in junk.items():
            with self.subTest(label):
                client = _FakeClient(table_data={}, rpc_result=response)
                store = _make_store(client)
                with self.assertRaises(RuntimeError):
                    store.delete_project(Project(id="proj-1"))

    def test_malformed_response_is_logged_before_raising(self):
        """Removed-behavior review: the exception message embeds the raw response, but a
        caller that doesn't log the exception itself would lose it -- the same reason a
        failed purge is logged separately from being put in the return value."""
        client = _FakeClient(table_data={}, rpc_result={"project_deleted": True, "source_document_uris": "not-a-list"})
        store = _make_store(client)
        with patch.object(supabase_model_store.logger, "warning") as warn:
            with self.assertRaises(RuntimeError):
                store.delete_project(Project(id="proj-1"))
        warn.assert_called_once()
        self.assertIn("not-a-list", str(warn.call_args))

    def test_purge_storage_objects_seam_raises_storage_not_configured(self):
        client = _FakeClient(table_data={}, rpc_result={"project_deleted": True, "source_document_uris": []})
        store = _make_store(client)
        with self.assertRaises(StorageNotConfiguredError):
            store._purge_storage_objects(["t1/p1/a.txt"])


if __name__ == "__main__":
    unittest.main()
