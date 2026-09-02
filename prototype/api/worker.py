from __future__ import annotations

import logging  # for recording what happens during the pipeline run
import os

from keystone.council import make_council       # reasons about design → ADRs
from keystone.cost_meter import CostMeter
from keystone.ingestion import Source, make_ingestor, scan_and_redact_secrets
from keystone.claude_council import _redact_engine_metrics
from keystone.report import render              # produces the markdown report
from keystone.simulation import simulate        # the ONLY source of numbers
from keystone.grounding import ground_model
from api.jobs import update_job  # updates job status as the pipeline progresses

log = logging.getLogger("keystone.worker")


def _make_meter() -> CostMeter | None:
    """One CostMeter shared across this job's ingestion + council calls, so
    LLM_MAX_SPEND_USD (if set) is a total cap on the whole job, not two separate budgets.
    Unset -> None, matching CostMeter's own uncapped default (fully backward compatible;
    a stub-provider job never touches an LLM at all, so this is a no-op either way)."""
    cap = os.getenv("LLM_MAX_SPEND_USD")
    if not cap:
        return None
    try:
        return CostMeter(max_micro_usd=int(float(cap) * 1_000_000))
    except ValueError:
        log.warning("LLM_MAX_SPEND_USD=%r is not a number; ignoring (uncapped)", cap)
        return None


def run_pipeline(job_id: str, intent_text: str) -> None:
    """Run the full pipeline for one job. Called in the background after /intent responds.

    Updates job status at each stage so the frontend can show progress:
    queued → processing → done (or error)
    """
    try:
        update_job(job_id, status="processing")  # tell the store we've started — inside the
        # try so a failure here still lands on status="error" below, instead of leaving the job
        # stuck at its initial status forever with no error ever recorded.
        meter = _make_meter()  # shared ingest+council spend cap for this job, if configured

        # Step 1: ingest — turn the raw intent text into a structured SystemModel
        ingestor = make_ingestor(meter=meter)
        source = Source(text=intent_text, kind="text", name="user-intent")
        ingest_result = ingestor.ingest(source)

        # Step 2: ground - attach GROUNDED evidence + cost-rate sections to the model
        model = ground_model(ingest_result.model)

        # Step 3: council — reason about the model, produce Architecture Decision Records
        council = make_council(meter=meter)
        adrs = council.design(model)

        # Step 4: simulate — run the deterministic engine (prime directive: ONLY source of numbers)
        sim_result = simulate(model)

        # Step 5: render — combine everything into a markdown report
        report = render(model, adrs, sim_result)

        update_job(job_id, status="done", result=report)  # store the finished report
        log.info("job %s completed successfully", job_id)

    except Exception as exc:
        # cap + scrub the error before storing or logging — IngestError can carry up to 400 chars
        # of raw LLM output, which may contain secrets or model-produced numbers (harm floor)
        raw_msg = str(exc)[:500]                          # cap length
        safe_msg, _ = scan_and_redact_secrets(raw_msg)   # redact any secrets in the error text
        safe_msg, _ = _redact_engine_metrics(safe_msg)   # also strip any stray numbers
        log.error("job %s failed: %s", job_id, safe_msg)
        update_job(job_id, status="error", error=safe_msg)