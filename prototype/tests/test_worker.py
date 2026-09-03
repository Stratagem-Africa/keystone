from __future__ import annotations

import unittest
from unittest import mock
from unittest.mock import patch  # lets us fake a function to simulate failures

from fastapi.testclient import TestClient

from api.main import app
from api import jobs
from api.jobs import create_job, get_job, update_job
from api.worker import _make_meter, run_pipeline
from auth_test_helpers import make_test_token, patch_jwks, set_test_supabase_url
from keystone.cost_meter import CostMeter

client = TestClient(app)

# create_job/get_job/update_job are RLS-scoped by (user_id, access_token) — but these
# tests never set SUPABASE_ANON_KEY, so jobs.py's Postgres path is always skipped and
# only the in-memory store is exercised. The access_token value itself is therefore
# never actually used to talk to Postgres here; it just has to be a non-empty string,
# and user_id must match _auth_headers()'s token (sub="user-123" is make_test_token's
# default) so the memory-fallback ownership check in get_job() doesn't reject it.
TEST_USER_ID = "user-123"
TEST_ACCESS_TOKEN = "test-token"


def _auth_headers() -> dict:
    # /intent is gated by Supabase-JWT auth (#10) — mint a valid test token rather
    # than a real one, verified via patch_jwks() (set up in setUp below) instead of
    # a real network call to Supabase's JWKS endpoint.
    return {"Authorization": f"Bearer {make_test_token()}"}


class TestWorker(unittest.TestCase):

    def setUp(self):
        jobs._store.clear()       # fresh store before every test
        set_test_supabase_url(self)
        patch_jwks(self)

    def test_update_job_changes_status(self):
        # create a job, then update it and check the change was saved
        job = create_job("some intent text for testing here", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(job.status, "queued")

        update_job(job.job_id, access_token=TEST_ACCESS_TOKEN, status="processing")

        updated = get_job(job.job_id, user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(updated.status, "processing")

    def test_run_pipeline_completes_job(self):
        # run the full pipeline on a stub job — no API key needed (stub ingestor + council)
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)

        run_pipeline(job.job_id, job.intent_text, TEST_ACCESS_TOKEN)

        completed = get_job(job.job_id, user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(completed.status, "done")
        self.assertIsNotNone(completed.result)   # report was generated
        self.assertIsNone(completed.error)

    def test_run_pipeline_records_error_on_failure(self):
        # patch make_ingestor to raise an exception — simulates a real pipeline failure
        # patch() temporarily replaces the real function with a fake one for this test only
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)

        with patch("api.worker.make_ingestor", side_effect=RuntimeError("simulated failure")):
            run_pipeline(job.job_id, job.intent_text, TEST_ACCESS_TOKEN)

        failed = get_job(job.job_id, user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(failed.status, "error")
        self.assertIsNotNone(failed.error)   # error message was stored

    def test_processing_update_failure_still_marks_job_error(self):
        # update_job(status="processing") used to sit OUTSIDE run_pipeline's try/except — a failure
        # there propagated uncaught, leaving the job stuck at its initial status forever with no
        # error ever recorded. It's now the first statement INSIDE the try, so this must land on
        # status="error" like any other failure in the pipeline.
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        real_update_job = jobs.update_job

        def flaky(job_id, *, access_token, status, result=None, error=None):
            if status == "processing":
                raise RuntimeError("simulated store failure")
            return real_update_job(job_id, access_token=access_token, status=status,
                                   result=result, error=error)

        with patch("api.worker.update_job", side_effect=flaky):
            run_pipeline(job.job_id, job.intent_text, TEST_ACCESS_TOKEN)

        failed = get_job(job.job_id, user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(failed.status, "error")
        self.assertIsNotNone(failed.error)

    def test_make_meter_treats_unparseable_cap_as_uncapped(self):
        # float("inf") parses fine, but int(inf) raises OverflowError (not ValueError) --
        # a bare `except ValueError` would let that escape and crash the job. Confirms the
        # broadened except degrades to an UNCAPPED meter (never None -- see next test),
        # same as a non-numeric string already does.
        with mock.patch.dict("os.environ", {"LLM_MAX_SPEND_USD": "inf"}, clear=False):
            self.assertIsNone(_make_meter().max_micro_usd)
        with mock.patch.dict("os.environ", {"LLM_MAX_SPEND_USD": "not-a-number"}, clear=False):
            self.assertIsNone(_make_meter().max_micro_usd)

    def test_make_meter_always_returns_a_real_meter(self):
        # _make_meter() must never return None -- run_pipeline logs meter.summary() in
        # both its success and error paths, so a None meter (the pre-fix behavior when
        # LLM_MAX_SPEND_USD was unset) would crash every job with an AttributeError.
        with mock.patch.dict("os.environ", {}, clear=True):
            meter = _make_meter()
        self.assertIsInstance(meter, CostMeter)
        self.assertIsNone(meter.max_micro_usd)   # uncapped, not absent

    def test_pipeline_error_is_scrubbed(self):
        # error messages from the real ingestor can contain raw LLM output with secrets
        # — the worker must redact them before storing or logging
        job = create_job("I am building a URL shortener that handles 50k req/s", [],
                         user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)

        # fake exception whose message contains a secret pattern
        fake_error = RuntimeError("failed: sk-ant-api03-AAABBBCCCDDDEEEFFFGGGHHH leaked in output")

        with patch("api.worker.make_ingestor", side_effect=fake_error):
            run_pipeline(job.job_id, job.intent_text, TEST_ACCESS_TOKEN)

        failed = get_job(job.job_id, user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(failed.status, "error")
        self.assertIsNotNone(failed.error)
        self.assertNotIn("sk-ant-api03", failed.error)  # secret was redacted before storage


    def test_intent_endpoint_triggers_pipeline(self):
        # TestClient runs background tasks synchronously — so by the time we check,
        # the pipeline has already completed
        response = client.post(
            "/intent",
            data={"text": "I am building a URL shortener that handles 50k req/s"},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        job = get_job(data["job_id"], user_id=TEST_USER_ID, access_token=TEST_ACCESS_TOKEN)
        self.assertEqual(job.status, "done")   # pipeline ran and finished


if __name__ == "__main__":
    unittest.main()
