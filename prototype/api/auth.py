"""Supabase-JWT verification — the API's only gate on "who is calling."

Verification scheme: Supabase's asymmetric JWT Signing Keys (ES256, key rotation via
a public JWKS endpoint) — confirmed against a real token from the team's dev project
(its header is `{"alg": "ES256", "kid": "..."}`), not the legacy HS256 shared secret
the dashboard also shows. Verifying against a PUBLIC key set means no shared secret
is needed at all: SUPABASE_URL is enough to locate `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`.

Fail-closed by design: unlike COUNCIL_PROVIDER/KB_PROVIDER (which default to a safe
stub when unconfigured), auth has no safe default. If SUPABASE_URL isn't set, every
protected route rejects the request — it never silently lets traffic through.

Gotcha this file exists to handle correctly: Supabase's signing keys sign the anon key,
the service-role key, AND real user-session tokens. Signature validity alone doesn't
prove "this is a logged-in user" — the anon/service keys would pass signature +
expiry + audience checks too. The `role` claim is the actual discriminator: user
sessions carry role="authenticated"; the static API keys don't. This must be checked
explicitly, not inferred from a valid signature.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)

# One PyJWKClient per Supabase project, reused across requests — it caches the
# fetched public key set internally, so this avoids re-fetching the JWKS endpoint
# on every single request.
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    client = _jwks_clients.get(supabase_url)
    if client is None:
        client = jwt.PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")
        _jwks_clients[supabase_url] = client
    return client


@dataclass
class AuthUser:
    user_id: str
    email: str | None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> AuthUser:
    """FastAPI dependency: verify the request's Supabase JWT or raise 401."""
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        # Fail closed: an unconfigured server must not accept traffic as if auth
        # were disabled (that's for COUNCIL_PROVIDER/KB_PROVIDER-style features,
        # not auth — see harm floor, CLAUDE.md).
        raise HTTPException(status_code=401, detail="auth not configured")

    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")

    try:
        jwks_client = _get_jwks_client(supabase_url)
        signing_key = jwks_client.get_signing_key_from_jwt(credentials.credentials)
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            # ES256 ONLY — this project's JWKS holds one EC (elliptic-curve) key, so
            # RS256 must not be listed here even though it's also "asymmetric": a
            # forged token that just CLAIMS alg=RS256 would make PyJWT try to read
            # the EC key as an RSA key, raising a bare TypeError (not a PyJWTError)
            # that the except below wouldn't catch — an unauthenticated 500, not a
            # 401. Only list algorithms this project's key set can actually satisfy.
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{supabase_url}/auth/v1",
            # Reject a token missing any of these outright, rather than only checking
            # them when present. Real Supabase tokens always carry all four — this is
            # defense-in-depth against a hand-crafted token reaching this far.
            options={"require": ["exp", "aud", "iss", "sub"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    # Reject the anon/service-role keys if handed to us as a bearer token — they
    # verify fine (same signing keys) but aren't a logged-in user's session.
    if payload.get("role") != "authenticated":
        raise HTTPException(status_code=401, detail="not a user session token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="token missing subject")

    return AuthUser(user_id=user_id, email=payload.get("email"))
