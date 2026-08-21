"""Issue #21 Milestone 3 — "the honesty wall": a user cannot fabricate or alter a persisted
engine number in simulation_run (the engine's results table), and every row is stamped with
the engine_version + seed that produced it (ADR-005 §1b/§3). "Keeps 'only the engine makes
numbers' true at the database level."

Narrowed wording per review: a user CAN remove their own simulation_run rows, by deleting
their whole project (project -> system_model -> simulation_run, both `on delete cascade`,
0001 lines 104 + 477) — that's intended (ADR-005 §5, cleaning up derived artifacts on
deletion) and leaves no false number behind, so "engine-write-only" over-claimed; what's
actually proven and actually matters is that content can't be faked or edited.

Confirmed directly against db/migrations/0001_canonical_model_store.sql that the schema
already satisfies this — it landed as part of Milestone 1 (#144), before Milestone 3 was ever
explicitly scoped: `authenticated` has SELECT only on simulation_run (no write grant at all),
`service_role` has full CRUD, and engine_version/seed are `not null` with no default. This
file is the dedicated, committed proof — the thing every other guarantee in this project has
gotten and this one hadn't yet, not a new migration.

Never collected by `python3 -m unittest discover -s tests` — same db_test_ naming rationale
as db_test_tenant_isolation.py's module docstring. Run via scripts/test_tenant_isolation.sh.
"""
from __future__ import annotations

import unittest

import psycopg

from tenant_isolation_test_helpers import DatabaseTestCase, sign_in_as


def setUpModule() -> None:
    from tenant_isolation_test_helpers import require_database_url
    require_database_url()


class TestSimulationRunHonesty(DatabaseTestCase):
    scratch_db_name = "keystone_test_simulation_run_honesty"

    def _insert_simulation_run(self, *, project_id, model_version, omit=None):
        """A full, well-formed simulation_run row for the given project/model_version, minus
        whichever column name is passed as `omit` (used to provoke NOT NULL violations on
        specific columns without duplicating this whole statement per column). Returns the
        new row's id (via `returning id`) so a caller can read back its OWN row precisely —
        seed_tenant() already seeds a simulation_run row with these exact default values
        (engine_version='test', seed=1), so identifying "my row" by shape instead of by id
        is genuinely ambiguous, not just untidy (see module history / PR review: this is
        exactly the bug that made test_service_role_can_write_simulation_run vacuous before
        this fix — both rows share a created_at, since seed_tenant's insert and this one run
        in the same transaction and Postgres's now() is transaction-start-time, not
        per-statement). The NOT-NULL tests below expect this call to raise before returning
        anything, so they never use the return value — no special-casing needed there."""
        columns = {
            "engine_version": "'test'",
            "seed": "1",
            "bottleneck_id": "'app'",
            "bottleneck_name": "'app'",
            "bottleneck_utilization": "0.5",
            "breakpoint_rps_safe": "100",
            "breakpoint_rps_theoretical": "100",
            "mean_latency_ms": "10",
            "p50_ms": "10",
            "p95_ms": "10",
            "p99_ms": "10",
            "monthly_cost": "500",
            "confidence": "'low'",
        }
        if omit is not None:
            del columns[omit]
        col_names = ", ".join(["project_id", "model_version", *columns.keys()])
        col_values = ", ".join(["%s", "%s", *columns.values()])
        self.cur.execute(
            f"insert into simulation_run ({col_names}) values ({col_values}) returning id",
            (project_id, model_version),
        )
        row = self.cur.fetchone()
        return row[0] if row else None

    def test_authenticated_cannot_insert_simulation_run(self):
        """The direct test of the literal Milestone 3 claim: a normal user login cannot
        fabricate a result — not even one tagged as their own project. `authenticated` has NO
        insert grant on simulation_run at all (0001 line 616), so this fails at the grant
        level before the BEFORE INSERT trigger (tenant derivation) is ever reached."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self._insert_simulation_run(
                        project_id=self.tenant_a.project_id, model_version=self.tenant_a.model_version
                    )

    def test_service_role_can_write_simulation_run(self):
        """The positive half of "user can't, engine can" — no existing test proves the engine
        path actually stays open, only that the user path is closed. service_role carries
        BYPASSRLS, so the tenant-derivation trigger's own lookup on system_model (itself
        SECURITY INVOKER) isn't restricted by RLS either — it can see tenant A's system_model
        row and derive tenant_id correctly regardless of who's asking.

        Reads back by the new row's OWN id, not by "most recent" — seed_tenant() already
        seeds tenant A a simulation_run row with identical engine_version/seed defaults, in
        the same transaction (so an identical created_at), which made an `order by
        created_at` readback here pick either row arbitrarily and pass regardless of whether
        this test's own insert ran at all. Reading back a specific id can't do that — the
        review that caught this: "comment out the insert line and watch it still pass" is
        exactly the check that would fail loudly now."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=None, role="service_role"):
            new_id = self._insert_simulation_run(
                project_id=self.tenant_a.project_id, model_version=self.tenant_a.model_version
            )
            self.cur.execute(
                "select engine_version, seed, tenant_id from simulation_run where id = %s",
                (new_id,),
            )
            engine_version, seed, tenant_id = self.cur.fetchone()
        self.assertEqual(engine_version, "test")
        self.assertEqual(seed, 1)
        self.assertEqual(
            tenant_id, self.tenant_a.tenant_id,
            "the tenant-derivation trigger must still resolve correctly for a service_role write",
        )

    def test_simulation_run_requires_engine_version(self):
        """Every result row is stamped with the engine version — structurally, not by
        convention. Omitting it (even as service_role, which has every other privilege) must
        fail: `engine_version text not null` has no default."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=None, role="service_role"):
            with self.assertRaises(psycopg.errors.NotNullViolation):
                with self.conn.transaction():
                    self._insert_simulation_run(
                        project_id=self.tenant_a.project_id,
                        model_version=self.tenant_a.model_version,
                        omit="engine_version",
                    )

    def test_simulation_run_requires_seed(self):
        """Same shape as the engine_version test, for `seed` — reproducibility (model_version
        + seed + engine_version) is the other half of "every number is attributable"."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=None, role="service_role"):
            with self.assertRaises(psycopg.errors.NotNullViolation):
                with self.conn.transaction():
                    self._insert_simulation_run(
                        project_id=self.tenant_a.project_id,
                        model_version=self.tenant_a.model_version,
                        omit="seed",
                    )

    def test_authenticated_cannot_delete_simulation_run(self):
        """Write-verb coverage was INSERT + UPDATE (existing test) but never DELETE. Already
        blocked today (no grant covers it) — this locks it so a future stray `grant delete`
        can't slip through green unnoticed."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute(
                        "delete from simulation_run where project_id = %s", (self.tenant_a.project_id,)
                    )

    def test_authenticated_cannot_truncate_simulation_run(self):
        """TRUNCATE needs its own, separate privilege in Postgres — not covered by any of
        the INSERT/UPDATE/DELETE/SELECT grants — so this is a genuinely distinct check, not
        a duplicate of the DELETE test above."""
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute("truncate simulation_run")


if __name__ == "__main__":
    unittest.main()
