from __future__ import annotations  # allows modern type hints on older Python

import unittest

from fastapi.testclient import TestClient  # simulates HTTP requests without a real server

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


def _auth_headers() -> dict:
    # These endpoints are gated by Supabase-JWT auth (#10) — mint a valid test token
    # rather than a real one, verified via patch_jwks() (set up in setUp below) instead
    # of a real network call to Supabase's JWKS endpoint.
    return {"Authorization": f"Bearer {make_test_token()}"}


class TestJobStatusEndpoint(unittest.TestCase):
    """Tests for GET /jobs/{job_id} — the status polling endpoint."""

    def setUp(self):
        # Clear the in-memory store before every test so tests don't bleed into each other.
        # Without this, a job created in test A would still exist when test B runs.
        jobs._store.clear()
        set_test_supabase_url(self)
        patch_jwks(self)

    def test_unknown_job_returns_404(self):
        # A made-up ID that was never created — should get a clean 404, not a server crash
        response = client.get("/jobs/does-not-exist", headers=_auth_headers())
        self.assertEqual(response.status_code, 404)

    def test_queued_job_returns_status(self):
        # Create a job — it starts in "queued" state automatically
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)

        response = client.get(f"/jobs/{job.job_id}", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.json()  # parse the JSON body into a Python dict
        self.assertEqual(data["job_id"], job.job_id)
        self.assertEqual(data["status"], "queued")
        self.assertNotIn("error", data)  # error field should NOT appear for non-error jobs

    def test_error_job_includes_error_message(self):
        # Set up a job and manually mark it as failed — simulates a pipeline crash
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="error",
                  error="something went wrong in the pipeline")

        response = client.get(f"/jobs/{job.job_id}", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("error", data)  # error field MUST appear when status is "error"
        self.assertEqual(data["error"], "something went wrong in the pipeline")

    def test_another_users_job_returns_404_not_someone_elses_status(self):
        # The tenant-isolation gate: a job created by a DIFFERENT user must be invisible
        # to this test's caller (_auth_headers()'s "user-123") -- a 404, indistinguishable
        # from a job that never existed, never a "yes it exists but isn't yours" signal.
        job = create_job("someone else's system description", [],
                         user_id="a-different-user", access_token=TEST_ACCESS_TOKEN)

        response = client.get(f"/jobs/{job.job_id}", headers=_auth_headers())

        self.assertEqual(response.status_code, 404)


class TestJobReportEndpoint(unittest.TestCase):
    """Tests for GET /jobs/{job_id}/report — the report fetch endpoint."""

    def setUp(self):
        jobs._store.clear()
        set_test_supabase_url(self)
        patch_jwks(self)

    def test_unknown_job_returns_404(self):
        response = client.get("/jobs/does-not-exist/report", headers=_auth_headers())
        self.assertEqual(response.status_code, 404)

    def test_report_not_ready_returns_404(self):
        # Job exists but is still running — report hasn't been written yet
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="processing")

        response = client.get(f"/jobs/{job.job_id}/report", headers=_auth_headers())

        self.assertEqual(response.status_code, 404)
        # The error message should mention the current status so the client knows why
        self.assertIn("processing", response.json()["detail"])

    def test_done_job_returns_json_report(self):
        # Set up a finished job with a report stored
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here")

        response = client.get(f"/jobs/{job.job_id}/report", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "done")
        self.assertIn("report", data)          # report key must be present
        self.assertIsNotNone(data["report"])   # and it must have a value

    def test_format_query_param_returns_markdown(self):
        # ?fmt=markdown in the URL should return plain text, not JSON
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here")

        response = client.get(f"/jobs/{job.job_id}/report?fmt=markdown", headers=_auth_headers())

        self.assertEqual(response.status_code, 200)
        # content-type header tells us what kind of data the server returned
        self.assertIn("text/markdown", response.headers["content-type"])
        # The raw body should be the markdown string, not a JSON object
        self.assertIn("# My Report", response.text)

    def test_accept_header_returns_markdown(self):
        # Accept: text/markdown header is the standard HTTP way to request markdown
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# My Report\nsome content here")

        response = client.get(
            f"/jobs/{job.job_id}/report",
            headers={"Accept": "text/markdown", **_auth_headers()},  # this is how a browser/client signals its preference
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])
        self.assertIn("# My Report", response.text)

    def test_another_users_report_returns_404(self):
        # Same tenant-isolation gate as the status endpoint above, for the report fetch.
        job = create_job("someone else's system description", [],
                         user_id="a-different-user", access_token=TEST_ACCESS_TOKEN)
        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="done",
                  result="# Someone else's report")

        response = client.get(f"/jobs/{job.job_id}/report", headers=_auth_headers())

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
