
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field

log = logging.getLogger("keystone.jobs")

_db_client = None

def _get_db():
    global _db_client
    if _db_client is not None:
        return _db_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    from supabase import create_client
    _db_client = create_client(url, key)
    return _db_client


@dataclass
class Job:
    job_id: str
    status: str   # "queued" | "processing" | "done" | "error"
    intent_text: str
    secrets_found: list[str] = field(default_factory=list)
    result: str | None = None   # markdown report, filled in when status = "done"
    error: str | None = None    # error message, filled in when status = "error"

# In-memory fallback store — used when Postgres is not configured.
_store: dict[str, Job] = {}

def create_job(intent_text: str, secrets_found: list[str]) -> Job:
    """Create a new queued job and persist it."""
    job_id = str(uuid.uuid4()) # random unique ID
    job = Job(job_id=job_id, status="queued", intent_text=intent_text, secrets_found=secrets_found)
    _store[job_id] = job # always write to memory (fast, works offline)

    db = _get_db()
    if db:
        try:
            db.table("jobs").insert({
                "job_id": job_id,
                "status": "queued",
                "intent_text": intent_text,
                "secrets_found": secrets_found,
            }).execute()
        except Exception as exc:
            log.warning("Postgres insert failed, using memort only: %s", exc)
    
    return job

def get_job(job_id: str) -> Job | None:
    """Fetch a job by ID — Postgres first, memory fallback."""
    db = _get_db()
    if db:
        try:
            rows = db.table("jobs").select("*").eq("job_id", job_id).execute()
            if rows.data:
                r = rows.data[0] # First and only matching row
                return Job(
                    job_id=r["job_id"],
                    status=r["status"],
                    intent_text=r["intent_text"],
                    secrets_found=r.get("secrets_found") or [],
                    result=r.get("result"),
                    error=r.get("error"),
                )
        except Exception as exc:
            log.warning("Postgres get failed, falling back to memory: %s", exc)
    
    return _store.get(job_id) # Memory fallback


def update_job(job_id: str, *, status: str, result: str | None = None, error: str | None = None) -> None:
    """Update a job's status and optionally its result or error message."""
    # update memory store if the job is there
    job = _store.get(job_id)
    if job:
        job.status = status
        job.result = result
        job.error = error

    db = _get_db()
    if db:
        try:
            data: dict = {"status": status}
            if result is not None:
                data["result"] = result
            if error is not None:
                data["error"] = error
            db.table("jobs").update(data).eq("job_id", job_id).execute()
        except Exception as exc:
            log.warning("Postgres update failed, memory still updated: %s", exc)