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
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from keystone.ingestion import IngestError
from keystone.model import Component, ComponentKind, Flow, FlowStep, PricingRates, SystemModel, Workload
from keystone.model_store import Project
from keystone.provenance import Citation, Grounding
from keystone.supabase_model_store import SupabaseModelStore


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
    with patch.dict(os.environ, {"SUPABASE_URL": "http://example.test", "SUPABASE_ANON_KEY": "anon-key"}):
        with patch("supabase.create_client", return_value=fake_client):
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


if __name__ == "__main__":
    unittest.main()
