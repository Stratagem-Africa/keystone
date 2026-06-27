"""Payments / Checkout platform as a Keystone canonical model — worked case #3.

Chosen to exercise two things the first two cases don't:
  1. HIGH-STAKES domain handling — money movement triggers the mandatory expert-review gate
     (Doc 03 §6); the report must never imply production/PCI safety.
  2. An EXTERNAL dependency as the binding constraint — a third-party payment gateway
     (Stripe / Adyen-class) is RATE-LIMITED (~100 req/s, server-enforced) and SLOW
     (~140 ms round-trip). Those two inputs match cited corpus evidence (external_api
     per_instance_rps + base_latency_ms), so they ground in-band and the gateway shows up
     as the throughput ceiling — the realistic, non-obvious finding: your checkout rate is
     capped by the gateway's rate limit, not your own infra.

Honesty note this case surfaces: the engine models the gateway as an M/M/1 queue (latency
rises smoothly toward saturation), but a rate limit is a HARD ceiling — requests are
REJECTED (HTTP 429) past the cap, not slowed. The grounded evidence note for the gateway's
rate limit says exactly this, so the Grounding section carries the caveat.

Single-region synchronous checkout stack -> in v1 scope. Capacities/costs are SEED
benchmarks (provenance=ASSUMPTION) to be field-calibrated; the gateway's rps/latency are
modeler values that the KB then grounds against cited evidence.
"""
from __future__ import annotations

from keystone.model import (
    Assumption, Component, ComponentKind, Flow, FlowStep, SystemModel, Workload,
)

BASELINE_RPS = 80
BASELINE_CHECKOUT_SHARE = 0.80   # checkout-heavy: 80% buy / 20% order-status reads


def build(system_rps: float = BASELINE_RPS, checkout_share: float = BASELINE_CHECKOUT_SHARE) -> SystemModel:
    """Build the checkout platform at a given load + buy/read mix. A sale = high `system_rps`
    (more checkouts hitting the rate-limited gateway)."""
    checkout = max(0.0, min(1.0, checkout_share))
    status = 1.0 - checkout

    components = {
        "lb": Component("lb", ComponentKind.LOAD_BALANCER, "API gateway / load balancer",
                        per_instance_rps=50_000, instances=1, base_latency_ms=1.0,
                        monthly_cost_per_instance=1800, provenance="ASSUMPTION"),
        "app": Component("app", ComponentKind.APP_SERVER, "Checkout service",
                         per_instance_rps=4_000, instances=2, base_latency_ms=5.0,
                         monthly_cost_per_instance=7000, provenance="ASSUMPTION"),
        # The constraint: a third-party payment gateway. ~100 req/s is a server-enforced RATE
        # LIMIT (HARD 429 ceiling), and ~140 ms is the external round-trip — both grounded.
        "gateway": Component("gateway", ComponentKind.EXTERNAL_API, "Payment gateway (Stripe/Adyen-class)",
                             per_instance_rps=100, instances=1, base_latency_ms=140.0,
                             monthly_cost_per_instance=0, provenance="ASSUMPTION"),
        "db": Component("db", ComponentKind.SQL_DB, "Payments ledger (ACID, idempotent writes)",
                        per_instance_rps=12_000, instances=1, base_latency_ms=0.3,
                        monthly_cost_per_instance=12000, provenance="ASSUMPTION"),
        "cache": Component("cache", ComponentKind.CACHE, "Idempotency / order cache",
                           per_instance_rps=110_000, instances=1, base_latency_ms=0.5,
                           monthly_cost_per_instance=15000, provenance="ASSUMPTION"),
    }

    flows = [
        # Checkout (write): LB -> checkout service -> payment gateway (charge) -> ledger (record).
        # Every checkout calls the gateway and writes the ledger exactly once. The contended path.
        Flow("checkout", share=checkout, path=[
            FlowStep("lb"), FlowStep("app"), FlowStep("gateway"), FlowStep("db"),
        ]),
        # Order status (read): LB -> checkout service -> idempotency/order cache -> (miss) ledger read.
        Flow("status", share=status, path=[
            FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.2),
        ]),
    ]

    label = "sale" if (system_rps * checkout) > BASELINE_RPS * BASELINE_CHECKOUT_SHARE else "steady state"
    assumptions = [
        Assumption("workload", f"{system_rps:,.0f} req/s, {checkout:.0%} checkout / {status:.0%} status ({label})",
                   confidence="med", source="llm_inferred"),
        Assumption("gateway", "Third-party payment gateway is the binding constraint: a server-enforced "
                              "~100 req/s RATE LIMIT (HARD 429 ceiling, NOT a graceful slowdown) and a "
                              "~140 ms external round-trip. Confirm YOUR vendor/tier — limits vary widely.",
                   confidence="med", source="benchmark"),
        Assumption("db", "Single ACID ledger; writes are idempotent (a charge is recorded exactly once "
                         "even on retry). Sized well above the gateway-capped write rate.",
                   confidence="low", source="benchmark"),
        Assumption("compliance", "Money movement: PCI-DSS scope, fraud, reconciliation and idempotency "
                                 "are REQUIRED and out of this model's scope — expert review is mandatory.",
                   confidence="high", source="llm_inferred"),
    ]

    return SystemModel(
        name="Payments / Checkout",
        components=components,
        flows=flows,
        workload=Workload(system_rps=system_rps,
                          description=f"{checkout:.0%} checkout / {status:.0%} status ({label})"),
        assumptions=assumptions,
        domain_flags=["high_stakes:payments"],   # money movement -> mandatory expert-review gate
    )


def sale(system_rps: float = 160, checkout_share: float = 0.85) -> SystemModel:
    """A sale spike: traffic surges and the checkout share rises, driving the rate-limited
    payment gateway past its ceiling (the headline what-if)."""
    return build(system_rps=system_rps, checkout_share=checkout_share)
