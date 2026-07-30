from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from api.main import app
from auth_test_helpers import (
    make_forged_alg_header_token,
    make_hs256_confusion_token,
    make_test_token,
    patch_jwks,
    set_test_supabase_url,
)

client = TestClient(app)


class TestAuth(unittest.TestCase):
    def setUp(self):
        set_test_supabase_url(self)
        patch_jwks(self)

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

    def test_missing_exp_is_rejected(self):
        # PyJWT only validates exp if present — options={"require": [...]} in
        # auth.py is what makes an exp-less token get rejected instead of treated
        # as never-expiring.
        token = make_test_token(exp_delta=None)
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_unsupported_algorithm_is_rejected_not_500(self):
        # A token whose header just claims alg=RS256 — this project's JWKS only
        # holds an EC key, so algorithms=["ES256"] in auth.py must reject this
        # cleanly (401) rather than PyJWT raising a bare TypeError trying to read
        # the EC key as an RSA key (which would surface as an unhandled 500).
        token = make_forged_alg_header_token("RS256")
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_hs256_confusion_token_is_rejected(self):
        # Regression test locking in a defense we already have: even though the
        # "secret" here (the PEM-encoded public key) is technically valid HMAC
        # input and the signature genuinely matches, ES256-only in the allow-list
        # means an HS256-header token is rejected before that signature is ever
        # checked.
        token = make_hs256_confusion_token()
        response = client.post(
            "/design", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_jwks_connection_failure_is_rejected_not_500(self):
        # Regression test locking in fail-closed behaviour: if Supabase's JWKS
        # endpoint is unreachable, that must surface as a clean 401, not a 500 —
        # PyJWKClientConnectionError is a PyJWTError subclass, so the existing
        # `except jwt.PyJWTError` in auth.py already covers it.
        token = make_test_token()
        with patch.object(
            jwt.PyJWKClient,
            "get_signing_key_from_jwt",
            side_effect=jwt.exceptions.PyJWKClientConnectionError("JWKS endpoint unreachable"),
        ):
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
