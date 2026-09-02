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
        # /intent is a multipart form endpoint (text field + optional file) so a real
        # browser upload and a plain text-only prompt share one contract.
        response = client.post(
            "/intent",
            data={"text": "I am building a URL shortener that handles 50k req/s"},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 200)  # HTTP 200 means success

        data = response.json()
        self.assertIn("job_id", data)           # response must contain a job_id
        self.assertEqual(data["status"], "queued") # job starts in queued state
        self.assertNotIn("warnings", data)     # no warnings — this text has no secrets


    def test_submit_intent_too_short_is_rejected(self):
        # Text under 10 characters should be rejected
        response = client.post("/intent", data={"text": "short"}, headers=_auth_headers())

        self.assertEqual(response.status_code, 422)  # 422 = Unprocessable Entity (validation failed)


    def test_submit_intent_redacts_secrets(self):
        # A text that contains what looks like an API key
        text = "My system uses sk-ant-api03-AAABBBCCCDDDEEEFFFGGGHHH to call the AI"

        response = client.post("/intent", data={"text": text}, headers=_auth_headers())

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("job_id", data)
        # A warning should be present because a secret was detected
        self.assertIn("warnings", data)

        # The stored job text must NOT contain the raw secret
        stored_job = jobs.get_job(data["job_id"])
        self.assertNotIn("sk-ant-api03", stored_job.intent_text)  # secret was redacted


    def test_submit_intent_with_txt_file_combines_text_and_file(self):
        response = client.post(
            "/intent",
            data={"text": "A note about the system:"},
            files={"file": ("notes.txt", b"Users upload photos and browse a feed.", "text/plain")},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        stored_job = jobs.get_job(response.json()["job_id"])
        self.assertIn("A note about the system:", stored_job.intent_text)
        self.assertIn("Users upload photos and browse a feed.", stored_job.intent_text)


    def test_submit_intent_with_only_a_file_no_typed_text(self):
        response = client.post(
            "/intent",
            files={"file": ("notes.md", b"# A food delivery app for 500 users", "text/markdown")},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        stored_job = jobs.get_job(response.json()["job_id"])
        self.assertIn("A food delivery app for 500 users", stored_job.intent_text)


    def test_submit_intent_rejects_unsupported_file_type(self):
        response = client.post(
            "/intent",
            data={"text": "some prompt text here"},
            files={"file": ("doc.pdf", b"%PDF-1.4 fake pdf bytes", "application/pdf")},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 400)


    def test_submit_intent_rejects_oversized_file(self):
        big = b"x" * (2 * 1024 * 1024 + 1)   # one byte over the 2MB cap
        response = client.post(
            "/intent",
            files={"file": ("notes.txt", big, "text/plain")},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 400)


    def test_submit_intent_rejects_non_utf8_file(self):
        response = client.post(
            "/intent",
            files={"file": ("notes.txt", b"\xff\xfe\x00\x01 not valid utf-8", "text/plain")},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 400)


    def test_submit_intent_combined_text_still_enforces_length_bounds(self):
        # An empty file + no typed text should still trip the 10-char floor, same as
        # the plain too-short case above, just reached via the file path.
        response = client.post(
            "/intent",
            files={"file": ("notes.txt", b"hi", "text/plain")},
            headers=_auth_headers(),
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
