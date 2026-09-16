"""Issue #21 "Milestone 6" (ADR-005 §5, privacy + deletion) — the DB-row half of erasure,
on real Postgres.

Two things get proven here:
1. That deleting a `project` row, as its own tenant, actually reaches every `project_id`-
   scoped table down to zero rows — verified empirically, not assumed, because FK
   `ON DELETE CASCADE` reaching child tables `authenticated` holds NO direct write grant on
   (system_model/component/flow/flow_step/assumption/simulation_run, locked down by 0004)
   was a real open question before this file existed.
2. `keystone_delete_project` (0006) — the RPC `SupabaseModelStore.delete_project` calls —
   correctly collects `source_document.uri` values AND deletes the project row atomically,
   closing the two-call read-then-delete race a plain select-then-delete over PostgREST
   would have (found by independent review; see 0006's header for the full reasoning).

Scope note (posted to Bifola on #21, not yet answered as of this file landing): ADR-005 §5
also calls for actually purging the Storage/R2 objects these uris point at. That half has no
code to test yet — no Storage/R2 client exists anywhere in this repo, and nothing writes a
`source_document` row today (see `SupabaseModelStore._purge_storage_objects`'s docstring).

Never collected by `python3 -m unittest discover -s tests` — same db_test_ naming rationale as
db_test_tenant_isolation.py's module docstring. Run via scripts/test_tenant_isolation.sh.
"""
from __future__ import annotations

import unittest
import uuid

from tenant_isolation_test_helpers import DatabaseTestCase, sign_in_as


def setUpModule() -> None:
    from tenant_isolation_test_helpers import require_database_url
    require_database_url()


# Every table that carries a project_id and must reach zero rows once the owning project is
# gone. Order doesn't matter for the count check (cascade handles ordering internally); this
# list exists so a future table that gains a project_id FK and forgets ON DELETE CASCADE
# shows up here as a leftover row instead of silently passing.
_PROJECT_SCOPED_TABLES = (
    "system_model", "component", "flow", "flow_step",
    "assumption", "source_document", "simulation_run",
)


class TestProjectDeletion(DatabaseTestCase):
    scratch_db_name = "keystone_test_project_deletion"

    def _child_row_counts(self, project_id) -> dict[str, int]:
        # Runs on self.cur OUTSIDE any sign_in_as block, i.e. as the scratch database's
        # superuser owner — RLS-bypassing on purpose, so this checks what's ACTUALLY in the
        # tables, not what a particular tenant's RLS view would show (a cross-tenant delete
        # that silently failed but still hid the rows from the deleting tenant would pass a
        # RLS-scoped check and should not pass this one).
        counts = {}
        for table in _PROJECT_SCOPED_TABLES:
            self.cur.execute(f"select count(*) from {table} where project_id = %s", (project_id,))
            counts[table] = self.cur.fetchone()[0]
        return counts

    def test_deleting_own_project_purges_every_child_table(self):
        before = self._child_row_counts(self.tenant_a.project_id)
        self.assertTrue(all(n == 1 for n in before.values()), f"fixture setup assumption broken: {before}")

        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("delete from project where id = %s", (self.tenant_a.project_id,))
            self.assertEqual(self.cur.rowcount, 1)

        after = self._child_row_counts(self.tenant_a.project_id)
        self.assertEqual(
            after, {t: 0 for t in _PROJECT_SCOPED_TABLES},
            "every project_id-scoped table must reach zero rows -- ADR-005 §5 erasure",
        )
        self.cur.execute("select count(*) from project where id = %s", (self.tenant_a.project_id,))
        self.assertEqual(self.cur.fetchone()[0], 0)

    def test_deleting_another_tenants_project_is_denied(self):
        """RLS's existing tenant_isolation policy on `project` (0001) is what scopes
        erasure to the caller's own tenant -- a DELETE for a row outside it matches zero
        rows rather than raising (same shape as any other RLS-scoped DML), so the caller
        distinguishes this via rowcount, not an exception."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("delete from project where id = %s", (self.tenant_b.project_id,))
            self.assertEqual(self.cur.rowcount, 0)

        after = self._child_row_counts(self.tenant_b.project_id)
        self.assertEqual(after, {t: 1 for t in _PROJECT_SCOPED_TABLES}, "tenant B's rows must be untouched")
        self.cur.execute("select count(*) from project where id = %s", (self.tenant_b.project_id,))
        self.assertEqual(self.cur.fetchone()[0], 1)

    def test_deleting_a_nonexistent_project_is_a_no_op(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("delete from project where id = %s", (uuid.uuid4(),))
            self.assertEqual(self.cur.rowcount, 0)


class TestDeleteProjectRpc(DatabaseTestCase):
    """`keystone_delete_project` (0006) — the atomic collect-uris-then-delete RPC
    `SupabaseModelStore.delete_project` calls through `.rpc(...)`."""

    scratch_db_name = "keystone_test_delete_project_rpc"

    def _call_rpc(self, project_id):
        with self.conn.cursor() as cur:
            cur.execute("select keystone_delete_project(%s)", (project_id,))
            return cur.fetchone()[0]   # jsonb -> already a dict via psycopg's adapter

    def test_rpc_returns_uris_and_deletes_the_project(self):
        expected_uri = f"{self.tenant_a.tenant_id}/{self.tenant_a.project_id}/note.txt"
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            result = self._call_rpc(self.tenant_a.project_id)

        self.assertTrue(result["project_deleted"])
        self.assertEqual(result["source_document_uris"], [expected_uri])
        self.cur.execute(
            "select count(*) from system_model where project_id = %s", (self.tenant_a.project_id,)
        )
        self.assertEqual(self.cur.fetchone()[0], 0, "the cascade must have fired inside the RPC's own transaction")

    def test_rpc_denies_another_tenants_project(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            result = self._call_rpc(self.tenant_b.project_id)

        self.assertFalse(result["project_deleted"])
        self.assertEqual(result["source_document_uris"], [], "RLS hides B's rows from A's SELECT too")
        self.cur.execute("select count(*) from project where id = %s", (self.tenant_b.project_id,))
        self.assertEqual(self.cur.fetchone()[0], 1, "tenant B's project must be untouched")

    def test_rpc_on_nonexistent_project_is_a_no_op(self):
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            result = self._call_rpc(uuid.uuid4())
        self.assertFalse(result["project_deleted"])
        self.assertEqual(result["source_document_uris"], [])


if __name__ == "__main__":
    unittest.main()
