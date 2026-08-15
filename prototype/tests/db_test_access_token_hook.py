"""Direct tests of public.keystone_access_token_hook (db/migrations/0002_tenant_id_auth_hook.sql).

Callable as plain SQL — no real Supabase Auth service needed, since the hook is just a
function that takes an `event jsonb` and returns a `claims`-modified `event jsonb`.

Never collected by `python3 -m unittest discover -s tests` (see db_test_tenant_isolation.py's
module docstring for the naming rationale, shared here) — run via
scripts/test_tenant_isolation.sh.
"""
from __future__ import annotations

import json
import unittest

import psycopg

from tenant_isolation_test_helpers import DatabaseTestCase, sign_in_as


def setUpModule() -> None:
    from tenant_isolation_test_helpers import require_database_url
    require_database_url()


def _call_hook(cur, *, user_id, inbound_claims: dict | None = None) -> dict:
    """Call the hook as supabase_auth_admin (the only role with EXECUTE) with a given
    user_id and optional pre-existing inbound claims, and return the resulting claims dict."""
    event = {"user_id": str(user_id), "claims": inbound_claims or {}}
    with sign_in_as(cur, user_id=user_id, tenant_id=None, role="supabase_auth_admin"):
        cur.execute("select public.keystone_access_token_hook(%s::jsonb)", (json.dumps(event),))
        result = cur.fetchone()[0]
    return result["claims"]


class TestAccessTokenHook(DatabaseTestCase):
    scratch_db_name = "keystone_test_access_token_hook"

    def test_single_membership_gets_correct_tenant_claim(self):
        claims = _call_hook(self.cur, user_id=self.tenant_a.user_id)
        self.assertEqual(claims.get("tenant_id"), str(self.tenant_a.tenant_id))

    def test_zero_memberships_gets_no_tenant_id_claim(self):
        orphan_user_id = self.cur.execute(
            "insert into auth.users (email) values ('orphan@example.test') returning id"
        ).fetchone()[0]
        claims = _call_hook(self.cur, user_id=orphan_user_id)
        self.assertNotIn("tenant_id", claims, "a user with no membership must get NO tenant_id claim")

    def test_zero_memberships_strips_preexisting_forged_claim(self):
        # Simulates a stale/forged tenant_id already present on the inbound event — 0002:
        # "Strip any pre-existing value so a stale/forged claim... can never survive."
        orphan_user_id = self.cur.execute(
            "insert into auth.users (email) values ('orphan2@example.test') returning id"
        ).fetchone()[0]
        claims = _call_hook(
            self.cur, user_id=orphan_user_id,
            inbound_claims={"tenant_id": str(self.tenant_b.tenant_id)},
        )
        self.assertNotIn("tenant_id", claims, "a forged inbound tenant_id must be stripped, not kept")

    def test_multi_membership_deterministic_earliest_pick(self):
        """0002: `order by created_at, tenant_id limit 1` — intentional v1 design (confirmed
        by Bifola: "your test can assert the deterministic pick so the behavior is pinned"),
        not a bug. Pins BOTH ordering keys: distinct created_at values (the common case) AND
        a created_at tie broken by the lower tenant_id (the rare case the second ORDER BY key
        exists specifically for — untested, it could silently regress to nondeterministic)."""
        shared_user_id = self.cur.execute(
            "insert into auth.users (email) values ('multi@example.test') returning id"
        ).fetchone()[0]
        # tenant_b's membership created FIRST -> must win over tenant_a's later one.
        self.cur.execute(
            "insert into membership (user_id, tenant_id, role, created_at) "
            "values (%s, %s, 'member', '2024-01-01T00:00:00Z')",
            (shared_user_id, self.tenant_b.tenant_id),
        )
        self.cur.execute(
            "insert into membership (user_id, tenant_id, role, created_at) "
            "values (%s, %s, 'member', '2024-01-02T00:00:00Z')",
            (shared_user_id, self.tenant_a.tenant_id),
        )
        claims = _call_hook(self.cur, user_id=shared_user_id)
        self.assertEqual(
            claims["tenant_id"], str(self.tenant_b.tenant_id),
            "the earlier-created_at membership must win",
        )

        # A third membership, TIED on created_at with tenant_b's row, pins the tenant_id
        # tie-break. Assumes Python's uuid.UUID ordering agrees with Postgres's `uuid`
        # column ordering (both compare the 128-bit value the same way) — flagged as a thing
        # to double-check on first real run, same as the other Postgres-behavior assumptions
        # noted in tenant_isolation_test_helpers.py's module docstring.
        third_tenant_id = self.cur.execute(
            "insert into tenant (name) values ('tie-break-tenant') returning id"
        ).fetchone()[0]
        self.cur.execute(
            "insert into membership (user_id, tenant_id, role, created_at) "
            "values (%s, %s, 'member', '2024-01-01T00:00:00Z')",  # tied with tenant_b's row
            (shared_user_id, third_tenant_id),
        )
        expected_winner = min(self.tenant_b.tenant_id, third_tenant_id)
        claims = _call_hook(self.cur, user_id=shared_user_id)
        self.assertEqual(
            claims["tenant_id"], str(expected_winner),
            "a created_at tie must break on the lower tenant_id",
        )

    def test_execute_denied_for_anon(self):
        # 0002 revokes EXECUTE from anon and authenticated via two SEPARATE statements, so
        # each gets its own test rather than one assuming the other holds too.
        with sign_in_as(self.cur, user_id=self.tenant_a.user_id, tenant_id=None, role="anon"):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute("select public.keystone_access_token_hook('{}'::jsonb)")

    def test_execute_denied_for_authenticated(self):
        with sign_in_as(
            self.cur, user_id=self.tenant_a.user_id, tenant_id=self.tenant_a.tenant_id,
            role="authenticated",
        ):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with self.conn.transaction():
                    self.cur.execute("select public.keystone_access_token_hook('{}'::jsonb)")

    def test_supabase_auth_admin_can_read_membership_despite_rls(self):
        """As supabase_auth_admin (NOT superuser — no BYPASSRLS) with NO auth.uid() set (none
        exists yet at token-mint time, so membership's own_memberships policy would deny
        everything): direct proof that the dedicated membership_auth_admin_read policy — not
        an accidental broad privilege — is what makes the hook's own internal lookup work."""
        self.cur.execute("RESET ROLE")
        self.cur.execute("SELECT set_config('request.jwt.claims', '', true)")
        self.cur.execute("SET LOCAL ROLE supabase_auth_admin")
        self.cur.execute("select count(*) from membership")
        count = self.cur.fetchone()[0]
        self.cur.execute("RESET ROLE")
        self.assertGreaterEqual(
            count, 2, "supabase_auth_admin must see membership rows across different users"
        )


if __name__ == "__main__":
    unittest.main()
