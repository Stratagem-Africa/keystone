from __future__ import annotations
import unittest
from fastapi.testclient import TestClient  # test helper that fakes HTTP requests
from api.main import app  # import our FastAPI app so we can send test requests to it
from api import jobs  # import the jobs module so we can inspect and reset the store
from auth_test_helpers import make_test_token, patch_jwks, set_test_supabase_url

# TestClient wraps our app — no real server needed, everything runs in memory
client = TestClient(app)


def _auth_headers() -> dict:
    # /intent is gated by Supabase-JWT auth (#10) — mint a valid test token rather
    # than a real one, verified via patch_jwks() (set up in setUp below) instead of
    # a real network call to Supabase's JWKS endpoint.
    return {"Authorization": f"Bearer {make_test_token()}"}


class TestIntentEndpoint(unittest.TestCase):
    def setUp(self):
        jobs._store.clear()
        set_test_supabase_url(self)
        patch_jwks(self)


    def test_submit_intent_returns_job_id(self):
        # send a valid POST request with clean text (no secrets)
        response = client.post(
            "/intent",
            json={"text": "I am building a URL shortener that handles 50k req/s"},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 200)  # HTTP 200 means success

        data = response.json()
        self.assertIn("job_id", data)           # response must contain a job_id
        self.assertEqual(data["status"], "queued") # job starts in queued state
        self.assertNotIn("warnings", data)     # no warnings — this text has no secrets


    def test_submit_intent_too_short_is_rejected(self):
        # Text under 10 characters should be rejected before our code even runs
        response = client.post("/intent", json={"text": "short"}, headers=_auth_headers())

        self.assertEqual(response.status_code, 422)  # 422 = Unprocessable Entity (validation failed)


    def test_submit_intent_redacts_secrets(self):
        # A text that contains what looks like an API key
        text = "My system uses sk-ant-api03-AAABBBCCCDDDEEEFFFGGGHHH to call the AI"

        response = client.post("/intent", json={"text": text}, headers=_auth_headers())

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("job_id", data)
        # A warning should be present because a secret was detected
        self.assertIn("warnings", data)

        # The stored job text must NOT contain the raw secret
        stored_job = jobs.get_job(data["job_id"])
        self.assertNotIn("sk-ant-api03", stored_job.intent_text)  # secret was redacted


if __name__ == "__main__":
    unittest.main()
