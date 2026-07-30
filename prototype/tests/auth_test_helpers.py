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

import base64
import hashlib
import hmac
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey

TEST_SUPABASE_URL = "https://test-project.supabase.co"


def set_test_supabase_url(testcase: unittest.TestCase) -> None:
    """Set SUPABASE_URL for one test, then restore whatever was there before —
    not just unset it, so a test run alongside a real `.env` (e.g. locally) doesn't
    leak the test URL into whichever test file happens to run afterward."""
    original = os.environ.get("SUPABASE_URL")
    os.environ["SUPABASE_URL"] = TEST_SUPABASE_URL

    def _restore() -> None:
        if original is None:
            os.environ.pop("SUPABASE_URL", None)
        else:
            os.environ["SUPABASE_URL"] = original

    testcase.addCleanup(_restore)

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
    exp_delta: int | None = 3600,
    private_key: EllipticCurvePrivateKey | None = None,
) -> str:
    """Mint a JWT shaped like a real Supabase token, signed with the module's test key
    by default — pass a different `private_key` to simulate a signature that won't
    match what patch_jwks() hands the verifier, or `exp_delta=None` to omit the exp
    claim entirely (real Supabase tokens always carry one; this is for testing that
    a token missing it gets rejected, not silently treated as never-expiring)."""
    payload = {"aud": aud, "iss": issuer, "role": role}
    if exp_delta is not None:
        payload["exp"] = int(time.time()) + exp_delta
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(
        payload, private_key or _private_key, algorithm="ES256", headers={"kid": "test-kid"}
    )


def make_forged_alg_header_token(alg: str) -> str:
    """Build a token whose header just CLAIMS a given algorithm, with a garbage
    signature — a token's header is plain unsigned base64 JSON, so anyone can write
    any `alg` value into it. Used to test that an allow-list mismatch (e.g. a claimed
    alg this project doesn't actually use) is rejected cleanly with 401, not a 500
    from PyJWT trying to load the wrong kind of key."""
    header = {"alg": alg, "kid": "test-kid", "typ": "JWT"}
    payload = {
        "aud": "authenticated",
        "iss": f"{TEST_SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "sub": "user-123",
        "exp": int(time.time()) + 3600,
    }

    def _b64(d: dict) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=")

    return (_b64(header) + b"." + _b64(payload) + b"." + b"garbage-signature").decode()


def make_hs256_confusion_token() -> str:
    """The classic RS/ES-vs-HS "algorithm confusion" attack: a public key is not
    secret, so anyone can PEM-encode it and use those bytes as an HMAC secret,
    producing a token that's genuinely, correctly HS256-signed — just with a "secret"
    the whole world can read. This only fails to fool the verifier if HS256 is
    absent from auth.py's algorithms allow-list (it is — ES256 only).

    Built by hand with the stdlib `hmac` module rather than jwt.encode(): PyJWT's own
    encode() refuses to use a PEM-shaped key as an HMAC secret (InvalidKeyError) — a
    real safety feature, but it means it can't be used to construct this attack
    token. A real attacker computing HMAC-SHA256 with any other library wouldn't be
    stopped by that guard, so this builds the token the way they would."""
    public_pem = _public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    header = {"alg": "HS256", "kid": "test-kid", "typ": "JWT"}
    payload = {
        "aud": "authenticated",
        "iss": f"{TEST_SUPABASE_URL}/auth/v1",
        "role": "authenticated",
        "sub": "user-123",
        "exp": int(time.time()) + 3600,
    }

    def _b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    signing_input = _b64(json.dumps(header).encode()) + b"." + _b64(json.dumps(payload).encode())
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64(signature)).decode()


def patch_jwks(testcase: unittest.TestCase) -> None:
    """Make api.auth's JWKS lookup return our in-memory public key, no network call."""
    patcher = patch.object(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        return_value=SimpleNamespace(key=_public_key),
    )
    patcher.start()
    testcase.addCleanup(patcher.stop)
