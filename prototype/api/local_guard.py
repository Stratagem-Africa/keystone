"""The loopback guard for `/local/*` — the AI routes that only the person at the keyboard may use (#204).

Why these routes exist apart from the public ones: the public `/generate` is pinned to the offline
path (main.py) because an unauthenticated endpoint that reaches a live LLM is an anonymous,
unmetered spend endpoint. The `/local/*` routes DO reach the LLM — on the operator's own Claude
subscription via `llm_cli` — so they must refuse anyone who is not that operator.

Why they may skip the Supabase login: auth exists to stop one user reading another's data. A route
that refuses every caller except the one at this machine's keyboard has exactly one user, so the
guard does the job the login did. **If this guard is ever weakened, the auth question comes back.**

Fail closed, three checks, all required:

1. `KEYSTONE_ALLOW_CLI_IN_SERVER=1` — the SAME single, documented override `llm_cli._refuse_if_served`
   honours. `scripts/keystone-local.sh` sets it only after proving its bind address is loopback, so a
   server started any other way (a deploy, `uvicorn --host 0.0.0.0`) never has it.
2. The TCP peer is loopback — the request physically came from this machine.
3. The `Host` header names loopback — stops DNS rebinding, where a web page on some other site
   points its own hostname at 127.0.0.1 and gets the browser to call this API "same-origin".
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request

from api.auth import AuthUser

# The one identity every /local/* request runs as. An empty access token makes jobs.py stay
# memory-only (no Supabase client), so nothing from a local run is written to the shared database.
LOCAL_USER = AuthUser(user_id="local", email=None, access_token="")

_LOOPBACK_PEERS = {"127.0.0.1", "::1"}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _host_name(host_header: str) -> str:
    """'127.0.0.1:8000' -> '127.0.0.1', '[::1]:8000' -> '[::1]', 'localhost' -> 'localhost'."""
    if host_header.startswith("["):                     # IPv6 literal: keep the brackets, drop the port
        return host_header.split("]", 1)[0] + "]"
    return host_header.rsplit(":", 1)[0] if ":" in host_header else host_header


def local_refusal(request: Request) -> str | None:
    """Why this request may NOT use the local AI routes, or None if it may. Never raises."""
    if os.getenv("KEYSTONE_ALLOW_CLI_IN_SERVER") != "1":
        return ("the local AI routes are off. They drive YOUR Claude subscription, so they only run "
                "when Keystone is started by scripts/keystone-local.sh, which proves the server is "
                "loopback-only before setting KEYSTONE_ALLOW_CLI_IN_SERVER=1. A served API must never "
                "answer other people out of one person's account.")
    peer = request.client.host if request.client else ""
    if peer not in _LOOPBACK_PEERS:
        return f"the local AI routes only answer this machine (request came from {peer or 'unknown'})."
    host = _host_name(request.headers.get("host", "").lower())
    if host not in _LOOPBACK_HOSTS:
        return f"the local AI routes only answer a loopback Host header (got {host or 'none'})."
    return None


def require_local_operator(request: Request) -> AuthUser:
    """FastAPI dependency: let the person at this machine through, refuse everyone else loudly (403)."""
    reason = local_refusal(request)
    if reason:
        raise HTTPException(status_code=403, detail=reason)
    return LOCAL_USER
