"""Ticket Booking as a Keystone canonical model — benchmark case #2 (CLAUDE.md Phase-1).

An event-driven booking system whose defining stress is the FLASH SALE: normally browse
(read) traffic dominates, but when tickets drop, a spike of BOOKING (write) traffic hits
the seat-inventory datastore — the contended resource. The interesting what-if (F6) is
that spike: it shifts the bottleneck from the app tier to the inventory DB and collapses
the safe breakpoint.

Single-region event-driven stack -> in v1 scope. Matches the SysSimulator corpus entry
(`ticket_booking`, event_driven, 8 components, $300–1500/mo). Capacities/costs are SEED
benchmarks (provenance=ASSUMPTION) to be field-calibrated (Doc 03).

In the product this model is DERIVED by the LLM from a concept note; here it is hand-built
so the deterministic loop + the flash-sale what-if can be validated independently.
"""
from __future__ import annotations

from keystone.model import (
    Assumption, Component, ComponentKind, Flow, FlowStep, SystemModel, Workload,
)

BASELINE_RPS = 5_000
BASELINE_BOOK_SHARE = 0.05   # normally 95% browse / 5% book


def build(system_rps: float = BASELINE_RPS, book_share: float = BASELINE_BOOK_SHARE) -> SystemModel:
    """Build the model at a given load + booking mix. A flash sale = high `system_rps`
    AND a high `book_share` (browsing collapses into buying)."""
    book = max(0.0, min(1.0, book_share))
    browse = 1.0 - book

    components = {
        "cdn": Component("cdn", ComponentKind.CDN, "CDN (event pages)", per_instance_rps=80_000,
                         instances=1, base_latency_ms=2.0, monthly_cost_per_instance=50, provenance="ASSUMPTION"),
        "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                        instances=1, base_latency_ms=1.0, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
        "app": Component("app", ComponentKind.APP_SERVER, "Booking app tier", per_instance_rps=2_000,
                         instances=4, base_latency_ms=10.0, monthly_cost_per_instance=40, provenance="ASSUMPTION"),
        "cache": Component("cache", ComponentKind.CACHE, "Seat-availability cache", per_instance_rps=100_000,
                           instances=1, base_latency_ms=0.5, monthly_cost_per_instance=120, provenance="ASSUMPTION"),
        "queue": Component("queue", ComponentKind.QUEUE, "Booking request queue", per_instance_rps=20_000,
                           instances=1, base_latency_ms=2.0, monthly_cost_per_instance=90, provenance="ASSUMPTION"),
        "db": Component("db", ComponentKind.SQL_DB, "Inventory DB (seats)", per_instance_rps=3_000,
                        instances=1, base_latency_ms=6.0, monthly_cost_per_instance=300, provenance="ASSUMPTION"),
        "replica": Component("replica", ComponentKind.REPLICA, "Read replica", per_instance_rps=8_000,
                             instances=1, base_latency_ms=4.0, monthly_cost_per_instance=150, provenance="ASSUMPTION"),
        "payment": Component("payment", ComponentKind.EXTERNAL_API, "Payment gateway", per_instance_rps=5_000,
                             instances=1, base_latency_ms=120.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
    }

    flows = [
        # Browse (read): CDN -> LB -> app -> cache -> (cache miss) replica.
        Flow("browse", share=browse, path=[
            FlowStep("cdn"), FlowStep("lb"), FlowStep("app"), FlowStep("cache"),
            FlowStep("replica", visit_prob=0.1),
        ]),
        # Book (write): LB -> app -> queue -> inventory DB -> payment. The contended path.
        Flow("book", share=book, path=[
            FlowStep("lb"), FlowStep("app"), FlowStep("queue"), FlowStep("db"), FlowStep("payment"),
        ]),
    ]

    label = "flash sale" if book >= 0.3 else "steady state"
    assumptions = [
        Assumption("workload", f"{system_rps:,.0f} req/s, {browse:.0%} browse / {book:.0%} book ({label})",
                   confidence="med", source="llm_inferred"),
        Assumption("db", "Single inventory DB sized ~3k writes/s; seat decrements are the contended path",
                   confidence="low", source="benchmark"),
        Assumption("queue", "Booking writes serialized through a queue to prevent overselling",
                   confidence="med", source="llm_inferred"),
    ]

    return SystemModel(
        name="Ticket Booking",
        components=components,
        flows=flows,
        workload=Workload(system_rps=system_rps,
                          description=f"{browse:.0%} browse / {book:.0%} book ({label})"),
        assumptions=assumptions,
        domain_flags=[],  # not high-stakes by default (payments handled by the gateway)
    )


def flash_sale(system_rps: float = 40_000, book_share: float = 0.5) -> SystemModel:
    """The flash-sale spike scenario: traffic surges and browsing collapses into buying."""
    return build(system_rps=system_rps, book_share=book_share)
