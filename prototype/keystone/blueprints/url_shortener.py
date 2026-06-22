"""URL Shortener as a Keystone canonical model — the Phase-0 build target.

Chosen because it is the most-documented system in existence (SysSimulator blueprint
+ learn guide; systemdesign.one Bitly write-up), so the engine's output can be
sanity-checked against ground truth. Single-region web stack -> fully in v1 scope.

In the real product this model is DERIVED by the LLM from a concept note. Here it is
hand-built so the deterministic loop can be validated independently of the LLM.

Capacities/costs are SEED benchmarks (provenance=ASSUMPTION) to be field-calibrated.
"""
from __future__ import annotations

from keystone.model import (
    SystemModel, Component, ComponentKind, Flow, FlowStep, Workload, Assumption,
)

CACHE_HIT_RATE = 0.90        # redirect read path; the load-bearing assumption


def build(system_rps: float = 10_000, cache_hit_rate: float = CACHE_HIT_RATE) -> SystemModel:
    miss = 1.0 - cache_hit_rate

    components = {
        "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Application Load Balancer",
                        per_instance_rps=30_000, instances=1, base_latency_ms=1.0,
                        monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
        "app": Component("app", ComponentKind.APP_SERVER, "App tier (t4g.medium x12)",
                         per_instance_rps=1_200, instances=12, base_latency_ms=8.0,
                         monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
        "cache": Component("cache", ComponentKind.CACHE, "Redis cache (r7g.large)",
                           per_instance_rps=100_000, instances=1, base_latency_ms=0.5,
                           monthly_cost_per_instance=18000, provenance="ASSUMPTION"),
        "db": Component("db", ComponentKind.SQL_DB, "PostgreSQL primary (r7g.large)",
                        per_instance_rps=8_000, instances=1, base_latency_ms=5.0,
                        monthly_cost_per_instance=42000, provenance="ASSUMPTION"),
    }

    flows = [
        # Redirect (read): LB -> app -> cache -> (cache miss) DB
        Flow("redirect", share=0.99, path=[
            FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=miss),
        ]),
        # Create (write): LB -> app -> DB
        Flow("create", share=0.01, path=[
            FlowStep("lb"), FlowStep("app"), FlowStep("db"),
        ]),
    ]

    assumptions = [
        Assumption("workload", f"{system_rps:,.0f} req/s peak, 99:1 read:write (redirects:creates)",
                   confidence="med", source="llm_inferred"),
        Assumption("cache", f"Cache hit-rate {cache_hit_rate*100:.0f}% on the redirect path",
                   confidence="med", source="llm_inferred"),
        Assumption("db", "Single PostgreSQL primary sized at ~8k rps",
                   confidence="low", source="benchmark"),
        Assumption("app", "App server ~1,200 rps/instance (lightweight redirect handler)",
                   confidence="low", source="benchmark"),
    ]

    return SystemModel(
        name="URL Shortener",
        components=components,
        flows=flows,
        workload=Workload(system_rps=system_rps, description="99:1 read:write, cache-aside"),
        assumptions=assumptions,
    )
