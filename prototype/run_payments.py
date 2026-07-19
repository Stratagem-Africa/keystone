"""Payments / Checkout (worked case #3) — high-stakes domain + a rate-limited external dependency.

Shows (a) the mandatory expert-review gate firing for a money-movement domain, and (b) the
third-party payment gateway's RATE LIMIT (a hard ceiling) surfacing as the throughput
constraint — the realistic, non-obvious finding. The what-if drives a sale spike past the
gateway's ceiling. Deterministic engine; council stubbed by default ($0/offline).

Run from prototype/:  python3 run_payments.py  ->  outputs/payments_report.md
"""
from __future__ import annotations

import os

from _env import load_env, report_path
from keystone.blueprints import payments
from keystone.confidence_bands import simulate_with_confidence
from keystone.cost_meter import CostMeter
from keystone.council import make_council
from keystone.grounding import ground_model
from keystone.report import render
from keystone.simulation import simulate

OUT = os.path.join(os.path.dirname(__file__), "outputs", "payments_report.md")


def main() -> None:
    load_env()                              # activate local .env (council/grounding); existing env wins
    baseline = ground_model(payments.build())          # 80 req/s, 80% checkout (grounding activated)
    sim = simulate_with_confidence(baseline)           # output ranges from cited input uncertainty (values unchanged)
    meter = CostMeter()                     # OUR council API spend for this run (empty on the stub path)
    council = make_council(meter=meter)
    adrs = council.design(baseline)

    whatifs = [
        ("Sale: 2× traffic (160 rps), 85% checkout",
         simulate(payments.sale(system_rps=160, checkout_share=0.85))),
        ("Black-Friday: 4× traffic (320 rps), 90% checkout",
         simulate(payments.sale(system_rps=320, checkout_share=0.90))),
    ]

    md = render(baseline, adrs, sim, whatifs,
                context_trimmed=getattr(council, "context_trimmed", False))
    out, provider = report_path(OUT)        # LIVE council -> gitignored *.local.md (never clobber the golden)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(md)

    print("=" * 74)
    print("KEYSTONE — Payments / Checkout (case #3): high-stakes + rate-limited gateway")
    print("=" * 74)
    print(f"Council    : {provider}"
          + ("  (deterministic stub)" if provider == "stub" else "  (LIVE LLM — non-deterministic)"))
    print(f"Council API spend: {meter.summary()}")   # OUR inference spend (council only) — NOT the user's system cost
    print(f"Baseline ({baseline.workload.description}) @ {sim.system_rps:,.0f} rps")
    print(f"  bottleneck : {sim.bottleneck_name} ({sim.bottleneck_utilization*100:.0f}% util)")
    print(f"  max safe   : {sim.breakpoint_rps_safe:,.0f} rps · compute ${sim.monthly_cost / 100:,.0f}/mo")  # cents (ADR-008)
    print(f"  high-stakes: {', '.join(baseline.domain_flags) or 'none'} (expert-review gate)")
    print("-" * 74)
    print("WHAT-IF (the sale spike past the gateway's rate-limit ceiling):")
    for label, w in whatifs:
        print(f"  {label}")
        print(f"     -> bottleneck {w.bottleneck_name} ({w.bottleneck_utilization*100:.0f}% util), "
              f"safe {w.breakpoint_rps_safe:,.0f} rps")
    print("-" * 74)
    print(f"Full report -> outputs/{os.path.basename(out)}")


if __name__ == "__main__":
    main()
