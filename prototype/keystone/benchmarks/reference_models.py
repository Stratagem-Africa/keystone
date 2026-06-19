"""Hand-built reference SystemModels for in-scope SysSimulator blueprints (board #5).

The benchmark corpus (syssimulator_blueprints.py) is METADATA only — component count +
monthly cost band. To SCORE the engine we need a runnable SystemModel per blueprint;
14 of the 34 in-scope blueprints are modelled so far. Each model here is built at a
documented REFERENCE LOAD chosen to represent a small/typical deployment (the scale the
SysSimulator cost band implies), and every capacity/cost is a SEED ASSUMPTION (provenance)
— calibration to real benchmarks is the L1 work (Doc 03). Building the remaining in-scope
models is a tracked GAP (and is partly what the ingestion layer will eventually automate).

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


def build_serverless_api(system_rps: float = 2_000) -> SystemModel:
    """Serverless REST API: API gateway → function tier → managed KV/cache. Cheap, bursty."""
    return SystemModel(
        name="Serverless REST API",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=20_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Function tier (Lambda)", per_instance_rps=1_500,
                             instances=2, base_latency_ms=12.0, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Edge/result cache", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=20, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Managed KV (DynamoDB)", per_instance_rps=8_000,
                            instances=1, base_latency_ms=5.0, monthly_cost_per_instance=60, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("read", 0.8, [FlowStep("gw"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.2)]),
            Flow("write", 0.2, [FlowStep("gw"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="80/20 read:write, cache-aside"),
        assumptions=[_assume("serverless", "Function concurrency ~1.5k rps/instance is the constraint, not the gateway")],
    )


def build_blog_platform(system_rps: float = 3_000) -> SystemModel:
    """Blog platform: CDN → LB → app → cache → DB, with an object store for media. Read-heavy."""
    return SystemModel(
        name="Blog Platform",
        components={
            "cdn": Component("cdn", ComponentKind.CDN, "CDN (static + media)", per_instance_rps=200_000,
                             instances=1, base_latency_ms=1.0, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Render tier", per_instance_rps=2_000,
                             instances=2, base_latency_ms=8.0, monthly_cost_per_instance=35, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Rendered-page cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Posts DB", per_instance_rps=5_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=90, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Media store", per_instance_rps=20_000,
                             instances=1, base_latency_ms=3.0, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("read_post", 0.85, [FlowStep("cdn"), FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.15)]),
            Flow("read_media", 0.10, [FlowStep("cdn"), FlowStep("obj")]),
            Flow("write_post", 0.05, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="read-heavy; CDN-fronted, cache-aside"),
        assumptions=[_assume("blog", "Render tier is the constraint; most reads served from CDN/cache")],
    )


def build_hotel_reservation(system_rps: float = 3_000) -> SystemModel:
    """Hotel reservation: search-heavy reads + transactional bookings to a payment external."""
    return SystemModel(
        name="Hotel Reservation System",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Reservation app", per_instance_rps=1_500,
                             instances=3, base_latency_ms=10.0, monthly_cost_per_instance=45, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Availability cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=60, provenance="ASSUMPTION"),
            "search": Component("search", ComponentKind.APP_SERVER, "Geo/availability search", per_instance_rps=3_000,
                                instances=1, base_latency_ms=8.0, monthly_cost_per_instance=50, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Reservations DB", per_instance_rps=4_000,
                            instances=1, base_latency_ms=6.0, monthly_cost_per_instance=200, provenance="ASSUMPTION"),
            "pay": Component("pay", ComponentKind.EXTERNAL_API, "Payment provider", per_instance_rps=5_000,
                             instances=1, base_latency_ms=30.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("search", 0.8, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("search", visit_prob=0.5)]),
            Flow("book", 0.2, [FlowStep("lb"), FlowStep("app"), FlowStep("db"), FlowStep("pay")]),
        ],
        workload=Workload(system_rps=system_rps, description="80/20 search:book; bookings are transactional"),
        assumptions=[_assume("hotel", "App tier sized to absorb search; booking writes hit the durable DB + external PSP")],
    )


def build_parking_lot(system_rps: float = 500) -> SystemModel:
    """Parking lot system: availability checks + entry/exit writes. Low traffic."""
    return SystemModel(
        name="Parking Lot System",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=30_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=20, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=1_000,
                             instances=1, base_latency_ms=8.0, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Availability cache", per_instance_rps=40_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=15, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Spots/tickets DB", per_instance_rps=3_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=40, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("availability", 0.7, [FlowStep("lb"), FlowStep("app"), FlowStep("cache")]),
            Flow("entry_exit", 0.3, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="70/30 availability:entry-exit; small-site load"),
        assumptions=[_assume("parking", "Single-site low traffic; app tier is the modest constraint")],
    )


def build_leaderboard(system_rps: float = 8_000) -> SystemModel:
    """Leaderboard: read-heavy rank queries against a Redis sorted set, durable scores in SQL."""
    return SystemModel(
        name="Leaderboard System",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Leaderboard API", per_instance_rps=4_000,
                             instances=3, base_latency_ms=2.0, monthly_cost_per_instance=35, provenance="ASSUMPTION"),
            "redis": Component("redis", ComponentKind.CACHE, "Redis sorted set", per_instance_rps=100_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=90, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Durable scores", per_instance_rps=6_000,
                            instances=1, base_latency_ms=3.0, monthly_cost_per_instance=80, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("get_rank", 0.9, [FlowStep("lb"), FlowStep("app"), FlowStep("redis")]),
            Flow("submit_score", 0.1, [FlowStep("lb"), FlowStep("app"), FlowStep("redis"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="90/10 read:write; ranks from the sorted set"),
        assumptions=[_assume("leaderboard", "Redis sorted set fronts all reads; SQL is the durable write path")],
    )


def build_typeahead(system_rps: float = 12_000) -> SystemModel:
    """Typeahead/autocomplete: every keystroke hits a suggestion (trie) cache. Very read-heavy."""
    return SystemModel(
        name="Typeahead / Autocomplete",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=60_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Suggest API", per_instance_rps=5_000,
                             instances=3, base_latency_ms=1.5, monthly_cost_per_instance=40, provenance="ASSUMPTION"),
            "trie": Component("trie", ComponentKind.CACHE, "Suggestion (trie) cache", per_instance_rps=150_000,
                              instances=1, base_latency_ms=0.3, monthly_cost_per_instance=200, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Term store", per_instance_rps=8_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=100, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("suggest", 0.97, [FlowStep("lb"), FlowStep("app"), FlowStep("trie"), FlowStep("db", visit_prob=0.05)]),
            Flow("log_select", 0.03, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="keystroke-rate suggests; ~95% trie hit"),
        assumptions=[_assume("typeahead", "In-memory trie cache absorbs near-all load; app tier is the constraint")],
    )


def build_task_queue(system_rps: float = 1_000) -> SystemModel:
    """Task queue: submit → broker → worker pool → state DB. Worker pool is the constraint."""
    return SystemModel(
        name="Task Queue",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "Submit gateway", per_instance_rps=20_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=25, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Message broker", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=80, provenance="ASSUMPTION"),
            "worker": Component("worker", ComponentKind.APP_SERVER, "Worker pool", per_instance_rps=400,
                                instances=3, base_latency_ms=20.0, monthly_cost_per_instance=40, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Job-state DB", per_instance_rps=5_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=90, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Result cache", per_instance_rps=40_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
        },
        flows=[Flow("job", 1.0, [FlowStep("gw"), FlowStep("queue"), FlowStep("worker"), FlowStep("db"), FlowStep("cache")])],
        workload=Workload(system_rps=system_rps, description="one job's lifecycle: enqueue → process → persist"),
        assumptions=[_assume("queue", "Per-job worker throughput ~400/s is the bottleneck; the broker decouples bursts")],
    )


def build_mcp_starter(system_rps: float = 400) -> SystemModel:
    """MCP starter: gateway → MCP server → tool backend, with session/context stores.
    Agent/tool calls are slow (low rps/instance, high latency)."""
    return SystemModel(
        name="MCP Starter",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=10_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=20, provenance="ASSUMPTION"),
            "mcp": Component("mcp", ComponentKind.APP_SERVER, "MCP server", per_instance_rps=300,
                             instances=2, base_latency_ms=40.0, monthly_cost_per_instance=35, provenance="ASSUMPTION"),
            "tool": Component("tool", ComponentKind.EXTERNAL_API, "Tool backend", per_instance_rps=2_000,
                              instances=1, base_latency_ms=50.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Context/result cache", per_instance_rps=30_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=30, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Session/memory store", per_instance_rps=4_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=60, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("query", 0.8, [FlowStep("gw"), FlowStep("mcp"), FlowStep("cache"), FlowStep("tool", visit_prob=0.6)]),
            Flow("store", 0.2, [FlowStep("gw"), FlowStep("mcp"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="80/20 tool-query:store; MCP server is the constraint"),
        assumptions=[_assume("mcp", "MCP server per-instance throughput (~300/s) bounds the system, not the gateway")],
    )


# (blueprint_key, build_fn, reference_rps). url_shortener uses its existing blueprint.
REFERENCE_MODELS = [
    ("url_shortener", lambda: url_shortener.build(system_rps=10_000), 10_000),
    ("ticket_booking", ticket_booking.build, 5_000),   # case #2; baseline (steady state)
    ("rate_limiter", build_rate_limiter, 5_000),
    ("kv_store", build_kv_store, 7_000),
    ("paste_bin", build_paste_bin, 1_000),
    ("id_generator", build_id_generator, 20_000),
    ("serverless_api", build_serverless_api, 2_000),
    ("blog_platform", build_blog_platform, 3_000),
    ("hotel_reservation", build_hotel_reservation, 3_000),
    ("parking_lot", build_parking_lot, 500),
    ("leaderboard", build_leaderboard, 8_000),
    ("typeahead", build_typeahead, 12_000),
    ("task_queue", build_task_queue, 1_000),
    ("mcp_starter", build_mcp_starter, 400),
]
