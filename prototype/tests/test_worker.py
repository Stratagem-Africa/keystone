from __future__ import annotations

import unittest
from unittest.mock import patch  # lets us fake a function to simulate failures

from fastapi.testclient import TestClient

from api.main import app
from api import jobs
from api.jobs import create_job, get_job, update_job
from api.worker import run_pipeline
from auth_test_helpers import make_test_token, patch_jwks, set_test_supabase_url

client = TestClient(app)


def _auth_headers() -> dict:
    # /intent is gated by Supabase-JWT auth (#10) — mint a valid test token rather
    # than a real one, verified via patch_jwks() (set up in setUp below) instead of
    # a real network call to Supabase's JWKS endpoint.
    return {"Authorization": f"Bearer {make_test_token()}"}


class TestWorker(unittest.TestCase):

    def setUp(self):
        jobs._store.clear()       # fresh store before every test
        jobs._db_client = None    # make sure no Postgres client leaks between tests
        set_test_supabase_url(self)
        patch_jwks(self)

    def test_update_job_changes_status(self):
        # create a job, then update it and check the change was saved
        job = create_job("some intent text for testing here", [])
        self.assertEqual(job.status, "queued")

        update_job(job.job_id, status="processing")

        updated = get_job(job.job_id)
        self.assertEqual(updated.status, "processing")

    def test_run_pipeline_completes_job(self):
        # run the full pipeline on a stub job — no API key needed (stub ingestor + council)
        job = create_job("I am building a URL shortener that handles 50k req/s", [])

        run_pipeline(job.job_id, job.intent_text)

        completed = get_job(job.job_id)
        self.assertEqual(completed.status, "done")
        self.assertIsNotNone(completed.result)   # report was generated
        self.assertIsNone(completed.error)

    def test_run_pipeline_records_error_on_failure(self):
        # patch make_ingestor to raise an exception — simulates a real pipeline failure
        # patch() temporarily replaces the real function with a fake one for this test only
        job = create_job("I am building a URL shortener that handles 50k req/s", [])

        with patch("api.worker.make_ingestor", side_effect=RuntimeError("simulated failure")):
            run_pipeline(job.job_id, job.intent_text)

        failed = get_job(job.job_id)
        self.assertEqual(failed.status, "error")
        self.assertIsNotNone(failed.error)   # error message was stored

    def test_pipeline_error_is_scrubbed(self):
        # error messages from the real ingestor can contain raw LLM output with secrets
        # — the worker must redact them before storing or logging
        job = create_job("I am building a URL shortener that handles 50k req/s", [])

        # fake exception whose message contains a secret pattern
        fake_error = RuntimeError("failed: sk-ant-api03-AAABBBCCCDDDEEEFFFGGGHHH leaked in output")

        with patch("api.worker.make_ingestor", side_effect=fake_error):
            run_pipeline(job.job_id, job.intent_text)

        failed = get_job(job.job_id)
        self.assertEqual(failed.status, "error")
        self.assertIsNotNone(failed.error)
        self.assertNotIn("sk-ant-api03", failed.error)  # secret was redacted before storage


    def test_intent_endpoint_triggers_pipeline(self):
        # TestClient runs background tasks synchronously — so by the time we check,
        # the pipeline has already completed
        response = client.post(
            "/intent",
            json={"text": "I am building a URL shortener that handles 50k req/s"},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        job = get_job(data["job_id"])
        self.assertEqual(job.status, "done")   # pipeline ran and finished


if __name__ == "__main__":
    unittest.main()
