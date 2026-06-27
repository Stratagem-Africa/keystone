from __future__ import annotations

import logging  # for recording what happens during the pipeline run

from keystone.council import make_council       # reasons about design → ADRs
from keystone.ingestion import Source, make_ingestor  # turns text → SystemModel
from keystone.report import render              # produces the markdown report
from keystone.simulation import simulate        # the ONLY source of numbers
from keystone.grounding import ground_model
from api.jobs import update_job  # updates job status as the pipeline progresses

log = logging.getLogger("keystone.worker")


def run_pipeline(job_id: str, intent_text: str) -> None:
    """Run the full pipeline for one job. Called in the background after /intent responds.

    Updates job status at each stage so the frontend can show progress:
    queued → processing → done (or error)
    """
    update_job(job_id, status="processing")  # tell the store we've started

    try:
        # Step 1: ingest — turn the raw intent text into a structured SystemModel
        ingestor = make_ingestor()
        source = Source(text=intent_text, kind="text", name="user-intent")
        ingest_result = ingestor.ingest(source)

        #Step 2: ground - attach GROUNDED evidence + cost-rate sections to the model
        model = ground_model(ingest_result.model)

        # Step 3: council — reason about the model, produce Architecture Decision Records
        council = make_council()
        adrs = council.design(model)

        # Step 4: simulate — run the deterministic engine (prime directive: ONLY source of numbers)
        sim_result = simulate(model)

        # Step 5: render — combine everything into a markdown report
        report = render(model, adrs, sim_result)

        update_job(job_id, status="done", result=report)  # store the finished report
        log.info("job %s completed successfully", job_id)

    except Exception as exc:
        # something went wrong — record the error so the frontend can show it
        log.error("job %s failed: %s", job_id, exc)
        update_job(job_id, status="error", error=str(exc))
