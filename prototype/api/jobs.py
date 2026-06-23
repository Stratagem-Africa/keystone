
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

@dataclass
class Job:
    job_id: str
    status: str   # "queued" | "processing" | "done" | "error"
    intent_text: str
    secrets_found: list[str] = field(default_factory=list)

# In-memory store — lives in process memory only, lost on restart.
# Epic 3.4 replaces this with a Postgres table.
_store: dict[str, Job] = {}

def create_job(intent_text: str, secrets_found: list[str]) -> Job:
    job_id = str(uuid.uuid4())
    job = Job(job_id=job_id, status="queued", intent_text=intent_text, secrets_found=secrets_found)
    _store[job_id] = job
    return job

def get_job(job_id: str) -> Job | None:
    return _store.get(job_id)