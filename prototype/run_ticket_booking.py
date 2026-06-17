"""Ticket Booking (case #2) — the flash-sale spike what-if (F6).

Shows how a flash sale (traffic surge + browsing collapsing into buying) shifts the
bottleneck from the app tier to the seat-inventory DB and collapses the safe breakpoint.
Deterministic engine; council stubbed by default ($0/offline).

Run from prototype/:  python3 run_ticket_booking.py  ->  outputs/ticket_booking_report.md
"""
from __future__ import annotations

import os

from keystone.blueprints import ticket_booking
from keystone.council import make_council
from keystone.report import render
from keystone.simulation import simulate

OUT = os.path.join(os.path.dirname(__file__), "outputs", "ticket_booking_report.md")


def main() -> None:
    baseline = ticket_booking.build()                 # steady state: 5k rps, 5% book
    sim = simulate(baseline)
    adrs = make_council().design(baseline)

    whatifs = [
        ("Flash sale: 8× traffic, browsing → buying (50% book)",
         simulate(ticket_booking.flash_sale(system_rps=40_000, book_share=0.5))),
        ("Mild on-sale: 2× traffic, 20% book",
         simulate(ticket_booking.build(system_rps=10_000, book_share=0.2))),
    ]

    md = render(baseline, adrs, sim, whatifs)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(md)

    print("=" * 74)
    print(f"KEYSTONE — Ticket Booking (case #2): flash-sale what-if")
    print("=" * 74)
    print(f"Baseline ({baseline.workload.description}) @ {sim.system_rps:,.0f} rps")
    print(f"  bottleneck : {sim.bottleneck_name} ({sim.bottleneck_utilization*100:.0f}% util)")
    print(f"  max safe   : {sim.breakpoint_rps_safe:,.0f} rps · compute ${sim.monthly_cost:,.0f}/mo")
    print("-" * 74)
    print("WHAT-IF (the retention feature — F6):")
    for label, w in whatifs:
        print(f"  {label}")
        print(f"     -> bottleneck {w.bottleneck_name} ({w.bottleneck_utilization*100:.0f}% util), "
              f"safe {w.breakpoint_rps_safe:,.0f} rps")
    print("-" * 74)
    print("Full report -> outputs/ticket_booking_report.md")


if __name__ == "__main__":
    main()
