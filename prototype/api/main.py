"""Keystone API — a thin FastAPI surface over the deterministic engine + council.

Prime directive: the council reasons (it emits ADRs only); `simulate()` is the ONLY
source of numbers. This module just orchestrates the existing seams and serialises
the result — it never computes a metric itself.
"""
from __future__ import annotations

import dataclasses
import math

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from keystone.blueprints.url_shortener import build as build_url_shortener
from keystone.council import make_council
from keystone.simulation import simulate
from keystone.ingestion import scan_and_redact_secrets
from api.jobs import create_job

app = FastAPI(title="Keystone API", version="0.1.0")

# CORS. There is no auth yet, so the API exposes no per-user/credentialed data and a
# wildcard origin is acceptable for dev — but ONLY with credentials OFF. Never pair
# allow_origins=["*"] with allow_credentials=True: the spec forbids it, so the browser
# would instead reflect any caller's Origin and allow credentialed cross-site calls.
# When Supabase-JWT auth lands (#20), replace ["*"] with an explicit allow-list of origins
# (JWT travels in the Authorization header, so credentials can stay off).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize(obj):
    """Replace non-finite floats (inf/nan) with None so the result is JSON-serialisable.

    `simulate()` legitimately emits inf — e.g. an idle component's utilisation and the
    breakpoint at zero load. The JSON encoder rejects inf/nan, so we scrub them (recursively,
    because they can be nested anywhere in the result tree) before the response goes out.
    """
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    return obj


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


class DesignRequest(BaseModel):
    # A plain field with a default (not Optional): an omitted `system_rps` becomes 10_000.
    # `gt=0` rejects zero/negative load and `le` caps it, so bad input fails fast with a
    # clean 422 at the edge and the engine only ever sees a sane value.
    system_rps: float = Field(10_000, gt=0, le=10_000_000)

class IntentRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=10_000)


@app.post("/design")
def design(req: DesignRequest) -> dict:
    """Build the reference model at the requested load, reason over it (ADRs), then simulate."""
    model = build_url_shortener(system_rps=req.system_rps)

    council = make_council()
    adrs = council.design(model)        # council reasons → ADRs only, never numbers

    sim_result = simulate(model)        # simulate() is the ONLY source of numbers

    # Already-sanitised plain dict: FastAPI serialises it (and can validate it against a
    # response_model later). No need to wrap it in JSONResponse ourselves.
    return _sanitize({
        "model": model.name,
        "simulation": dataclasses.asdict(sim_result),
        "adrs": [dataclasses.asdict(adr) for adr in adrs],
    })

@app.post("/intent")
def submit_intent(req: IntentRequest) -> dict:
    # Scan the raw text for secrets BEFORE storing anything (harm floor rule).
    clean_text, secrets_found = scan_and_redact_secrets(req.text)
    # Create a job record and get back a job_id straight away.
    job = create_job(intent_text=clean_text, secrets_found=secrets_found)
    # Build the response. warnings tells the frontend if any secrets were redacted.
    response: dict = {"job_id": job.job_id, "status": job.status}
    if secrets_found:
        response["warnings"] = [f"secrets redacted on intake: {', '.join(secrets_found)}"]

    return response


    


if __name__ == "__main__":
    import uvicorn

    # Dev entrypoint only (host/port/reload are dev conveniences). Production launches via a
    # process manager per ADR-003, not this block.
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
