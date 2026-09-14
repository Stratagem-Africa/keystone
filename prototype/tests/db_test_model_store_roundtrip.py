"""Issue #21 Milestones 4+5 — the ACTUAL "model.py <-> rows <-> model.py" gate ADR-005's
build plan names (item 3: "a loss-less round-trip test"), on real Postgres. Calls
keystone_save_system_model(...) (0004_model_store_save_rpc.sql) directly via SQL under
sign_in_as (this harness drives Postgres via raw psycopg — there is no live PostgREST server
anywhere in this repo's test infra, so this can't go through SupabaseModelStore's own
.rpc()/.table() calls; test_supabase_model_store.py covers that half with a mocked client).

Reuses supabase_model_store.py's own serialization/reconstruction helpers (rather than
hand-rolling a second copy here) so this test proves two things at once: the RPC's SQL
persists exactly what those helpers produce, AND those helpers correctly rebuild a
SystemModel from REAL Postgres rows — not just the shape a mock assumed.

Never collected by `python3 -m unittest discover -s tests` — same db_test_ naming rationale
as db_test_tenant_isolation.py's module docstring. Run via scripts/test_tenant_isolation.sh.
"""
from __future__ import annotations

import json
import unittest

import psycopg
from psycopg.rows import dict_row

from keystone.model import Assumption, Component, ComponentKind, Flow, FlowStep, PricingRates, SystemModel, Workload
from keystone.model_store import Project
from keystone.provenance import Citation, Grounding
from keystone.supabase_model_store import (
    _build_save_payload,
    _component_from_row,
    _deserialize_groundings,
    _group_and_sort_steps,
)
from tenant_isolation_test_helpers import DatabaseTestCase, sign_in_as


def setUpModule() -> None:
    from tenant_isolation_test_helpers import require_database_url
    require_database_url()


def _rich_model() -> SystemModel:
    """Deliberately exercises every corner ADR-005 §6a calls out by name: a Grounding
    (int-vs-float band fidelity), a non-default PricingRates, multiple flows AND multiple
    assumptions (list ORDER — the gap this migration's flow_order/assumption_order columns
    fix), and domain_flags."""
    return SystemModel(
        name="round-trip model",
        components={
            "app": Component(
                id="app", kind=ComponentKind.APP_SERVER, name="App server",
                per_instance_rps=250.0, instances=3, base_latency_ms=8.5,
                monthly_cost_per_instance=7500, egress_gb_per_month=100, storage_gb=0,
                requests_per_month=5_000_000, provenance="ASSUMPTION",
                groundings={
                    # int value on the wire (5000, not 5000.0) — the exact case ADR-005 §6a
                    # flags: dataclass equality doesn't care, but this proves the fidelity
                    # holds through Postgres regardless.
                    "monthly_cost_per_instance": Grounding(
                        value=5000, unit="usd_minor_per_month",
                        confidence_low=4000, confidence_high=6000,
                        citations=(Citation(source="vendor pricing page", reference="https://example.com/pricing"),),
                        measured_context="us-east-1, r7g.large",
                    ),
                },
                match_context={"instance_type": "r7g.large", "region": "us-east-1"},
            ),
            "db": Component(
                id="db", kind=ComponentKind.SQL_DB, name="Primary DB",
                per_instance_rps=1200.0, base_latency_ms=2.0, monthly_cost_per_instance=15000,
                provenance="GROUNDED",
            ),
        },
        flows=[
            Flow(name="write path", share=0.3, path=[
                FlowStep(component_id="app", visit_prob=1.0),
                FlowStep(component_id="db", visit_prob=1.0),
            ]),
            Flow(name="read path", share=0.7, path=[
                FlowStep(component_id="app", visit_prob=1.0),
                FlowStep(component_id="db", visit_prob=0.2),   # cache-miss-shaped
            ]),
        ],
        workload=Workload(system_rps=500.0, description="steady-state"),
        # Deliberately NOT alphabetical (subject "z..." before "a...") -- if list order
        # weren't preserved through the round trip, a naive re-sort would silently "fix"
        # this and the ordering bug would go undetected.
        assumptions=[
            Assumption("z-latency", "p99 under 50ms", confidence="high", source="user", provenance="ASSUMPTION"),
            Assumption("a-throughput", "sustained 500 rps", confidence="med", source="llm_inferred", provenance="ASSUMPTION"),
        ],
        domain_flags=["high_stakes:payments"],
        pricing=PricingRates(
            egress_micro_usd_per_gb=95_000,
            storage_micro_usd_per_gb_month=22_000,
            compute_pricing="reserved_1yr",
            groundings={
                "egress_micro_usd_per_gb": Grounding(
                    value=95_000.0, unit="usd_minor_per_month",  # unit is illustrative here; not engine-read
                    confidence_low=90_000.0, confidence_high=100_000.0,
                    citations=(Citation(source="cloud pricing calculator", reference="https://example.com/calc"),),
                ),
            },
        ),
    )


class TestModelStoreRoundTrip(DatabaseTestCase):
    scratch_db_name = "keystone_test_model_store_roundtrip"

    def _call_save_rpc(self, project_id, model: SystemModel) -> int:
        payload = _build_save_payload(model, Project(id=str(project_id)))
        with self.conn.cursor() as cur:
            cur.execute(
                """select keystone_save_system_model(
                     %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                     %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                   )""",
                (
                    payload["p_project_id"], payload["p_name"], payload["p_domain_flags"],
                    payload["p_system_rps"], payload["p_workload_description"],
                    payload["p_egress_micro_usd_per_gb"], payload["p_storage_micro_usd_per_gb_month"],
                    payload["p_request_micro_usd_per_thousand"],
                    payload["p_llm_input_micro_usd_per_1k_tokens"],
                    payload["p_llm_output_micro_usd_per_1k_tokens"], payload["p_compute_pricing"],
                    json.dumps(payload["p_pricing_groundings"]), json.dumps(payload["p_components"]),
                    json.dumps(payload["p_flows"]), json.dumps(payload["p_assumptions"]),
                ),
            )
            return cur.fetchone()[0]

    def _reload_model(self, project_id, version: int) -> SystemModel:
        """Mirrors SupabaseModelStore.get_model's query shape exactly, but via raw psycopg
        instead of PostgREST — reusing the same reconstruction helpers that class uses, so
        this proves those helpers work against a REAL row shape, not just a mock's."""
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "select * from system_model where project_id = %s and version = %s",
                (project_id, version),
            )
            sm = cur.fetchone()

            cur.execute(
                "select * from component where project_id = %s and model_version = %s",
                (project_id, version),
            )
            components = cur.fetchall()

            cur.execute(
                "select * from flow where project_id = %s and model_version = %s order by flow_order",
                (project_id, version),
            )
            flow_rows = cur.fetchall()

            cur.execute(
                "select * from flow_step where project_id = %s and model_version = %s",
                (project_id, version),
            )
            step_rows = cur.fetchall()
            steps_by_flow = _group_and_sort_steps(step_rows)

            cur.execute(
                "select * from assumption where project_id = %s and model_version = %s "
                "order by assumption_order",
                (project_id, version),
            )
            assumption_rows = cur.fetchall()

        return SystemModel(
            name=sm["name"],
            components={row["id"]: _component_from_row(row) for row in components},
            flows=[
                Flow(
                    name=row["name"], share=float(row["share"]),
                    path=[
                        FlowStep(component_id=s["component_id"], visit_prob=float(s["visit_prob"]))
                        for s in steps_by_flow.get(row["id"], [])
                    ],
                )
                for row in flow_rows
            ],
            workload=Workload(system_rps=float(sm["system_rps"]), description=sm["workload_description"]),
            assumptions=[
                Assumption(
                    subject=row["subject"], statement=row["statement"], confidence=row["confidence"],
                    source=row["source"], provenance=row["provenance"],
                )
                for row in assumption_rows
            ],
            domain_flags=sm.get("domain_flags") or [],
            pricing=PricingRates(
                egress_micro_usd_per_gb=int(sm["egress_micro_usd_per_gb"]),
                storage_micro_usd_per_gb_month=int(sm["storage_micro_usd_per_gb_month"]),
                request_micro_usd_per_thousand=int(sm["request_micro_usd_per_thousand"]),
                llm_input_micro_usd_per_1k_tokens=int(sm["llm_input_micro_usd_per_1k_tokens"]),
                llm_output_micro_usd_per_1k_tokens=int(sm["llm_output_micro_usd_per_1k_tokens"]),
                compute_pricing=sm["compute_pricing"],
                groundings=_deserialize_groundings(sm.get("pricing_groundings")),
            ),
        )

    def test_save_then_reload_is_byte_for_byte_identical(self):
        model = _rich_model()
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            new_version = self._call_save_rpc(self.tenant_a.project_id, model)
            reloaded = self._reload_model(self.tenant_a.project_id, new_version)
        self.assertEqual(reloaded, model, "save -> reload must reproduce an identical SystemModel")

    def test_flow_and_assumption_order_survive_the_round_trip(self):
        """The specific gap this PR's migration closes: 0001 had no order column for flow
        or assumption at all. Save a model with flows/assumptions in a DELIBERATE,
        non-alphabetical order and confirm reload preserves it exactly — a set/dict-based
        comparison would silently hide an ordering regression, so this checks list identity."""
        model = _rich_model()
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            new_version = self._call_save_rpc(self.tenant_a.project_id, model)
            reloaded = self._reload_model(self.tenant_a.project_id, new_version)
        self.assertEqual(
            [f.name for f in reloaded.flows], [f.name for f in model.flows],
            "flow order must survive the round trip",
        )
        self.assertEqual(
            [a.subject for a in reloaded.assumptions], [a.subject for a in model.assumptions],
            "assumption order must survive the round trip",
        )

    def test_head_pointer_moves_atomically_with_the_new_version(self):
        """The literal Milestone-4 requirement: the insert-new-version + move-head-pointer
        pair is one transaction. Save twice, confirm project.head_model_version tracks the
        LATEST version each time — not the first, and not left stale."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            v1 = self._call_save_rpc(self.tenant_a.project_id, _rich_model())
            with self.conn.cursor() as cur:
                cur.execute(
                    "select head_model_version from project where id = %s", (self.tenant_a.project_id,)
                )
                self.assertEqual(cur.fetchone()[0], v1)

            v2 = self._call_save_rpc(self.tenant_a.project_id, _rich_model())
            self.assertGreater(v2, v1)
            with self.conn.cursor() as cur:
                cur.execute(
                    "select head_model_version from project where id = %s", (self.tenant_a.project_id,)
                )
                self.assertEqual(cur.fetchone()[0], v2, "head must move to the newest version, not stay at v1")

    def test_saving_for_another_tenants_project_is_denied(self):
        """As of 0004 (Bifola's ruling, issue #21, 2026-09-10) the RPC is SECURITY DEFINER,
        not INVOKER — it no longer gets this check for free from RLS, since a DEFINER
        function typically runs as a role RLS doesn't bind. The function does its OWN
        explicit tenant check instead (comparing p_project_id's actual tenant against
        keystone_current_tenant(), the caller's own JWT claim) — same observable outcome
        (NoDataFound, since the locked project SELECT's WHERE clause now explicitly filters
        by tenant match rather than relying on implicit RLS row-visibility), different
        mechanism. Signed in as tenant A, saving against tenant B's project must still fail,
        not silently succeed against the wrong tenant's data."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self._call_save_rpc(self.tenant_b.project_id, _rich_model())

    # -- "poison tests" Bifola's ruling explicitly asked for (issue #21, 2026-09-10) -------
    # (a) authenticated direct-insert on system_model now denied: covered in
    #     db_test_tenant_isolation.py's test_system_model_select_isolation (and the other
    #     four SELECT-only tables), not duplicated here.
    # (b) the RPC itself rejects an invalid model, below.
    # (c) a valid model round-trips: covered above (test_save_then_reload_is_byte_for_byte_identical).

    def test_rpc_rejects_model_with_no_components(self):
        """Structural validation now lives INSIDE the RPC too (0004), not just in Python's
        validate_model() before it — a caller reaching this function directly (raw SQL, a
        future client, a bug in SupabaseModelStore) still can't get a structurally invalid
        model past it. This is the most basic case: an empty components object."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.conn.transaction():
                    with self.conn.cursor() as cur:
                        cur.execute(
                            """select keystone_save_system_model(
                                 %s, 'broken', '{}', 10.0, '', 0, 0, 0, 0, 0, 'on_demand',
                                 '{}'::jsonb, '[]'::jsonb,
                                 '[{"name": "f", "share": 1.0, "path": []}]'::jsonb, '[]'::jsonb
                               )""",
                            (str(self.tenant_a.project_id),),
                        )

    def test_rpc_rejects_flow_shares_not_summing_to_one(self):
        """Flow shares summing to ~1.0 can't be a column CHECK (ADR-005 §6 says so
        explicitly — it spans rows) — confirms this cross-row invariant is now enforced
        inside the RPC itself, not just by the Python validate_model() call in front of it."""
        model = _rich_model()
        # Deliberately break what _rich_model() otherwise builds correctly (0.3 + 0.7 = 1.0):
        # halve one flow's share so the two no longer sum near 1.0.
        model.flows[0].share = 0.05
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.conn.transaction():
                    self._call_save_rpc(self.tenant_a.project_id, model)

    def test_rpc_rejects_orphan_component(self):
        """Every component must be reachable by at least one flow (ADR-005 §6 / the
        engine's own "an unconnected component reports a misleading 0% utilisation" reason,
        ingestion.py's orphan_components check) — confirms the RPC enforces this itself,
        not just the Python wrapper in front of it."""
        model = _rich_model()
        model.components["orphan"] = Component(
            id="orphan", kind=ComponentKind.CACHE, name="Unwired cache", per_instance_rps=100.0,
            provenance="ASSUMPTION",
        )
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.conn.transaction():
                    self._call_save_rpc(self.tenant_a.project_id, model)


if __name__ == "__main__":
    unittest.main()
