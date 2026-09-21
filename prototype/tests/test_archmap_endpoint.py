from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app          # the FastAPI app — all routes live here
from api import jobs              # the module so we can clear _store between tests
from api.jobs import create_job, update_job  # helpers to set up test data directly
from auth_test_helpers import make_test_token, patch_jwks, set_test_supabase_url

client = TestClient(app)  # one shared client for all tests in this file

# Jobs are RLS-scoped by (user_id, access_token) — these tests never set
# SUPABASE_ANON_KEY, so jobs.py's Postgres path is always skipped and only the
# in-memory store is exercised. user_id must match _auth_headers()'s token
# (sub="user-123" is make_test_token's default) so the HTTP requests below,
# authenticated as that user, pass the memory-fallback ownership check in get_job().
TEST_USER_ID = "user-123"
TEST_ACCESS_TOKEN = "test-token"

# A minimal but shape-valid arch_map dict — enough to exercise render_html() (which reads
# arch["meta"]["title"]) without running the full engine pipeline in every test.
FAKE_ARCH_MAP = {
    "meta": {"title": "Test System", "engine_version": "test", "accuracy_level": "L0 (Directional)",
              "offered_load_rps": 1000.0, "confidence": "high", "high_stakes": False, "domain_flags": []},
    "verdict": {"bottleneck_id": "svc", "bottleneck_name": "svc", "bottleneck_utilization": 0.5,
                "breakpoint_rps_safe": 2000.0, "breakpoint_rps_theoretical": 2000.0, "spofs": [],
                "monthly_cost_cents": 100, "latency": {"mean_ms": 1.0, "p50_ms": 1.0, "p95_ms": 2.0, "p99_ms": 3.0}},
    "layers": [], "nodes": [], "flows": [], "metrics": [], "caveats": [], "derivation": [], "assumptions": [],
}


def _auth_headers() -> dict:
    # These endpoints are gated by Supabase-JWT auth (#10) — mint a valid test token
    # rather than a real one, verified via patch_jwks() (set up in setUp below) instead
    # of a real network call to Supabase's JWKS endpoint.
    return {"Authorization": f"Bearer {make_test_token()}"}


class TestJobArchMapEndpoint(unittest.TestCase):
    """Tests for GET /jobs/{job_id}/archmap — issue #183."""

    def setUp(self):
        jobs._store.clear()
        set_test_supabase_url(self)
        patch_jwks(self)

    def test_unknown_job_returns_404(self):
        response = client.get("/jobs/does-not-exist/archmap", headers=_auth_headers())
        self.assertEqual(response.status_code, 404)

    def test_archmap_not_ready_returns_404(self):
        # Job exists but is still running — the map hasn't been written yet
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="processing")

        response = client.get(f"/jobs/{job.job_id}/archmap", headers=_auth_headers())

        self.assertEqual(response.status_code, 404)
        self.assertIn("processing", response.json()["detail"])

    def test_done_job_returns_json_archmap(self):
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here", arch_map=FAKE_ARCH_MAP)

        response = client.get(f"/jobs/{job.job_id}/archmap", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "done")
        self.assertIn("arch_map", data)
        self.assertEqual(data["arch_map"], FAKE_ARCH_MAP)

    def test_format_query_param_returns_html(self):
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here", arch_map=FAKE_ARCH_MAP)

        response = client.get(f"/jobs/{job.job_id}/archmap?fmt=html", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        # A byte-for-byte check on the rendered page isn't the point here (test_arch_map.py
        # already goldens render_html itself) — just confirm this IS the self-contained page,
        # not a JSON blob, and that it's keyed to the right job's data.
        self.assertIn("<!doctype html>", response.text.lower())
        self.assertIn("Test System", response.text)

    def test_accept_header_returns_html(self):
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here", arch_map=FAKE_ARCH_MAP)

        response = client.get(
            f"/jobs/{job.job_id}/archmap",
            headers={"Accept": "text/html", **_auth_headers()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("<!doctype html>", response.text.lower())

    def test_archmap_is_deterministic(self):
        # Same stored data in -> byte-identical HTML out, every time (build_arch_map/render_html
        # are already covered for determinism in test_arch_map.py — this just checks the wiring
        # through the endpoint doesn't introduce any per-request variance, e.g. timestamps).
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here", arch_map=FAKE_ARCH_MAP)

        first = client.get(f"/jobs/{job.job_id}/archmap?fmt=html", headers=_auth_headers())
        second = client.get(f"/jobs/{job.job_id}/archmap?fmt=html", headers=_auth_headers())
        self.assertEqual(first.text, second.text)

    def test_another_users_archmap_returns_404(self):
        # Same tenant-isolation gate as the report endpoint, for the arch-map fetch.
        job = create_job("someone else's system description", [],
                         user_id="a-different-user", access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# Someone else's report", arch_map=FAKE_ARCH_MAP)

        response = client.get(f"/jobs/{job.job_id}/archmap", headers=_auth_headers())

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
