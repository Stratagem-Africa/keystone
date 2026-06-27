from __future__ import annotations  # allows modern type hints on older Python

import unittest

from fastapi.testclient import TestClient  # simulates HTTP requests without a real server

from api.main import app          # the FastAPI app — all routes live here
from api import jobs              # the module so we can clear _store between tests
from api.jobs import create_job, update_job  # helpers to set up test data directly

client = TestClient(app)  # one shared client for all tests in this file


class TestJobStatusEndpoint(unittest.TestCase):
    """Tests for GET /jobs/{job_id} — the status polling endpoint."""

    def setUp(self):
        # Clear the in-memory store before every test so tests don't bleed into each other.
        # Without this, a job created in test A would still exist when test B runs.
        jobs._store.clear()
        jobs._db_client = None  # ensure no Postgres client leaks between tests

    def test_unknown_job_returns_404(self):
        # A made-up ID that was never created — should get a clean 404, not a server crash
        response = client.get("/jobs/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_queued_job_returns_status(self):
        # Create a job — it starts in "queued" state automatically
        job = create_job("I am building a URL shortener that handles 50k req/s", [])

        response = client.get(f"/jobs/{job.job_id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()  # parse the JSON body into a Python dict
        self.assertEqual(data["job_id"], job.job_id)
        self.assertEqual(data["status"], "queued")
        self.assertNotIn("error", data)  # error field should NOT appear for non-error jobs

    def test_error_job_includes_error_message(self):
        # Set up a job and manually mark it as failed — simulates a pipeline crash
        job = create_job("I am building a URL shortener that handles 50k req/s", [])
        update_job(job.job_id, status="error", error="something went wrong in the pipeline")

        response = client.get(f"/jobs/{job.job_id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("error", data)  # error field MUST appear when status is "error"
        self.assertEqual(data["error"], "something went wrong in the pipeline")


class TestJobReportEndpoint(unittest.TestCase):
    """Tests for GET /jobs/{job_id}/report — the report fetch endpoint."""

    def setUp(self):
        jobs._store.clear()
        jobs._db_client = None

    def test_unknown_job_returns_404(self):
        response = client.get("/jobs/does-not-exist/report")
        self.assertEqual(response.status_code, 404)

    def test_report_not_ready_returns_404(self):
        # Job exists but is still running — report hasn't been written yet
        job = create_job("I am building a URL shortener that handles 50k req/s", [])
        update_job(job.job_id, status="processing")

        response = client.get(f"/jobs/{job.job_id}/report")

        self.assertEqual(response.status_code, 404)
        # The error message should mention the current status so the client knows why
        self.assertIn("processing", response.json()["detail"])

    def test_done_job_returns_json_report(self):
        # Set up a finished job with a report stored
        job = create_job("I am building a URL shortener that handles 50k req/s", [])
        update_job(job.job_id, status="done", result="# My Report\nsome content here")

        response = client.get(f"/jobs/{job.job_id}/report")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "done")
        self.assertIn("report", data)          # report key must be present
        self.assertIsNotNone(data["report"])   # and it must have a value

    def test_format_query_param_returns_markdown(self):
        # ?format=markdown in the URL should return plain text, not JSON
        job = create_job("I am building a URL shortener that handles 50k req/s", [])
        update_job(job.job_id, status="done", result="# My Report\nsome content here")

        response = client.get(f"/jobs/{job.job_id}/report?format=markdown")

        self.assertEqual(response.status_code, 200)
        # content-type header tells us what kind of data the server returned
        self.assertIn("text/markdown", response.headers["content-type"])
        # The raw body should be the markdown string, not a JSON object
        self.assertIn("# My Report", response.text)

    def test_accept_header_returns_markdown(self):
        # Accept: text/markdown header is the standard HTTP way to request markdown
        job = create_job("I am building a URL shortener that handles 50k req/s", [])
        update_job(job.job_id, status="done", result="# My Report\nsome content here")

        response = client.get(
            f"/jobs/{job.job_id}/report",
            headers={"Accept": "text/markdown"},  # this is how a browser/client signals its preference
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])
        self.assertIn("# My Report", response.text)


if __name__ == "__main__":
    unittest.main()
