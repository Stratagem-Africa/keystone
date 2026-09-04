"""Tests for POST /generate — the stateless intent → deep-architecture endpoint (offline reference path)."""
import unittest

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestGenerateEndpoint(unittest.TestCase):
    def test_twitter_intent_returns_deep_arch_map(self):
        r = client.post("/generate", json={"intent": "I want to build a platform like Twitter"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("verdict", d)
        self.assertIsNotNone(d["verdict"]["bottleneck_id"])
        self.assertGreaterEqual(len(d["nodes"]), 12, "a deep architecture, not a sketch")
        self.assertTrue(all("icon" in n and "role" in n for n in d["nodes"]))

    def test_no_auth_required(self):
        # Stateless compute — like /simulate, NOT auth-gated.
        r = client.post("/generate", json={"intent": "a url shortener"})
        self.assertEqual(r.status_code, 200)

    def test_unknown_intent_still_returns_a_valid_startingpoint_with_catalogue(self):
        r = client.post("/generate", json={"intent": "a quantum weather oracle for llamas"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["nodes"])                 # a real, editable starting point
        self.assertIn("social platform", d["catalogue"])  # hint: try one of these offline

    def test_empty_intent_is_422(self):
        r = client.post("/generate", json={"intent": ""})
        self.assertEqual(r.status_code, 422)        # pydantic min_length rejects before the handler


if __name__ == "__main__":
    unittest.main()
