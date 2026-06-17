"""Hand-built reference SystemModels for in-scope SysSimulator blueprints (board #5).

The benchmark corpus (syssimulator_blueprints.py) is METADATA only — component count +
monthly cost band. To SCORE the engine we need a runnable SystemModel per blueprint;
only a handful exist so far. Each model here is built at a documented REFERENCE LOAD
chosen to represent a small/typical deployment (the scale the SysSimulator cost band
implies), and every capacity/cost is a SEED ASSUMPTION (provenance) — calibration to
real benchmarks is the L1 work (Doc 03). Building the rest of the 33 in-scope models is
a tracked GAP (and is partly what the ingestion layer will eventually automate).

Each registry entry: (blueprint_key, build_fn, reference_rps).
"""
from __future__ import annotations

from keystone.blueprints import ticket_booking, url_shortener
from keystone.model import (
    Assumption, Component, ComponentKind, Flow, FlowStep, SystemModel, Workload,
)


def _assume(subject: str, statement: str) -> Assumption:
    return Assumption(subject, statement, confidence="low", source="benchmark", provenance="ASSUMPTION")


def build_rate_limiter(system_rps: float = 5_000) -> SystemModel:
    """Rate limiter: edge gateway + Redis counter store. Small infra service."""
    return SystemModel(
        name="Rate Limiter",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "Edge gateway", per_instance_rps=15_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
            "redis": Component("redis", ComponentKind.CACHE, "Redis counters (r7g.medium)", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=90, provenance="ASSUMPTION"),
        },
        flows=[Flow("check", 1.0, [FlowStep("gw"), FlowStep("redis")])],
        workload=Workload(system_rps=system_rps, description="token-bucket check per request"),
        assumptions=[_assume("redis", "Single Redis counter store ~80k ops/s")],
    )


def build_kv_store(system_rps: float = 7_000) -> SystemModel:
    """Distributed KV store: LB + app tier + a replicated KV (modelled as cache+db)."""
    return SystemModel(
        name="Key-Value Store",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "KV API tier", per_instance_rps=3_000,
                             instances=3, base_latency_ms=2.0, monthly_cost_per_instance=40, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "In-memory shard", per_instance_rps=120_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=120, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Durable store", per_instance_rps=12_000,
                            instances=1, base_latency_ms=3.0, monthly_cost_per_instance=200, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("read", 0.9, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.2)]),
            Flow("write", 0.1, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="90/10 read:write, cache-aside"),
        assumptions=[_assume("kv", "Single durable shard ~12k rps; in-memory cache fronts reads")],
    )


def build_paste_bin(system_rps: float = 1_000) -> SystemModel:
    """Paste bin: LB + app + cache + object store + small DB for metadata. Low traffic."""
    return SystemModel(
        name="Paste Bin",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=30_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=20, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=1_500,
                             instances=1, base_latency_ms=8.0, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Read cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=15, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Metadata DB", per_instance_rps=4_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("read", 0.95, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.1)]),
            Flow("create", 0.05, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="read-heavy paste reads"),
        assumptions=[_assume("traffic", "Low-traffic paste service ~1k rps reference load")],
    )


def build_id_generator(system_rps: float = 20_000) -> SystemModel:
    """Unique ID generator: stateless app tier behind an LB (Snowflake-style). Cheap."""
    return SystemModel(
        name="Unique ID Generator",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "ID workers (Snowflake)", per_instance_rps=15_000,
                             instances=2, base_latency_ms=0.5, monthly_cost_per_instance=35, provenance="ASSUMPTION"),
        },
        flows=[Flow("generate", 1.0, [FlowStep("lb"), FlowStep("app")])],
        workload=Workload(system_rps=system_rps, description="stateless ID issuance"),
        assumptions=[_assume("id", "Stateless workers; no datastore on the hot path")],
    )


# (blueprint_key, build_fn, reference_rps). url_shortener uses its existing blueprint.
REFERENCE_MODELS = [
    ("url_shortener", lambda: url_shortener.build(system_rps=10_000), 10_000),
    ("ticket_booking", ticket_booking.build, 5_000),   # case #2; baseline (steady state)
    ("rate_limiter", build_rate_limiter, 5_000),
    ("kv_store", build_kv_store, 7_000),
    ("paste_bin", build_paste_bin, 1_000),
    ("id_generator", build_id_generator, 20_000),
]
