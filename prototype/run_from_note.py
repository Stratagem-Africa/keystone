"""Phase-1 demo: intent (a concept note) -> ingest -> council -> simulate -> report.

Shows the full loop from prose to a validated-design report. Defaults to $0/offline
(stub ingestor + stub council); set INGEST_PROVIDER=claude and/or COUNCIL_PROVIDER=claude
(+ ANTHROPIC_API_KEY) to activate the real LLM layers.

Run from prototype/:  python3 run_from_note.py
"""
from __future__ import annotations

import os

from _env import load_env, report_path
from keystone.council import make_council
from keystone.grounding import ground_model
from keystone.ingestion import Source, make_ingestor
from keystone.report import render
from keystone.confidence_bands import simulate_with_confidence

NOTE = """
We're building a URL shortener. Users paste a long URL and get a short code; hitting the
short code redirects them. Redirects vastly outnumber creates (very read-heavy). We expect
heavy traffic at launch. A web app behind a load balancer talks to a Postgres database;
hot redirects are served from a Redis cache.
"""

OUT = os.path.join(os.path.dirname(__file__), "outputs", "from_note_report.md")


def main() -> None:
    load_env()                              # activate local .env (council/grounding); existing env wins
    # 1. Ingest intent -> partial canonical model (+ assumptions, scan/injection notes).
    result = make_ingestor().ingest(Source(text=NOTE, name="URL Shortener (from note)"))
    model = ground_model(result.model)   # grounding activated (curated default; KB_PROVIDER=stub disables)
    # 2. Council reasons (stub by default). 3. The deterministic engine produces numbers.
    adrs = make_council().design(model)
    sim = simulate_with_confidence(model)   # output ranges from cited input uncertainty (values unchanged)
    # 4. Report with the mandatory honesty section.
    md = render(model, adrs, sim)
    out, provider = report_path(OUT)        # LIVE council -> gitignored *.local.md (never clobber the golden)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(md)

    print("=" * 70)
    print(f"KEYSTONE — intent -> validated design   ({model.name})")
    print("=" * 70)
    print(f"Council            : {provider}"
          + ("  (deterministic stub)" if provider == "stub" else "  (LIVE LLM — non-deterministic)"))
    for n in result.notes:
        print(f"  note: {n}")
    print(f"Components inferred : {', '.join(model.components)}")
    print(f"Domain flags       : {', '.join(model.domain_flags) or 'none'}")
    print(f"Bottleneck         : {sim.bottleneck_name} ({sim.bottleneck_utilization*100:.0f}% util)")
    print(f"Max safe load      : {sim.breakpoint_rps_safe:,.0f} rps (engine-computed)")
    print(f"Assumptions        : {len(model.assumptions)} (all editable)")
    print("-" * 70)
    print(f"Full report written to: outputs/{os.path.basename(out)}")


if __name__ == "__main__":
    main()
