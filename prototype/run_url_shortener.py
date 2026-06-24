"""Phase-0 end-to-end run: intent -> model -> council -> simulate -> what-if -> report.

Run from the prototype/ directory:
    python3 run_url_shortener.py
"""
from __future__ import annotations

import os

from keystone.blueprints import url_shortener
from keystone.council import make_council
from keystone.grounding import enrich, ground_pricing
from keystone.knowledge_base import make_knowledge_base
from keystone.simulation import simulate
from keystone.report import render

OUT = os.path.join(os.path.dirname(__file__), "outputs", "url_shortener_report.md")


def build_and_render(kb=None):
    """The full loop, as a single source so the golden-report test renders EXACTLY what main() writes.

    `kb` defaults to the env-driven Knowledge Base (stub unless KB_PROVIDER=curated). Returns
    (model, sim, whatifs, markdown). Grounding is evidence-only here (override not set) — a strict
    no-op under the stub default, so the rendered report is byte-for-byte unchanged."""
    # 1. Canonical model (LLM-derived in product; hand-built here for validation).
    model = url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)

    # 1b. Attach cited KB evidence to the input numbers + the cost rates (ADR-006, the L0→L1 lever).
    #     Both are a strict no-op under the stub KB, so the rendered report is byte-for-byte unchanged.
    kb = kb if kb is not None else make_knowledge_base()
    model = enrich(model, kb).model
    model = ground_pricing(model, kb)

    # 2. Council reasons. Defaults to the deterministic stub ($0, no key); set
    #    COUNCIL_PROVIDER=claude (+ ANTHROPIC_API_KEY) to activate the real council.
    adrs = make_council().design(model)

    # 3. Deterministic simulation — the engine produces the numbers.
    sim = simulate(model)

    # 4. What-if interrogation (re-simulate variants of the same model).
    whatifs = [
        ("Cache cold / stampede (hit-rate 0%)",
         simulate(url_shortener.build(system_rps=10_000, cache_hit_rate=0.0))),
        ("10x traffic (100k rps)",
         simulate(url_shortener.build(system_rps=100_000, cache_hit_rate=0.90))),
    ]

    # 5. Report with the mandatory honesty section.
    return model, sim, whatifs, render(model, adrs, sim, whatifs)


def main() -> None:
    model, sim, whatifs, md = build_and_render()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(md)

    # Console summary
    print("=" * 70)
    print(f"KEYSTONE PHASE-0 — {model.name} @ {sim.system_rps:,.0f} rps")
    print("=" * 70)
    print(f"Bottleneck       : {sim.bottleneck_name} ({sim.bottleneck_utilization*100:.0f}% util)")
    print(f"Max safe load    : {sim.breakpoint_rps_safe:,.0f} rps "
          f"(theoretical {sim.breakpoint_rps_theoretical:,.0f})")
    print(f"Latency p50/p95/p99 : {sim.p50_ms:.0f} / {sim.p95_ms:.0f} / {sim.p99_ms:.0f} ms")
    print(f"SPOFs            : {', '.join(sim.spofs) or 'none'}")
    print(f"Compute cost     : ${sim.monthly_cost / 100:,.0f}/mo")  # cost is cents (ADR-008)
    print(f"Confidence       : {sim.confidence}")
    print("-" * 70)
    print("WHAT-IF:")
    for label, w in whatifs:
        print(f"  {label:38s} -> bottleneck {w.bottleneck_name:28s} "
              f"util {w.bottleneck_utilization*100:5.0f}%  safe {w.breakpoint_rps_safe:,.0f} rps")
    print("-" * 70)
    print(f"Full report written to: outputs/url_shortener_report.md")


if __name__ == "__main__":
    main()
