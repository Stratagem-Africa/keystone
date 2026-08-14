#!/usr/bin/env bash
# ADR-005 §1b harm-floor gate: "signed in as tenant A, every table returns ZERO of tenant B's
# rows on select/insert/update/delete" — plus 0002's access-token-hook behavior (multi-
# membership determinism, zero-membership fail-closed, EXECUTE grants).
#
# NOT part of scripts/check.sh — that gate is $0/hermetic/no-DB by design (it strips
# SUPABASE_* env vars before running). This is the explicit, opt-in reviewer step for any PR
# touching db/migrations/** or db/testing/**. It never silently passes if no DB is reachable —
# it hard-fails with a clear message instead.
#
#   docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17
#   pip install -e ".[dbtest]"
#   KEYSTONE_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres \
#     scripts/test_tenant_isolation.sh
#
# Needs a reachable Postgres 17+ SUPERUSER connection with CREATEDB (the harness creates and
# drops its own disposable scratch database(s) — nothing here ever touches a real project).
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "${KEYSTONE_TEST_DATABASE_URL:-}" ]; then
  echo "❌ KEYSTONE_TEST_DATABASE_URL is not set — this is a hard requirement, not a skip."
  echo "   e.g.: docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:17"
  echo "   then: KEYSTONE_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres $0"
  exit 2
fi

cd "$root/prototype" || { echo "error: cannot find prototype/"; exit 2; }

python3 -c "import psycopg" 2>/dev/null || {
  echo "❌ psycopg not installed. Run: pip install -e '.[dbtest]'"
  exit 2
}

echo "==> ADR-005 §1b tenant-isolation + 0002 access-token-hook gate"
python3 -m unittest discover -s tests -p "db_test_*.py" -v
status=$?

echo
if [ "$status" -eq 0 ]; then
  echo "✅ TENANT-ISOLATION GATE PASSED."
else
  echo "❌ TENANT-ISOLATION GATE FAILED — do not merge a schema change on a red run."
fi
exit "$status"
