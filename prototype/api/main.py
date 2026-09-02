"""Keystone API — a thin FastAPI surface over the deterministic engine + council.

Prime directive: the council reasons (it emits ADRs only); `simulate()` is the ONLY
source of numbers. This module just orchestrates the existing seams and serialises
the result — it never computes a metric itself.
"""
from __future__ import annotations

import dataclasses
import math
import os

from starlette.concurrency import run_in_threadpool

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from keystone.blueprints.url_shortener import build as build_url_shortener
from keystone.council import make_council
from keystone.simulation import simulate
from keystone.ingestion import scan_and_redact_secrets
from api.auth import AuthUser, get_current_user
from api.jobs import create_job, get_job
from api.worker import run_pipeline

app = FastAPI(title="Keystone API", version="0.1.0")

# CORS. Now that Supabase-JWT auth gates every non-health route (#10), the API carries
# per-user data and a wildcard origin is no longer acceptable. ALLOWED_ORIGINS is a
# comma-separated list from the environment (dev default: the local Next.js frontend).
# Credentials stay OFF — the JWT travels in the Authorization header, not a cookie, so
# the browser never needs allow_credentials=True (and pairing it with a wildcard origin
# is forbidden by spec anyway).
_allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Starlette's multipart parser buffers an uploaded file's *entire* body — spooling it to a
# real temp file on disk past 1MB — before a route's own File()/Form() params are even
# resolved, let alone before the route body runs. So /intent's own MAX_UPLOAD_BYTES check
# (below) can only reject an oversized upload AFTER the whole thing has already been
# received and buffered. This pre-parse check on the advertised Content-Length rejects
# grossly oversized requests before Starlette starts reading the body at all, bounding the
# actual resource cost. It's a blunt, request-wide cap (not per-part) — proportionate to
# this API's current single-tenant-dev-demo threat model, not a substitute for real
# streaming/part-level limits if this ever takes untrusted internet traffic.
_MAX_REQUEST_BYTES = 4 * 1024 * 1024   # 4MB — headroom over /intent's 2MB file cap for multipart overhead


@app.middleware("http")
async def _reject_oversized_requests(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit() and int(content_length) > _MAX_REQUEST_BYTES:
        return Response(status_code=413, content="request body too large")
    return await call_next(request)


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


@app.post("/design")
def design(req: DesignRequest, user: AuthUser = Depends(get_current_user)) -> dict:
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

# Uploaded documents are combined with any typed text and run through the harm-floor
# secret scan before storage — consistent with the no-retention ethos already governing
# ingestion (ADR-002): nothing here writes the intent text anywhere but the job record.
# Note the underlying multipart parser (Starlette) may itself spool a large file part to
# a temp file before this handler ever runs (see `_reject_oversized_requests` above) —
# this app never does so itself, but that framework-level behavior means "never touches
# disk" isn't a claim this endpoint can make on its own. Cap kept small since only
# plain-text formats are supported (no PDF parsing — deliberately deferred, see PR).
MAX_UPLOAD_BYTES = 2 * 1024 * 1024   # 2MB
_ALLOWED_UPLOAD_SUFFIXES = (".txt", ".md")


@app.post("/intent")
async def submit_intent(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    file: UploadFile | None = File(None),
    user: AuthUser = Depends(get_current_user),
) -> dict:
    combined_text = text.strip()
    if file is not None:
        if not file.filename or not file.filename.lower().endswith(_ALLOWED_UPLOAD_SUFFIXES):
            raise HTTPException(status_code=400, detail="only .txt and .md files are supported")
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="file too large (2MB max)")
        try:
            file_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="file must be UTF-8 text")
        combined_text = f"{combined_text}\n\n{file_text}".strip() if combined_text else file_text.strip()

    if not (10 <= len(combined_text) <= 10_000):
        raise HTTPException(
            status_code=422,
            detail="combined text (prompt + file, if any) must be between 10 and 10,000 characters",
        )

    # Scan the raw text for secrets BEFORE storing anything (harm floor rule).
    clean_text, secrets_found = scan_and_redact_secrets(combined_text)

    # Create a job record and get back a job_id straight away. create_job() is a
    # synchronous Supabase/Postgres call (jobs.py) — run it off the event loop so it
    # can't stall other requests while waiting on that round-trip (this handler is
    # `async def` for the file upload, which means it's no longer auto-threadpooled).
    job = await run_in_threadpool(create_job, intent_text=clean_text, secrets_found=secrets_found,
                                  user_id=user.user_id, access_token=user.access_token)


    # Register the pipeline to run AFTER this response is sent - never blocks the caller.
    background_tasks.add_task(run_pipeline, job.job_id, job.intent_text, user.access_token)
    
    # Build the response. warnings tells the frontend if any secrets were redacted.
    response: dict = {"job_id": job.job_id, "status": job.status}
    if secrets_found:
        response["warnings"] = [f"secrets redacted on intake: {', '.join(secrets_found)}"]

    return response

@app.get("/jobs/{job_id}")
def get_job_status(job_id: str, user: AuthUser = Depends(get_current_user)) -> dict:
    # {job_id} in the decorator becomes the job_id argument — FastAPI extracts it from the URL
    job = get_job(job_id, user_id=user.user_id, access_token=user.access_token)

    if job is None:
        # 404 = "Not Found" - correct code when the resource simply doesn't exist
        raise HTTPException(status_code=404, detail="job not found")
    
    # Always include id and status; only add error field when something went wrong
    response: dict = {"job_id": job.job_id, "status": job.status}
    if job.status == "error":
        response["error"] = job.error

    return response  # FastAPI auto-converts this dict to JSON

@app.get("/jobs/{job_id}/report", response_model=None)
def get_job_report(
    job_id: str,
    request: Request,
    fmt: str = "json",
    user: AuthUser = Depends(get_current_user),
):
    # `fmt` is a query param — client passes ?fmt=markdown in the URL
    # `request` gives access to HTTP headers the client sent
    job = get_job(job_id, user_id=user.user_id, access_token=user.access_token)

    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    if job.status != "done":
        # Report doesn't exist yet — tell the client what state the job is in
        raise HTTPException(status_code=404, detail=f"report not ready — job is '{job.status}'")

    if job.result is None:
        # Should never happen — done jobs always have a result — but guard defensively
        raise HTTPException(status_code=500, detail="report missing — this is a server bug")

    # Two ways a client can ask for markdown:
    # 1. ?fmt=markdown in the URL
    # 2. Accept: text/markdown in the request headers (the standard HTTP way)
    accept_header = request.headers.get("accept", "")  # empty string if header not sent
    want_markdown = fmt == "markdown" or "text/markdown" in accept_header

    if want_markdown:
        # Response() lets us return plain text instead of JSON
        return Response(content=job.result, media_type="text/markdown")

    # Default: return JSON — FastAPI serialises the dict automatically
    return {"job_id": job.job_id, "status": job.status, "report": job.result}

if __name__ == "__main__":
    import uvicorn

    # Dev entrypoint only (host/port/reload are dev conveniences). Production launches via a
    # process manager per ADR-003, not this block.
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
