"""ADR-005 §1b harm-floor gate: "signed in as tenant A, every table returns ZERO of tenant
B's rows on select / insert / update / delete (INSERT must be rejected by `with check`)."

Never collected by `python3 -m unittest discover -s tests` (scripts/check.sh's default
pattern is test*.py) — run explicitly via scripts/test_tenant_isolation.sh, which passes
`-p "db_test_*.py"`. See tenant_isolation_test_helpers.py's module docstring for the full
repeatability strategy and the things that still need verifying against a real Postgres.

0001's grants are NOT uniform across tables, so "every table" is tested against what's
actually grantable per table, not mechanically identical everywhere:
  - tenant, membership: SELECT only for `authenticated` — no write ops to test.
  - project, source_document: full CRUD — the full select/insert/update/delete matrix.
  - system_model, component, flow, flow_step, assumption: SELECT+INSERT only — UPDATE/DELETE
    aren't a cross-tenant test here, since there's no grant AT ALL, so even touching a row
    you own raises `permission denied` before RLS is ever evaluated (reinforcing ADR-005 §3's
    immutable-snapshot guarantee, a different property from §1b's tenant isolation).
  - simulation_run: SELECT only for `authenticated` (service_role's BYPASSRLS write path is
    explicitly out of scope for a DB-only harness — see the class docstring below).

One more subtlety worth being explicit about: Postgres uses the SAME SQLSTATE (42501,
insufficient_privilege) for both "no GRANT on this table" and "RLS with-check rejected this
row" — so `psycopg.errors.InsufficientPrivilege` is the right exception to assert in both
cases; it does not, by itself, tell you which of the two actually fired. Where that
distinction matters (proving a rejection is STRUCTURAL, not just a permission check), this
file uses `psycopg.errors.ForeignKeyViolation` (a genuinely different SQLSTATE, 23503)
instead — see the flow_step test at the bottom.

CONFIRMED ON A REAL RUN (Postgres 17): inserting a row tagged tenant B, while signed in as
tenant A, on any table whose tenant_id is DERIVED by a SECURITY INVOKER trigger (component,
flow, flow_step, assumption via keystone_derive_tenant_from_system_model /
keystone_derive_flow_step_scope; source_document via keystone_derive_tenant_from_project)
raises `psycopg.errors.NoDataFound` (SQLSTATE P0002), NOT InsufficientPrivilege. Reason: those
triggers are SECURITY INVOKER on purpose (Bifola's review: "makes a hidden cross-tenant parent
fail closed") — their own `select ... into strict` lookup runs under the CALLING role's RLS,
so looking up tenant B's parent row while signed in as A finds ZERO rows (A's RLS hides it),
and STRICT raises NO_DATA_FOUND before the with-check clause is ever reached. The write is
still correctly blocked either way; this is a different, EARLIER failure mode than the with-
check rejection tested directly on `project`/`source_document`/`system_model` (whose tenant_id
is app-supplied, not trigger-derived, so with-check is what actually fires there).
"""
from __future__ import annotations

import unittest

import psycopg

from tenant_isolation_test_helpers import DatabaseTestCase, sign_in_as


def setUpModule() -> None:
    from tenant_isolation_test_helpers import require_database_url
    require_database_url()  # fail loudly (RuntimeError) before any class/connection attempt


class TestTenantIsolation(DatabaseTestCase):
    scratch_db_name = "keystone_test_tenant_isolation"

    # -- tenant, membership: SELECT-only tables, isolated on different columns -----------

    def test_tenant_select_isolation(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("select id from tenant")
            rows = {r[0] for r in self.cur.fetchall()}
        self.assertEqual(rows, {self.tenant_a.tenant_id}, "A must see only A's own tenant row")

    def test_membership_select_isolation_by_user_not_tenant(self):
        # Isolation here is by user_id = auth.uid(), not tenant_id — a genuinely different
        # property from every other table (own_memberships policy, not tenant_isolation).
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("select user_id from membership")
            rows = {r[0] for r in self.cur.fetchall()}
        self.assertEqual(rows, {self.tenant_a.user_id}, "A must see only A's own membership row")

    # -- project, source_document: full CRUD, the full ADR-005 §1b matrix ----------------

    def test_project_full_crud_matrix(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            # SELECT: B invisible, A visible
            self.cur.execute("select id from project where id = %s", (self.tenant_b.project_id,))
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's project rows")
            self.cur.execute("select id from project where id = %s", (self.tenant_a.project_id,))
            self.assertEqual(len(self.cur.fetchall()), 1, "A must see A's own project row")

            # INSERT tagged tenant B -> rejected by `with check`
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into project (tenant_id, owner_id, name) values (%s, %s, 'evil')",
                        (self.tenant_b.tenant_id, self.tenant_a.user_id),
                    )

            # UPDATE / DELETE of B's row by id -> 0 rows affected, NOT an error (RLS makes
            # the row simply invisible to the WHERE clause, same as it not existing).
            self.cur.execute("update project set name = 'renamed' where id = %s", (self.tenant_b.project_id,))
            self.assertEqual(self.cur.rowcount, 0, "UPDATE of B's project must affect 0 rows")
            self.cur.execute("delete from project where id = %s", (self.tenant_b.project_id,))
            self.assertEqual(self.cur.rowcount, 0, "DELETE of B's project must affect 0 rows")

            # A's own writes succeed normally.
            self.cur.execute("update project set name = 'renamed' where id = %s", (self.tenant_a.project_id,))
            self.assertEqual(self.cur.rowcount, 1, "A must be able to update A's own project")

    def test_source_document_full_crud_matrix(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select id from source_document where id = %s", (self.tenant_b.source_document_id,)
            )
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's source_document rows")

            # NoDataFound, not InsufficientPrivilege: trg_source_document_tenant's lookup on
            # `project` (SECURITY INVOKER) can't see tenant B's project row under A's RLS —
            # see the module docstring's "CONFIRMED ON A REAL RUN" note.
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into source_document (project_id, type, uri, checksum) "
                        "values (%s, 'text', 'x', 'x')",
                        (self.tenant_b.project_id,),
                    )

            self.cur.execute(
                "update source_document set checksum = 'x' where id = %s",
                (self.tenant_b.source_document_id,),
            )
            self.assertEqual(self.cur.rowcount, 0)
            self.cur.execute("delete from source_document where id = %s", (self.tenant_b.source_document_id,))
            self.assertEqual(self.cur.rowcount, 0)

    # -- system_model, component, flow, flow_step, assumption: SELECT+INSERT only --------

    def _assert_own_row_write_denied_by_grant(self, update_sql: str, own_id) -> None:
        """UPDATE/DELETE on a SELECT+INSERT-only table: no grant exists at all, so even a
        row you legitimately own raises `permission denied` before RLS is ever consulted —
        ADR-005 §3's immutable-snapshot guarantee, not a §1b cross-tenant test."""
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.conn.transaction():
                self.cur.execute(update_sql, (own_id,))

    def test_system_model_select_insert_isolation(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select project_id from system_model where project_id = %s", (self.tenant_b.project_id,)
            )
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's system_model rows")

            # system_model has NO tenant-derivation trigger (its tenant_id is app-supplied,
            # not derived) — this is a direct with-check test, unlike the trigger-derived
            # tables below. tenant_id is set EXPLICITLY to B here (not omitted) so this test
            # actually exercises "tagged as tenant B", not an incidental NULL failure.
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into system_model (project_id, tenant_id, name, system_rps, "
                        "egress_micro_usd_per_gb, storage_micro_usd_per_gb_month, "
                        "request_micro_usd_per_thousand, llm_input_micro_usd_per_1k_tokens, "
                        "llm_output_micro_usd_per_1k_tokens) "
                        "values (%s, %s, 'evil', 1.0, 0, 0, 0, 0, 0)",
                        (self.tenant_b.project_id, self.tenant_b.tenant_id),
                    )

            self._assert_own_row_write_denied_by_grant(
                "update system_model set name = 'x' where project_id = %s", self.tenant_a.project_id
            )

    def test_component_select_insert_isolation(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select id from component where project_id = %s", (self.tenant_b.project_id,)
            )
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's component rows")

            # NoDataFound, not InsufficientPrivilege — see module docstring.
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into component (id, project_id, model_version, kind, name, "
                        "per_instance_rps, monthly_cost_per_instance, provenance) "
                        "values ('evil', %s, %s, 'app_server', 'evil', 1.0, 0, 'ASSUMPTION')",
                        (self.tenant_b.project_id, self.tenant_b.model_version),
                    )

            self._assert_own_row_write_denied_by_grant(
                "update component set name = 'x' where project_id = %s", self.tenant_a.project_id
            )

    def test_flow_select_insert_isolation(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("select id from flow where project_id = %s", (self.tenant_b.project_id,))
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's flow rows")

            # NoDataFound, not InsufficientPrivilege — see module docstring.
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into flow (project_id, model_version, name, share) "
                        "values (%s, %s, 'evil', 1.0)",
                        (self.tenant_b.project_id, self.tenant_b.model_version),
                    )

            self._assert_own_row_write_denied_by_grant(
                "update flow set name = 'x' where project_id = %s", self.tenant_a.project_id
            )

    def test_flow_step_select_insert_isolation(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select id from flow_step where flow_id = %s", (self.tenant_b.flow_id,)
            )
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's flow_step rows")

            # NoDataFound, not InsufficientPrivilege: keystone_derive_flow_step_scope's
            # lookup on `flow` (SECURITY INVOKER) can't see B's flow row under A's RLS —
            # same shape as component/flow/assumption/source_document, see module docstring.
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into flow_step (flow_id, component_id, step_order) "
                        "values (%s, 'evil', 99)",
                        (self.tenant_b.flow_id,),
                    )

            self._assert_own_row_write_denied_by_grant(
                "update flow_step set step_order = 1 where flow_id = %s", self.tenant_a.flow_id
            )

    def test_assumption_select_insert_isolation(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select id from assumption where project_id = %s", (self.tenant_b.project_id,)
            )
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's assumption rows")

            # NoDataFound, not InsufficientPrivilege — see module docstring.
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into assumption (project_id, model_version, subject, statement, "
                        "confidence, source, provenance) "
                        "values (%s, %s, 'x', 'x', 'med', 'user', 'ASSUMPTION')",
                        (self.tenant_b.project_id, self.tenant_b.model_version),
                    )

            self._assert_own_row_write_denied_by_grant(
                "update assumption set statement = 'x' where project_id = %s", self.tenant_a.project_id
            )

    # -- simulation_run: SELECT only for `authenticated` ----------------------------------

    def test_simulation_run_select_only_isolation(self):
        """`authenticated` has NO write grant here at all (ADR-005 §1b: "a DB privilege, not
        just RLS") — even A's OWN simulation_run row can't be written by a normal user login,
        which is the strongest form of the guarantee.

        Explicitly OUT OF SCOPE for this harness: `service_role`'s write-side tenant
        isolation. It carries BYPASSRLS by design (that's how the engine is allowed to write
        derived metrics at all), so no DB-level test could demonstrate isolation for it
        without just proving BYPASSRLS bypasses RLS — a tautology, not a gate. That guarantee
        is `SupabaseModelStore`'s application-layer tenant assertion
        (`project.tenant_id == caller.tenant_id`, checked in Python before every service-role
        write), which doesn't exist as code yet — a scope boundary, not a gap here."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select id from simulation_run where project_id = %s", (self.tenant_b.project_id,)
            )
            self.assertEqual(self.cur.fetchall(), [], "A must see zero of B's simulation_run rows")

            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute(
                        "update simulation_run set confidence = 'high' where project_id = %s",
                        (self.tenant_a.project_id,),
                    )

    # -- the structural test: flow_step's composite FK, not just RLS ----------------------

    def test_flow_step_component_id_cross_tenant_structurally_impossible(self):
        """Proves the flow_step composite FK — (project_id, model_version, component_id)
        references component(project_id, model_version, id) — makes a cross-tenant reference
        impossible to construct at all, not merely RLS-rejected. Both tenant A and tenant B's
        fixtures seed the SAME literal component id "app" (see seed_tenant's docstring) —
        the realistic collision this protection exists for.

        Three parts:
          1. A's own flow_step (already seeded in setUp, pointing at A's own "app" component)
             is visible and consistent — the composite FK correctly resolved to A's row.
          2. As a no-membership user (tenant_id=None — the hook's fail-closed state), every
             flow_step operation is denied, before any FK question is even reached.
          3. Directly pin the FK's existence/shape by provoking a genuine ForeignKeyViolation
             (23503) as superuser — orphaned (project_id, model_version, component_id) triple
             that matches no real component row. This is what distinguishes "structurally
             impossible" from "permission denied": a different SQLSTATE, not just a stricter
             grant.
        """
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "select component_id from flow_step where id = %s", (self.tenant_a.flow_step_id,)
            )
            self.assertEqual(self.cur.fetchone()[0], "app")

        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=None):
            # A bare SELECT never raises here — RLS just filters it to zero rows silently,
            # it doesn't error. The actual "every insert attempt fails" property (this
            # test's own claim) has to be proven with an INSERT instead.
            #
            # Expected exception is NoDataFound, NOT InsufficientPrivilege — and this is a
            # DIFFERENT reason than the other NoDataFound cases in this file: with NO claim
            # at all, keystone_current_tenant() is NULL, so `using (tenant_id = NULL)` fails
            # for EVERY row on `flow` for THIS session — including A's own flow_id used
            # below. keystone_derive_flow_step_scope's lookup on `flow` therefore finds zero
            # VISIBLE rows regardless of whose flow_id is passed, and STRICT raises
            # NO_DATA_FOUND before `with check` on flow_step is ever reached. (A genuinely
            # different failure path than "cross-tenant parent exists but isn't visible" —
            # here NOTHING is visible, not even your own data, which is the whole point of
            # the no-membership fail-closed state.)
            with self.assertRaises(psycopg.errors.NoDataFound):
                with self.conn.transaction():
                    self.cur.execute(
                        "insert into flow_step (flow_id, component_id, step_order) "
                        "values (%s, %s, 1)",
                        (self.tenant_a.flow_id, self.tenant_a.component_id),
                    )

        # superuser (RESET ROLE already happened on sign_in_as exit) — pin the FK itself
        self.cur.execute("RESET ROLE")
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.conn.transaction():
                self.cur.execute(
                    "insert into flow_step (flow_id, component_id, step_order) "
                    "values (%s, 'does-not-exist-anywhere', 99)",
                    (self.tenant_a.flow_id,),
                )


if __name__ == "__main__":
    unittest.main()
