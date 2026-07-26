from __future__ import annotations

import os
import unittest

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from api.main import app
from auth_test_helpers import TEST_SUPABASE_URL, make_test_token, patch_jwks

client = TestClient(app)


class TestAuth(unittest.TestCase):
    def setUp(self):
        self._orig_url = os.environ.get("SUPABASE_URL")
        os.environ["SUPABASE_URL"] = TEST_SUPABASE_URL
        patch_jwks(self)

    def tearDown(self):
        if self._orig_url is None:
            os.environ.pop("SUPABASE_URL", None)
        else:
            os.environ["SUPABASE_URL"] = self._orig_url

    def test_health_is_public(self):
        # No token attached at all — /health must stay reachable for liveness probes.
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_unconfigured_url_fails_closed(self):
        os.environ.pop("SUPABASE_URL", None)
        token = make_test_token()
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("not configured", response.json()["detail"])

    def test_missing_header_is_rejected(self):
        response = client.post("/design", json={})
        self.assertEqual(response.status_code, 401)

    def test_malformed_scheme_is_rejected(self):
        token = make_test_token()
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Basic {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_garbage_token_is_rejected(self):
        response = client.post(
            "/design", json={}, headers={"Authorization": "Bearer not-a-jwt"}
        )
        self.assertEqual(response.status_code, 401)

    def test_expired_token_is_rejected(self):
        token = make_test_token(exp_delta=-3600)
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_key_is_rejected(self):
        # Signed with a DIFFERENT private key than the one patch_jwks() hands the
        # verifier as "the project's real public key" — signature must not match.
        other_key = ec.generate_private_key(ec.SECP256R1())
        token = make_test_token(private_key=other_key)
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_audience_is_rejected(self):
        token = make_test_token(aud="not-authenticated")
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_issuer_is_rejected(self):
        token = make_test_token(issuer="https://someone-elses-project.supabase.co/auth/v1")
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_anon_key_role_is_rejected(self):
        # Supabase's signing keys sign the anon/service-role keys too — a valid
        # signature isn't enough, the role claim must say "authenticated".
        token = make_test_token(role="anon")
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("not a user session", response.json()["detail"])

    def test_missing_subject_is_rejected(self):
        token = make_test_token(sub=None)
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_token_is_accepted(self):
        token = make_test_token()
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("simulation", response.json())


if __name__ == "__main__":
    unittest.main()
