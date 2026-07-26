"""Shared test helper for Supabase-JWT auth (#10).

Real Supabase tokens are signed with an asymmetric ES256 key, verified via a public
JWKS endpoint (see prototype/api/auth.py) — there's no shared secret to hand the API
under test. So this module generates one in-memory EC keypair per test process and
provides `patch_jwks()`, which makes api.auth's JWKS lookup return that keypair's
public half instead of making a real HTTP call. scripts/check.sh explicitly strips
SUPABASE_URL before running the suite specifically to keep it hermetic/offline — a
real network call here would defeat that.
"""
from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

TEST_SUPABASE_URL = "https://test-project.supabase.co"

# The "official" keypair — patch_jwks() makes api.auth treat its public half as the
# project's real signing key, for every test in the process.
_private_key = ec.generate_private_key(ec.SECP256R1())
_public_key = _private_key.public_key()


def make_test_token(
    *,
    role: str = "authenticated",
    aud: str = "authenticated",
    issuer: str = f"{TEST_SUPABASE_URL}/auth/v1",
    sub: str | None = "user-123",
    exp_delta: int = 3600,
    private_key: EllipticCurvePrivateKey | None = None,
) -> str:
    """Mint a JWT shaped like a real Supabase token, signed with the module's test key
    by default — pass a different `private_key` to simulate a signature that won't
    match what patch_jwks() hands the verifier."""
    payload = {
        "aud": aud,
        "iss": issuer,
        "role": role,
        "exp": int(time.time()) + exp_delta,
    }
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(
        payload, private_key or _private_key, algorithm="ES256", headers={"kid": "test-kid"}
    )


def patch_jwks(testcase: unittest.TestCase) -> None:
    """Make api.auth's JWKS lookup return our in-memory public key, no network call."""
    patcher = patch.object(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        return_value=SimpleNamespace(key=_public_key),
    )
    patcher.start()
    testcase.addCleanup(patcher.stop)
