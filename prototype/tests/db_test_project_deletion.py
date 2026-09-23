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

import threading
import time
import unittest
import uuid

import psycopg

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

    def _add_project_with_documents(self, tenant, uris) -> "uuid.UUID":
        """A second project in the SAME tenant with one source_document per uri. Inserted as
        the harness superuser (before any sign_in_as), like seed_tenant -- source_document's
        tenant_id is trigger-derived from project_id."""
        project_id = self.cur.execute(
            "insert into project (tenant_id, owner_id, name) values (%s, %s, %s) returning id",
            (tenant.tenant_id, tenant.user_id, "extra-project"),
        ).fetchone()[0]
        for uri in uris:
            self.cur.execute(
                "insert into source_document (project_id, type, uri, checksum) "
                "values (%s, 'text', %s, 'deadbeef')",
                (project_id, uri),
            )
        return project_id

    def test_rpc_excludes_a_uri_a_surviving_row_still_points_at(self):
        """Bifola's PR #200 review, decision 3: `uri` has no UNIQUE constraint, so two
        documents can share one object. The list is the contract a future purge trusts, so it
        must mean "safe to purge", not merely "this project referenced it"."""
        own_uri = f"{self.tenant_a.tenant_id}/{self.tenant_a.project_id}/note.txt"   # seed_tenant's own row
        shared_uri = "shared/object.pdf"
        # The project being deleted also gets the shared uri; a SECOND project keeps a row
        # pointing at it. (Inserted while still superuser, before sign_in_as.)
        self.cur.execute(
            "insert into source_document (project_id, type, uri, checksum) "
            "values (%s, 'text', %s, 'deadbeef')",
            (self.tenant_a.project_id, shared_uri),
        )
        self._add_project_with_documents(self.tenant_a, [shared_uri])

        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            result = self._call_rpc(self.tenant_a.project_id)

        self.assertTrue(result["project_deleted"])
        self.assertEqual(
            result["source_document_uris"], [own_uri],
            "the shared uri must be withheld -- another row still uses that object",
        )

    def test_rpc_returns_each_uri_once_even_if_a_project_repeats_it(self):
        own_uri = f"{self.tenant_a.tenant_id}/{self.tenant_a.project_id}/note.txt"
        self.cur.execute(
            "insert into source_document (project_id, type, uri, checksum) "
            "values (%s, 'text', %s, 'cafef00d')",
            (self.tenant_a.project_id, own_uri),   # a second row with the seeded row's exact uri
        )
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            result = self._call_rpc(self.tenant_a.project_id)
        self.assertEqual(result["source_document_uris"], [own_uri])

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


class TestSharedUriConcurrentDeletes(DatabaseTestCase):
    """Two projects share one uri and are deleted CONCURRENTLY. Own class because it must
    COMMIT its seed data (a second connection can't see the base class's uncommitted rows);
    the scratch database is dropped at class teardown, so that leaks nothing.

    Regression for the independent review of the survivor filter: under READ COMMITTED each
    deleter used to see the OTHER's not-yet-committed row as a survivor, so both withheld the
    uri and the object was orphaned with no record. The FOR UPDATE on uri-sharing rows makes
    the second deleter wait, then re-read, so the LAST deleter reports the shared uri."""

    scratch_db_name = "keystone_test_delete_project_concurrency"

    def tearDown(self) -> None:
        # Every test in this class COMMITS (needed so a second, real connection can see the
        # seed data) -- which makes DatabaseTestCase's usual tearDown `rollback()` a NO-OP
        # here, so committed rows would otherwise accumulate across this class's test methods
        # for the rest of the run (found by line-by-line review). RLS means a later test's
        # freshly-`seed_tenant`-minted tenant can't actually SEE an earlier test's leftover
        # rows (different tenant_id each time), so this was inert today, not a live bug -- but
        # relying on that instead of real isolation is fragile, so clean up explicitly as
        # superuser (self.cur's role is already back to superuser here -- every sign_in_as
        # block in this class's tests resets it on exit before the test method returns).
        self.cur.execute("delete from project where tenant_id = %s", (self.tenant_a.tenant_id,))
        self.conn.commit()
        super().tearDown()

    def _new_project_with_doc(self, uri: str):
        tenant = self.tenant_a
        project_id = self.cur.execute(
            "insert into project (tenant_id, owner_id, name) values (%s, %s, %s) returning id",
            (tenant.tenant_id, tenant.user_id, "shared-uri-project"),
        ).fetchone()[0]
        self.cur.execute(
            "insert into source_document (project_id, type, uri, checksum) "
            "values (%s, 'text', %s, 'deadbeef')",
            (project_id, uri),
        )
        return project_id

    def _start_deleter(self, project_id, outcome: dict, key: str = "second") -> threading.Thread:
        """Run keystone_delete_project(project_id) as tenant A on its OWN connection/thread,
        leaving the result (or the exception, surfaced by the caller's assertions rather than
        swallowed) in `outcome`."""
        def run() -> None:
            try:
                with psycopg.connect(self.db_url, autocommit=False) as conn2:
                    cur2 = conn2.cursor()
                    with sign_in_as(cur2, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
                        cur2.execute("select keystone_delete_project(%s)", (project_id,))
                        outcome[key] = cur2.fetchone()[0]
                    conn2.commit()
            except Exception as exc:
                outcome["error"] = exc

        thread = threading.Thread(target=run)
        thread.start()
        return thread

    def _wait_for_lock_waiter(self, *, timeout: float, thread: threading.Thread) -> bool:
        deadline = time.monotonic() + timeout
        with psycopg.connect(self.db_url, autocommit=True) as admin:   # separate conn: leaves txn 1 untouched
            while time.monotonic() < deadline:
                waiting = admin.execute(
                    "select count(*) from pg_stat_activity "
                    "where datname = current_database() and wait_event_type = 'Lock'"
                ).fetchone()[0]
                if waiting:
                    return True
                if not thread.is_alive():   # finished (or died) without ever waiting
                    return False
                time.sleep(0.05)
        return False

    def test_last_deleter_of_a_shared_uri_reports_it(self):
        shared = "shared/object.pdf"
        project_a = self._new_project_with_doc(shared)
        project_b = self._new_project_with_doc(shared)
        self.conn.commit()   # make the seed visible to the second connection

        outcome: dict = {}

        # Transaction 1: delete A and leave the transaction OPEN (holding its locks).
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("select keystone_delete_project(%s)", (project_a,))
            first = self.cur.fetchone()[0]

        thread = self._start_deleter(project_b, outcome)
        # Wait until Postgres itself reports a backend waiting on a lock -- proof the second
        # deleter is genuinely blocked on the first's rows, not just "slow" -- instead of a
        # fixed sleep (which on a slow box could commit transaction 1 before the second one
        # ever reached the lock, passing without exercising the race).
        blocked = self._wait_for_lock_waiter(timeout=10.0, thread=thread)
        self.assertNotIn("error", outcome, f"second deleter raised instead of blocking: {outcome.get('error')!r}")
        self.assertTrue(
            blocked,
            "the second deleter must BLOCK on the first's row locks; if no backend ever waited, "
            "nothing stopped it reading A's not-yet-committed row as a survivor",
        )
        self.conn.commit()   # transaction 1 commits -> the second deleter unblocks
        thread.join(timeout=15)
        self.assertFalse(thread.is_alive(), "second deleter never unblocked")
        self.assertNotIn("error", outcome, outcome.get("error"))

        self.assertEqual(first["source_document_uris"], [], "B still referenced the uri when A was deleted")
        self.assertEqual(
            outcome["second"]["source_document_uris"], [shared],
            "the LAST deleter of a shared uri must report it -- otherwise the object is orphaned",
        )

    def test_project_row_lock_makes_a_racing_insert_visible_to_the_deleter(self):
        """Covers the FOR UPDATE on the project row (0006's first statement) -- Bifola's PR #200
        re-review, #2: deleting that line left all 46 DB tests green, because the shared-uri
        test above targets two DIFFERENT projects so their project-row locks never contend.

        A writer inserts a second document for project A and holds its transaction OPEN (the
        FK check takes a KEY SHARE lock on A's project row). The delete must wait for it and
        then SEE that document. Asserting only "it blocked" would not do: without the
        project-row lock the RPC still blocks -- later, at the `delete`, on the same KEY SHARE
        lock -- but by then it has already read its uri list, so the cascade deletes the racing
        document unreported (an orphaned Storage object with no record). Only the returned
        list tells the two apart."""
        own_uri, racing_uri = "own/doc.pdf", "racing/late-upload.pdf"
        project_a = self._new_project_with_doc(own_uri)
        self.conn.commit()   # visible to the deleter's connection

        # The writer: a second document for A, transaction left open.
        self.cur.execute(
            "insert into source_document (project_id, type, uri, checksum) "
            "values (%s, 'text', %s, 'deadbeef')",
            (project_a, racing_uri),
        )

        outcome: dict = {}
        thread = self._start_deleter(project_a, outcome)
        blocked = self._wait_for_lock_waiter(timeout=10.0, thread=thread)
        self.assertNotIn("error", outcome, f"deleter raised instead of blocking: {outcome.get('error')!r}")
        self.assertTrue(blocked, "the deleter must wait for the writer's open transaction")
        self.conn.commit()   # the writer commits -> the deleter unblocks
        thread.join(timeout=15)
        self.assertFalse(thread.is_alive(), "deleter never unblocked")
        self.assertNotIn("error", outcome, outcome.get("error"))

        result = outcome["second"]
        self.assertTrue(result["project_deleted"])
        self.assertEqual(
            sorted(result["source_document_uris"]), sorted([own_uri, racing_uri]),
            "the racing document was cascade-deleted but never reported -- the project-row "
            "lock is what makes the deleter wait BEFORE it reads its uri list",
        )


if __name__ == "__main__":
    unittest.main()
