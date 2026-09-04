
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field

log = logging.getLogger("keystone.jobs")


def _client_for(access_token: str | None):
    """Build a fresh Supabase client scoped to THIS ONE caller's identity.

    Never shared/cached across requests: this app serves requests concurrently, so
    mutating a shared client's auth token per-call would race between two requests,
    risking one user's rows leaking to another mid-flight. `jobs` has row-level
    security enabled with a real policy keyed on auth.uid() (0003_jobs_table.sql) —
    the anon key alone proves nothing; it's THIS caller's own JWT, set via
    `.postgrest.auth()`, that lets PostgREST resolve auth.uid() to them for every
    call this client instance makes, so the DB itself only ever returns their rows.
    Falls back to None (memory-only) if SUPABASE_URL/ANON_KEY are unset, no token
    was given, or client init fails — same graceful-degrade design as before."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key or not access_token:
        return None
    try:
        from supabase import create_client
        client = create_client(url, key)
        client.postgrest.auth(access_token)
        return client
    except Exception as exc:
        log.warning("Supabase client init failed, using memory only: %s", exc)
        return None


@dataclass
class Job:
    job_id: str
    status: str   # "queued" | "processing" | "done" | "error"
    intent_text: str
    user_id: str   # who submitted it — the ownership boundary for get_job below
    secrets_found: list[str] = field(default_factory=list)
    result: str | None = None      # markdown report, filled in when status = "done"
    arch_map: dict | None = None   # engine-driven architecture map (keystone.arch_map.build_arch_map), same timing as result
    error: str | None = None       # error message, filled in when status = "error"

# In-memory fallback store — used when Postgres is not configured.
_store: dict[str, Job] = {}

def create_job(intent_text: str, secrets_found: list[str], *, user_id: str, access_token: str) -> Job:
    """Create a new queued job, owned by `user_id`, and persist it."""
    job_id = str(uuid.uuid4()) # random unique ID
    job = Job(job_id=job_id, status="queued", intent_text=intent_text,
              user_id=user_id, secrets_found=secrets_found)
    _store[job_id] = job # always write to memory (fast, works offline)

    db = _client_for(access_token)
    if db:
        try:
            db.table("jobs").insert({
                "job_id": job_id,
                "user_id": user_id,
                "status": "queued",
                "intent_text": intent_text,
                "secrets_found": secrets_found,
            }).execute()
        except Exception as exc:
            log.warning("Postgres insert failed, using memory only: %s", exc)

    return job

def get_job(job_id: str, *, user_id: str, access_token: str) -> Job | None:
    """Fetch a job by ID, scoped to `user_id` — Postgres first, memory fallback.

    The Postgres path is scoped by the DB itself (RLS + the caller's own JWT set on
    the client), so it can never return another user's row. The in-memory fallback
    has no RLS to lean on, so ownership is checked explicitly here too — otherwise a
    server running without Postgres configured would hand back ANY job whose id was
    known/guessed, regardless of who's asking."""
    db = _client_for(access_token)
    if db:
        try:
            rows = db.table("jobs").select("*").eq("job_id", job_id).execute()
            if rows.data:
                r = rows.data[0] # First and only matching row
                return Job(
                    job_id=r["job_id"],
                    status=r["status"],
                    intent_text=r["intent_text"],
                    user_id=r["user_id"],
                    secrets_found=r.get("secrets_found") or [],
                    result=r.get("result"),
                    arch_map=r.get("arch_map"),
                    error=r.get("error"),
                )
        except Exception as exc:
            log.warning("Postgres get failed, falling back to memory: %s", exc)

    job = _store.get(job_id) # Memory fallback
    if job is not None and job.user_id != user_id:
        return None   # not yours — treat identically to "doesn't exist" (no ownership oracle)
    return job


def update_job(job_id: str, *, access_token: str, status: str,
               result: str | None = None, arch_map: dict | None = None,
               error: str | None = None) -> None:
    """Update a job's status and optionally its result, architecture map, or error message.

    Called only by the pipeline that owns this exact job_id (worker.run_pipeline),
    never with an attacker-supplied job_id, so no separate ownership check is needed
    here — the Postgres path is still RLS-scoped via the caller's own token."""
    # update memory store if the job is there
    job = _store.get(job_id)
    if job:
        job.status = status
        if result is not None:     # only overwrite when caller passes a value
            job.result = result
        if arch_map is not None:   # same — a status-only update won't wipe the stored map
            job.arch_map = arch_map
        if error is not None:      # same — a status-only update won't wipe the stored result
            job.error = error

    db = _client_for(access_token)
    if db:
        try:
            data: dict = {"status": status}
            if result is not None:
                data["result"] = result
            if arch_map is not None:
                data["arch_map"] = arch_map
            if error is not None:
                data["error"] = error
            db.table("jobs").update(data).eq("job_id", job_id).execute()
        except Exception as exc:
            log.warning("Postgres update failed, in-memory store updated if job was local: %s", exc)
