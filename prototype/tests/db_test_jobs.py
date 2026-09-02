"""Harm-floor gate for the `jobs` table (issue #87, PR #161 review) — proves the real
per-user RLS policy in 0003_jobs_table.sql actually isolates rows, the same way
db_test_tenant_isolation.py proves it for the 0001 tables.

Never collected by `python3 -m unittest discover -s tests` (scripts/check.sh's default
pattern is test*.py) — run explicitly via scripts/test_tenant_isolation.sh, which passes
`-p "db_test_*.py"`. See tenant_isolation_test_helpers.py's module docstring for the full
repeatability strategy.

jobs is scoped by user_id = auth.uid() (own_jobs policy), not tenant_id — genuinely
different from every 0001 table, same distinction db_test_tenant_isolation.py already
draws for `membership`'s own_memberships policy. Reuses DatabaseTestCase's tenant-a/
tenant-b fixtures purely as a convenient source of two distinct real `auth.users` rows
(via seed_tenant) — nothing about tenant/project/system_model itself is under test here.
"""
from __future__ import annotations

import unittest
import uuid

import psycopg

from tenant_isolation_test_helpers import DatabaseTestCase, sign_in_as


def setUpModule() -> None:
    from tenant_isolation_test_helpers import require_database_url
    require_database_url()  # fail loudly (RuntimeError) before any class/connection attempt


class TestJobsIsolation(DatabaseTestCase):
    scratch_db_name = "keystone_test_db_test_jobs"

    def _insert_job(self, *, as_user, tenant_id, intent_text="test intent") -> uuid.UUID:
        job_id = uuid.uuid4()
        with sign_in_as(self.cur, user_id=as_user, tenant_id=tenant_id):
            self.cur.execute(
                "insert into jobs (job_id, user_id, intent_text) values (%s, %s, %s)",
                (job_id, as_user, intent_text),
            )
        return job_id

    def test_user_can_insert_and_read_their_own_job(self):
        job_id = self._insert_job(as_user=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id)
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("select user_id, status from jobs where job_id = %s", (job_id,))
            row = self.cur.fetchone()
        self.assertIsNotNone(row, "the owner must be able to read their own job")
        self.assertEqual(row[0], self.tenant_a.user_id)
        self.assertEqual(row[1], "queued")   # column default

    def test_user_sees_zero_of_another_users_jobs(self):
        job_id = self._insert_job(as_user=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id)
        with sign_in_as(self.cur, user_id=self.tenant_b.user_id, tenant_id=self.tenant_b.tenant_id):
            self.cur.execute("select * from jobs where job_id = %s", (job_id,))
            rows = self.cur.fetchall()
        self.assertEqual(rows, [], "B must see zero of A's job rows (RLS filters, not an error)")

    def test_user_cannot_update_another_users_job(self):
        job_id = self._insert_job(as_user=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id)
        with sign_in_as(self.cur, user_id=self.tenant_b.user_id, tenant_id=self.tenant_b.tenant_id):
            self.cur.execute("update jobs set status = 'done' where job_id = %s", (job_id,))
            self.assertEqual(self.cur.rowcount, 0, "UPDATE of A's job by B must affect 0 rows")
        # confirm it's genuinely untouched, reading back as the real owner
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute("select status from jobs where job_id = %s", (job_id,))
            row = self.cur.fetchone()
        self.assertEqual(row[0], "queued")

    def test_insert_cannot_forge_another_users_ownership(self):
        # Even if the app sent someone else's user_id (a bug, or an attacker tampering with
        # the request body), trg_jobs_derive_owner overwrites it with auth.uid() -- the row
        # ends up owned by the ACTUAL caller, never who the payload claimed.
        job_id = uuid.uuid4()
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "insert into jobs (job_id, user_id, intent_text) values (%s, %s, %s)",
                (job_id, self.tenant_b.user_id, "forged ownership attempt"),
            )
            self.cur.execute("select user_id from jobs where job_id = %s", (job_id,))
            row = self.cur.fetchone()
        self.assertEqual(row[0], self.tenant_a.user_id, "the trigger must win, not the payload")

    def test_anon_role_gets_no_access_at_all(self):
        job_id = self._insert_job(as_user=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id)
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=None, role="anon"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute("select * from jobs where job_id = %s", (job_id,))

    def test_update_cannot_reassign_ownership(self):
        # A user updating their OWN job can't hand it to someone else either -- the same
        # derive-trigger fires on UPDATE too (before insert OR update), not just INSERT.
        job_id = self._insert_job(as_user=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id)
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            self.cur.execute(
                "update jobs set user_id = %s where job_id = %s",
                (self.tenant_b.user_id, job_id),
            )
            self.cur.execute("select user_id from jobs where job_id = %s", (job_id,))
            row = self.cur.fetchone()
        self.assertEqual(row[0], self.tenant_a.user_id, "ownership must not be reassignable")


if __name__ == "__main__":
    unittest.main()
