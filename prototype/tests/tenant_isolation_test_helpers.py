"""Shared harness for the Postgres-backed RLS / auth-hook tests (db_test_*.py).

Not a test module itself — deliberately named to avoid BOTH unittest discover's default
`test*.py` glob (what scripts/check.sh runs, so this never touches the $0/hermetic gate) AND
the `db_test_*.py` glob scripts/test_tenant_isolation.sh opts into (so it's never collected
as an empty, test-less module either). Matches the one real precedent in this directory,
auth_test_helpers.py: a plain descriptive name, no `test` prefix.

Repeatability strategy (three tiers — see DatabaseTestCase):
  1. CLASS level: one disposable scratch database per test class (DROP ... WITH (FORCE) +
     CREATE, on an autocommit connection — CREATE/DROP DATABASE cannot run inside a
     transaction block), with the shim + both migrations applied ONCE. This is deliberately
     NOT "wrap everything in one big transaction and roll back": 0001 and 0002 are each
     already self-contained `begin; ... commit;` blocks, and Postgres doesn't nest
     transactions — an embedded `commit;` while "inside" one more wrapping BEGIN just commits
     the single actual current transaction, silently defeating any outer rollback. A
     disposable database sidesteps that: each migration's own transaction runs exactly as it
     would against a real Supabase project, and cleanup is "drop the database", which is
     self-healing even if a prior run's teardown never happened (the next run's
     `DROP DATABASE IF EXISTS` at the top cleans up unconditionally).
  2. METHOD level: setUp() opens a real transaction and seeds tenant A + tenant B fresh;
     tearDown() rolls it back. Test methods never see each other's mutations.
  3. WITHIN a method: `with conn.transaction():` (a psycopg3 SAVEPOINT) around any statement
     expected to raise, so one expected rejection doesn't abort the rest of that method's
     assertions.

Needs verification against a real Postgres instance (cannot be confirmed from a sandboxed dev
environment with no network/Postgres access) — see scripts/test_tenant_isolation.sh's header:
  - `apply_sql_file` submits a whole file's text via a single `execute()` call with no bind
    parameters, relying on psycopg3 falling back to the simple query protocol (which allows
    multiple ;-separated statements) whenever no params are passed. If this errors instead,
    the fallback is to split the file on top-level `;` and execute statements one at a time,
    or shell out to `psql -f <path>` for that one call.
  - `DROP DATABASE ... WITH (FORCE)` (PG13+) behaves as expected on PG17.
  - The target connection actually has CREATEDB (a local `docker run postgres:17` superuser
    will; the wrapper script's error message should be actionable if not).
"""
from __future__ import annotations

import json
import os
import unittest
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import psycopg
    from psycopg import sql
except ImportError as exc:  # pragma: no cover - scripts/test_tenant_isolation.sh checks this first
    raise RuntimeError(
        "psycopg is required for the DB isolation harness. "
        "pip install -e '.[dbtest]', then run via scripts/test_tenant_isolation.sh."
    ) from exc

ENV_VAR = "KEYSTONE_TEST_DATABASE_URL"

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM_SQL = REPO_ROOT / "db" / "testing" / "supabase_role_shim.sql"
MIGRATIONS = [
    REPO_ROOT / "db" / "migrations" / "0001_canonical_model_store.sql",
    REPO_ROOT / "db" / "migrations" / "0002_tenant_id_auth_hook.sql",
    REPO_ROOT / "db" / "migrations" / "0003_jobs_table.sql",
]


def require_database_url() -> str:
    """Hard failure (RuntimeError, NOT unittest.SkipTest) if unset. A skip reads as
    `OK (skipped=N)` in a test summary line — easy to misread as green. This must never
    look like it passed when it didn't run at all."""
    url = os.environ.get(ENV_VAR)
    if not url:
        raise RuntimeError(
            f"{ENV_VAR} is not set. This harness needs a reachable Postgres 17+ SUPERUSER "
            "connection (it creates/drops its own scratch databases and roles). e.g.:\n"
            "  docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17\n"
            f"  {ENV_VAR}=postgresql://postgres:postgres@localhost:5432/postgres "
            "scripts/test_tenant_isolation.sh"
        )
    return url


def _with_dbname(url: str, dbname: str) -> str:
    # Swap the /path component of a postgresql:// URL for a different database name,
    # keeping host/port/user/password/query-string intact.
    prefix, _, _rest = url.partition("://")
    if "@" in _rest:
        creds_host, _, _old_db = _rest.partition("/")
        return f"{prefix}://{creds_host}/{dbname}"
    host, _, _old_db = _rest.partition("/")
    return f"{prefix}://{host}/{dbname}"


def build_scratch_database(admin_url: str, scratch_db: str) -> str:
    """DROP+CREATE a disposable database off an autocommit maintenance connection. Returns
    its connection URL. Fixed, greppable scratch_db name (per caller) so a crashed prior run
    is cleaned up unconditionally by the next run's DROP, not left orphaned forever."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(scratch_db))
        )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch_db)))
    return _with_dbname(admin_url, scratch_db)


def drop_scratch_database(admin_url: str, scratch_db: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(scratch_db))
        )


def apply_sql_file(conn: "psycopg.Connection", path: Path) -> None:
    """Run a file's raw SQL text as-is, unwrapped in any further transaction — see the
    module docstring for why (0001/0002 each already contain their own begin/commit)."""
    conn.execute(path.read_text())


@dataclass(frozen=True)
class TenantFixture:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    model_version: int
    component_id: str          # the text slug, e.g. "app" — see seed_tenant's docstring
    flow_id: uuid.UUID
    flow_step_id: uuid.UUID
    assumption_id: uuid.UUID
    source_document_id: uuid.UUID
    simulation_run_id: uuid.UUID


def seed_tenant(cur, *, name: str, component_slug: str = "app") -> TenantFixture:
    """Seeds one full tenant across all 10 tables. Runs as whatever role the caller's
    connection currently has (superuser at the point setUp() calls this, before any
    sign_in_as() — so RLS is bypassed and this always succeeds regardless of grants).

    component_slug defaults to the SAME literal "app" for every call on purpose: component.id
    is an app-chosen text slug, not a UUID, so two tenants legitimately using the identical
    slug is the realistic case the flow_step composite-FK protection exists for (see
    db_test_tenant_isolation.py's structural cross-tenant test, which depends on this
    collision existing between tenant A's and tenant B's fixtures)."""
    tenant_id = cur.execute(
        "insert into tenant (name) values (%s) returning id", (name,)
    ).fetchone()[0]
    user_id = cur.execute(
        "insert into auth.users (email) values (%s) returning id", (f"{name}@example.test",)
    ).fetchone()[0]
    cur.execute(
        "insert into membership (user_id, tenant_id, role) values (%s, %s, 'owner')",
        (user_id, tenant_id),
    )
    project_id = cur.execute(
        "insert into project (tenant_id, owner_id, name) values (%s, %s, %s) returning id",
        (tenant_id, user_id, f"{name}-project"),
    ).fetchone()[0]
    # tenant_id omitted: trg_component_tenant / trg_flow_tenant / trg_assumption_tenant /
    # trg_simulation_run_tenant all derive it from (project_id, model_version) via
    # keystone_derive_tenant_from_system_model — supplying it here would just be overwritten.
    model_version = cur.execute(
        """insert into system_model
             (project_id, tenant_id, name, system_rps,
              egress_micro_usd_per_gb, storage_micro_usd_per_gb_month,
              request_micro_usd_per_thousand, llm_input_micro_usd_per_1k_tokens,
              llm_output_micro_usd_per_1k_tokens)
           values (%s, %s, %s, 100.0, 0, 0, 0, 0, 0)
           returning version""",
        (project_id, tenant_id, f"{name} model v1"),
    ).fetchone()[0]
    cur.execute(
        """insert into component
             (id, project_id, model_version, kind, name, per_instance_rps,
              monthly_cost_per_instance, provenance)
           values (%s, %s, %s, 'app_server', %s, 50.0, 500, 'ASSUMPTION')""",
        (component_slug, project_id, model_version, f"{name} app"),
    )
    flow_id = cur.execute(
        """insert into flow (project_id, model_version, name, share)
           values (%s, %s, %s, 1.0) returning id""",
        (project_id, model_version, f"{name} main flow"),
    ).fetchone()[0]
    # flow_step's tenant_id/project_id/model_version are ALL trigger-derived (from flow_id,
    # via trg_flow_step_scope) — only flow_id/component_id/step_order are real inputs.
    flow_step_id = cur.execute(
        """insert into flow_step (flow_id, component_id, step_order)
           values (%s, %s, 0) returning id""",
        (flow_id, component_slug),
    ).fetchone()[0]
    assumption_id = cur.execute(
        """insert into assumption
             (project_id, model_version, subject, statement, confidence, source, provenance)
           values (%s, %s, 'latency', 'placeholder', 'med', 'user', 'ASSUMPTION') returning id""",
        (project_id, model_version),
    ).fetchone()[0]
    # source_document's tenant_id is trigger-derived from project_id alone (no model_version
    # concept for this table — trg_source_document_tenant uses keystone_derive_tenant_from_project).
    source_document_id = cur.execute(
        """insert into source_document (project_id, type, uri, checksum)
           values (%s, 'text', %s, 'deadbeef') returning id""",
        (project_id, f"{tenant_id}/{project_id}/note.txt"),
    ).fetchone()[0]
    simulation_run_id = cur.execute(
        """insert into simulation_run
             (project_id, model_version, engine_version, seed,
              bottleneck_id, bottleneck_name, bottleneck_utilization,
              breakpoint_rps_safe, breakpoint_rps_theoretical,
              mean_latency_ms, p50_ms, p95_ms, p99_ms, monthly_cost, confidence)
           values (%s, %s, 'test', 1, %s, 'app', 0.5, 100, 100, 10, 10, 10, 10, 500, 'low')
           returning id""",
        (project_id, model_version, component_slug),
    ).fetchone()[0]
    return TenantFixture(
        tenant_id=tenant_id, user_id=user_id, project_id=project_id,
        model_version=model_version, component_id=component_slug,
        flow_id=flow_id, flow_step_id=flow_step_id, assumption_id=assumption_id,
        source_document_id=source_document_id, simulation_run_id=simulation_run_id,
    )


@contextmanager
def sign_in_as(cur, *, user_id: uuid.UUID, tenant_id: "uuid.UUID | None", role: str = "authenticated"):
    """Simulate 'signed in as this user, with this tenant claim, as this Postgres role' —
    matching what the real hook (0002) + PostgREST would produce: a `request.jwt.claims`
    JSON GUC (SET LOCAL scope, via set_config(..., true)) plus SET LOCAL ROLE.

    tenant_id=None simulates a user with NO membership: the real hook strips the tenant_id
    claim entirely in that case (fail-closed), so every 0001 policy then denies every row —
    exactly the "designed bootstrap state" Bifola confirmed, not a gap.

    Always RESET ROLE first: switching directly between two non-superuser roles requires
    role-membership grants Postgres won't otherwise have between anon/authenticated/etc.;
    resetting to the session's original (superuser) role before switching sidesteps that,
    since a superuser may SET ROLE to anything unconditionally.
    """
    cur.execute("RESET ROLE")
    claims = {"sub": str(user_id), "role": role}
    if tenant_id is not None:
        claims["tenant_id"] = str(tenant_id)
    cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
    cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
    try:
        yield
    finally:
        cur.execute("RESET ROLE")
        cur.execute("SELECT set_config('request.jwt.claims', '', true)")


class DatabaseTestCase(unittest.TestCase):
    """Base class for Postgres-backed tests. Subclasses set `scratch_db_name` to a unique,
    fixed name (avoids two test modules colliding if ever run concurrently).

    setUpClass: build the scratch database once, apply the shim + 0001 + 0002 once (as
    superuser, autocommit — see apply_sql_file's docstring for why no further wrapping
    transaction). tearDownClass: drop it.

    setUp: open a real transaction, seed tenant A ("tenant-a") + tenant B ("tenant-b") fresh.
    tearDown: roll back. Every test method gets an identical, isolated starting state.
    """

    scratch_db_name: str = "keystone_test_db_test_case"  # subclasses override this
    admin_url: str
    db_url: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.admin_url = require_database_url()
        cls.db_url = build_scratch_database(cls.admin_url, cls.scratch_db_name)
        with psycopg.connect(cls.db_url, autocommit=True) as conn:
            apply_sql_file(conn, SHIM_SQL)
            for migration in MIGRATIONS:
                apply_sql_file(conn, migration)

    @classmethod
    def tearDownClass(cls) -> None:
        drop_scratch_database(cls.admin_url, cls.scratch_db_name)

    def setUp(self) -> None:
        self.conn = psycopg.connect(self.db_url, autocommit=False)
        self.cur = self.conn.cursor()
        self.tenant_a = seed_tenant(self.cur, name="tenant-a")
        self.tenant_b = seed_tenant(self.cur, name="tenant-b")

    def tearDown(self) -> None:
        self.conn.rollback()
        self.conn.close()
