"""Hand-built reference SystemModels for in-scope SysSimulator blueprints (board #5).

The benchmark corpus (syssimulator_blueprints.py) is METADATA only — component count +
monthly cost band. To SCORE the engine we need a runnable SystemModel per blueprint; **all
34 in-scope blueprints are now modelled** (full in-scope coverage). Each model is built at a
documented REFERENCE LOAD chosen to represent a small/typical deployment (the scale the
SysSimulator cost band implies), and every capacity/cost is a SEED ASSUMPTION (provenance)
— calibration to real benchmarks is the remaining L1 work (Doc 03), a tracked GAP (and is
partly what the ingestion layer will eventually automate). Out-of-scope blueprints await the
v2 discrete-event / multi-region engine.

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
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "redis": Component("redis", ComponentKind.CACHE, "Redis counters (r7g.medium)", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "KV API tier", per_instance_rps=3_000,
                             instances=3, base_latency_ms=2.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "In-memory shard", per_instance_rps=120_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=12000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Durable store", per_instance_rps=12_000,
                            instances=1, base_latency_ms=3.0, monthly_cost_per_instance=20000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=1_500,
                             instances=1, base_latency_ms=8.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Read cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=1500, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Metadata DB", per_instance_rps=4_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "ID workers (Snowflake)", per_instance_rps=15_000,
                             instances=2, base_latency_ms=0.5, monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Function tier (Lambda)", per_instance_rps=1_500,
                             instances=2, base_latency_ms=12.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Edge/result cache", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Managed KV (DynamoDB)", per_instance_rps=8_000,
                            instances=1, base_latency_ms=5.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
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
                             instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Render tier", per_instance_rps=2_000,
                             instances=2, base_latency_ms=8.0, monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Rendered-page cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Posts DB", per_instance_rps=5_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Media store", per_instance_rps=20_000,
                             instances=1, base_latency_ms=3.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Reservation app", per_instance_rps=1_500,
                             instances=3, base_latency_ms=10.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Availability cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "search": Component("search", ComponentKind.APP_SERVER, "Geo/availability search", per_instance_rps=3_000,
                                instances=1, base_latency_ms=8.0, monthly_cost_per_instance=5000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Reservations DB", per_instance_rps=4_000,
                            instances=1, base_latency_ms=6.0, monthly_cost_per_instance=20000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=1_000,
                             instances=1, base_latency_ms=8.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Availability cache", per_instance_rps=40_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=1500, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Spots/tickets DB", per_instance_rps=3_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Leaderboard API", per_instance_rps=4_000,
                             instances=3, base_latency_ms=2.0, monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
            "redis": Component("redis", ComponentKind.CACHE, "Redis sorted set", per_instance_rps=100_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Durable scores", per_instance_rps=6_000,
                            instances=1, base_latency_ms=3.0, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Suggest API", per_instance_rps=5_000,
                             instances=3, base_latency_ms=1.5, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "trie": Component("trie", ComponentKind.CACHE, "Suggestion (trie) cache", per_instance_rps=150_000,
                              instances=1, base_latency_ms=0.3, monthly_cost_per_instance=20000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Term store", per_instance_rps=8_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=10000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Message broker", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "worker": Component("worker", ComponentKind.APP_SERVER, "Worker pool", per_instance_rps=400,
                                instances=3, base_latency_ms=20.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Job-state DB", per_instance_rps=5_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Result cache", per_instance_rps=40_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
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
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "mcp": Component("mcp", ComponentKind.APP_SERVER, "MCP server", per_instance_rps=300,
                             instances=2, base_latency_ms=40.0, monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
            "tool": Component("tool", ComponentKind.EXTERNAL_API, "Tool backend", per_instance_rps=2_000,
                              instances=1, base_latency_ms=50.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Context/result cache", per_instance_rps=30_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Session/memory store", per_instance_rps=4_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("query", 0.8, [FlowStep("gw"), FlowStep("mcp"), FlowStep("cache"), FlowStep("tool", visit_prob=0.6)]),
            Flow("store", 0.2, [FlowStep("gw"), FlowStep("mcp"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="80/20 tool-query:store; MCP server is the constraint"),
        assumptions=[_assume("mcp", "MCP server per-instance throughput (~300/s) bounds the system, not the gateway")],
    )


def build_ecommerce(system_rps: float = 4_000) -> SystemModel:
    """E-commerce: browse (cache/search heavy) + cart + checkout to a payment external."""
    return SystemModel(
        name="E-Commerce Platform",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Storefront app", per_instance_rps=2_000,
                             instances=3, base_latency_ms=8.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Catalog cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Orders/catalog DB", per_instance_rps=5_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=12000, provenance="ASSUMPTION"),
            "search": Component("search", ComponentKind.APP_SERVER, "Product search", per_instance_rps=3_000,
                                instances=1, base_latency_ms=6.0, monthly_cost_per_instance=5000, provenance="ASSUMPTION"),
            "pay": Component("pay", ComponentKind.EXTERNAL_API, "Payment provider", per_instance_rps=5_000,
                             instances=1, base_latency_ms=30.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("browse", 0.7, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("search", visit_prob=0.4), FlowStep("db", visit_prob=0.2)]),
            Flow("cart", 0.2, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db")]),
            Flow("checkout", 0.1, [FlowStep("lb"), FlowStep("app"), FlowStep("db"), FlowStep("pay")]),
        ],
        workload=Workload(system_rps=system_rps, description="70/20/10 browse:cart:checkout"),
        assumptions=[_assume("ecommerce", "App tier sized to absorb browse; checkout writes hit DB + external PSP")],
    )


def build_file_hosting(system_rps: float = 3_000) -> SystemModel:
    """File hosting: CDN-fronted downloads + uploads to object storage, metadata in SQL."""
    return SystemModel(
        name="File Hosting Service",
        components={
            "cdn": Component("cdn", ComponentKind.CDN, "CDN", per_instance_rps=200_000,
                             instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=2_000,
                             instances=2, base_latency_ms=6.0, monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
            "meta": Component("meta", ComponentKind.SQL_DB, "Metadata DB", per_instance_rps=5_000,
                              instances=1, base_latency_ms=4.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Listing cache", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Object store", per_instance_rps=15_000,
                             instances=1, base_latency_ms=5.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("download", 0.7, [FlowStep("cdn"), FlowStep("lb"), FlowStep("app"), FlowStep("meta", visit_prob=0.3), FlowStep("obj")]),
            Flow("upload", 0.2, [FlowStep("lb"), FlowStep("app"), FlowStep("meta"), FlowStep("obj")]),
            Flow("list", 0.1, [FlowStep("lb"), FlowStep("app"), FlowStep("cache")]),
        ],
        workload=Workload(system_rps=system_rps, description="70/20/10 download:upload:list"),
        assumptions=[_assume("file_hosting", "App tier is the constraint; CDN fronts download bytes")],
    )


def build_image_hosting(system_rps: float = 4_000) -> SystemModel:
    """Image hosting: CDN-served views, async thumbnailing on upload, metadata in SQL."""
    return SystemModel(
        name="Image Hosting Service",
        components={
            "cdn": Component("cdn", ComponentKind.CDN, "CDN", per_instance_rps=200_000,
                             instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=3_000,
                             instances=2, base_latency_ms=4.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Hot-image cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=1500, provenance="ASSUMPTION"),
            "meta": Component("meta", ComponentKind.SQL_DB, "Metadata DB", per_instance_rps=6_000,
                              instances=1, base_latency_ms=3.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Image store", per_instance_rps=20_000,
                             instances=1, base_latency_ms=4.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "thumb": Component("thumb", ComponentKind.APP_SERVER, "Thumbnail worker", per_instance_rps=2_000,
                               instances=1, base_latency_ms=10.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("view", 0.8, [FlowStep("cdn"), FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("obj", visit_prob=0.3)]),
            Flow("upload", 0.15, [FlowStep("lb"), FlowStep("app"), FlowStep("obj"), FlowStep("thumb"), FlowStep("meta")]),
            Flow("meta", 0.05, [FlowStep("lb"), FlowStep("app"), FlowStep("meta")]),
        ],
        workload=Workload(system_rps=system_rps, description="view-heavy; upload triggers async thumbnailing"),
        assumptions=[_assume("image_hosting", "App tier is the constraint; CDN + cache serve most views")],
    )


def build_proximity_service(system_rps: float = 5_000) -> SystemModel:
    """Yelp / proximity: geo-search-heavy reads against a geo index + availability cache."""
    return SystemModel(
        name="Yelp / Proximity Service",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=40_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=2_500,
                             instances=3, base_latency_ms=6.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "geo": Component("geo", ComponentKind.APP_SERVER, "Geo index service", per_instance_rps=1_500,
                             instances=3, base_latency_ms=8.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Place cache", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Places DB", per_instance_rps=6_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=15000, provenance="ASSUMPTION"),
            "search": Component("search", ComponentKind.APP_SERVER, "Text search", per_instance_rps=3_000,
                                instances=1, base_latency_ms=7.0, monthly_cost_per_instance=5000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Photo store", per_instance_rps=20_000,
                             instances=1, base_latency_ms=3.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("search_nearby", 0.75, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("geo"), FlowStep("search", visit_prob=0.3), FlowStep("db", visit_prob=0.2)]),
            Flow("view_place", 0.20, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.3), FlowStep("obj", visit_prob=0.5)]),
            Flow("review", 0.05, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="search-heavy; geo index is a key tier"),
        assumptions=[_assume("proximity", "App + geo-index tiers carry search; cache fronts place reads")],
    )


def build_social_feed(system_rps: float = 10_000) -> SystemModel:
    """Social feed: read-heavy timeline from cache; posts fan out via a queue to workers."""
    return SystemModel(
        name="Social Media Feed",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Feed API", per_instance_rps=3_000,
                             instances=4, base_latency_ms=4.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Feed cache", per_instance_rps=100_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "fanout": Component("fanout", ComponentKind.APP_SERVER, "Fan-out workers", per_instance_rps=2_000,
                                instances=3, base_latency_ms=10.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Post queue", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Posts DB", per_instance_rps=8_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=15000, provenance="ASSUMPTION"),
            "graph": Component("graph", ComponentKind.SQL_DB, "Social graph", per_instance_rps=6_000,
                               instances=1, base_latency_ms=5.0, monthly_cost_per_instance=12000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Media store", per_instance_rps=30_000,
                             instances=1, base_latency_ms=3.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("read_feed", 0.8, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.2)]),
            Flow("post", 0.15, [FlowStep("lb"), FlowStep("app"), FlowStep("queue"), FlowStep("fanout"), FlowStep("graph"), FlowStep("obj", visit_prob=0.5)]),
            Flow("interact", 0.05, [FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="read-heavy timeline; writes fan out async"),
        assumptions=[_assume("social_feed", "App tier is the constraint; feed cache absorbs reads, fan-out is async")],
    )


def build_ci_cd(system_rps: float = 80) -> SystemModel:
    """CI/CD: jobs queued to a pool of build runners (slow, long jobs), artifacts to object store."""
    return SystemModel(
        name="CI/CD Pipeline",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=20_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Job queue", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=5000, provenance="ASSUMPTION"),
            "runner": Component("runner", ComponentKind.APP_SERVER, "Build runners", per_instance_rps=50,
                                instances=2, base_latency_ms=200.0, monthly_cost_per_instance=7500, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Build-state DB", per_instance_rps=5_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Artifact store", per_instance_rps=15_000,
                             instances=1, base_latency_ms=5.0, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
        },
        flows=[Flow("job", 1.0, [FlowStep("gw"), FlowStep("queue"), FlowStep("runner"), FlowStep("db"), FlowStep("obj")])],
        workload=Workload(system_rps=system_rps, description="build jobs; runner pool is the constraint"),
        assumptions=[_assume("ci_cd", "Per-runner throughput ~50 jobs/s bounds the system; the queue decouples bursts")],
    )


def build_notification_system(system_rps: float = 2_000) -> SystemModel:
    """Notifications: enqueue → dispatch workers → external push/email/sms channels."""
    return SystemModel(
        name="Notification System",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "Ingest gateway", per_instance_rps=30_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Dispatch queue", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "worker": Component("worker", ComponentKind.APP_SERVER, "Dispatch workers", per_instance_rps=1_000,
                                instances=3, base_latency_ms=15.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Delivery-state DB", per_instance_rps=6_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Template/prefs cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "push": Component("push", ComponentKind.EXTERNAL_API, "Push (APNs/FCM)", per_instance_rps=10_000,
                              instances=1, base_latency_ms=40.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "email": Component("email", ComponentKind.EXTERNAL_API, "Email (SES)", per_instance_rps=5_000,
                               instances=1, base_latency_ms=80.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "sms": Component("sms", ComponentKind.EXTERNAL_API, "SMS (Twilio)", per_instance_rps=3_000,
                             instances=1, base_latency_ms=100.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
        },
        flows=[Flow("send", 1.0, [FlowStep("gw"), FlowStep("queue"), FlowStep("worker"), FlowStep("cache"),
                                  FlowStep("db"), FlowStep("push", visit_prob=0.6), FlowStep("email", visit_prob=0.3), FlowStep("sms", visit_prob=0.1)])],
        workload=Workload(system_rps=system_rps, description="dispatch workers fan to push/email/sms"),
        assumptions=[_assume("notification", "Dispatch-worker throughput is the constraint; channels are external")],
    )


def build_microservices(system_rps: float = 16_000) -> SystemModel:
    """Microservices gateway: API gateway + LB routing to several services, shared cache/DB/queue."""
    return SystemModel(
        name="Microservices Gateway",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=30_000,
                            instances=2, base_latency_ms=1.0, monthly_cost_per_instance=5000, provenance="ASSUMPTION"),
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Internal LB", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "svc_a": Component("svc_a", ComponentKind.APP_SERVER, "Service A", per_instance_rps=3_000,
                               instances=3, base_latency_ms=5.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "svc_b": Component("svc_b", ComponentKind.APP_SERVER, "Service B", per_instance_rps=3_000,
                               instances=3, base_latency_ms=5.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "svc_c": Component("svc_c", ComponentKind.APP_SERVER, "Service C", per_instance_rps=2_000,
                               instances=2, base_latency_ms=8.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Shared cache", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Shared DB", per_instance_rps=8_000,
                            instances=2, base_latency_ms=4.0, monthly_cost_per_instance=15000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Event bus", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "registry": Component("registry", ComponentKind.APP_SERVER, "Service discovery", per_instance_rps=10_000,
                                  instances=1, base_latency_ms=2.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Blob store", per_instance_rps=20_000,
                             instances=1, base_latency_ms=3.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("req_a", 0.4, [FlowStep("gw"), FlowStep("lb"), FlowStep("svc_a"), FlowStep("cache"), FlowStep("db", visit_prob=0.3)]),
            Flow("req_b", 0.35, [FlowStep("gw"), FlowStep("lb"), FlowStep("svc_b"), FlowStep("cache"), FlowStep("db", visit_prob=0.3)]),
            Flow("req_c", 0.2, [FlowStep("gw"), FlowStep("lb"), FlowStep("svc_c"), FlowStep("queue"), FlowStep("obj", visit_prob=0.4)]),
            Flow("discover", 0.05, [FlowStep("gw"), FlowStep("registry")]),
        ],
        workload=Workload(system_rps=system_rps, description="gateway fans to services A/B/C over shared infra"),
        assumptions=[_assume("microservices", "Per-service app tiers are the constraints; gateway + LB have headroom")],
    )


def build_payment_system(system_rps: float = 5_000) -> SystemModel:
    """Payment system (HIGH-STAKES): fraud-scored payments to an ACID ledger + external PSP."""
    return SystemModel(
        name="Payment System",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "api": Component("api", ComponentKind.APP_SERVER, "Payments API", per_instance_rps=3_000,
                             instances=3, base_latency_ms=5.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "ledger": Component("ledger", ComponentKind.SQL_DB, "ACID ledger (replicated)", per_instance_rps=4_000,
                                instances=2, base_latency_ms=5.0, monthly_cost_per_instance=30000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Idempotency/status cache", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Settlement queue", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "fraud": Component("fraud", ComponentKind.APP_SERVER, "Fraud scoring", per_instance_rps=2_000,
                               instances=2, base_latency_ms=10.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "psp": Component("psp", ComponentKind.EXTERNAL_API, "Payment processor", per_instance_rps=5_000,
                             instances=1, base_latency_ms=50.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "audit": Component("audit", ComponentKind.OBJECT_STORE, "Audit log store", per_instance_rps=20_000,
                               instances=1, base_latency_ms=3.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("pay", 0.7, [FlowStep("lb"), FlowStep("api"), FlowStep("fraud"), FlowStep("ledger"), FlowStep("psp"), FlowStep("queue"), FlowStep("audit")]),
            Flow("status", 0.25, [FlowStep("lb"), FlowStep("api"), FlowStep("cache"), FlowStep("ledger", visit_prob=0.3)]),
            Flow("refund", 0.05, [FlowStep("lb"), FlowStep("api"), FlowStep("ledger"), FlowStep("psp"), FlowStep("audit")]),
        ],
        workload=Workload(system_rps=system_rps, description="fraud-scored payments; ledger is ACID + replicated"),
        assumptions=[_assume("payment", "Fraud-scoring tier is the constraint; ledger replicated for durability")],
        domain_flags=["high_stakes:payments"],
    )


def build_food_delivery(system_rps: float = 7_000) -> SystemModel:
    """Food delivery: browse/track (geo-heavy) + ordering to DB + external payment + notifications."""
    return SystemModel(
        name="Food Delivery System",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "App tier", per_instance_rps=3_000,
                             instances=3, base_latency_ms=6.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "geo": Component("geo", ComponentKind.APP_SERVER, "Geo matching", per_instance_rps=2_000,
                             instances=2, base_latency_ms=8.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Menu/availability cache", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Orders DB", per_instance_rps=6_000,
                            instances=2, base_latency_ms=4.0, monthly_cost_per_instance=15000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Order events", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "pay": Component("pay", ComponentKind.EXTERNAL_API, "Payment provider", per_instance_rps=5_000,
                             instances=1, base_latency_ms=50.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "notif": Component("notif", ComponentKind.APP_SERVER, "Notification service", per_instance_rps=5_000,
                               instances=1, base_latency_ms=5.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("browse", 0.5, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("geo", visit_prob=0.5), FlowStep("db", visit_prob=0.2)]),
            Flow("order", 0.3, [FlowStep("lb"), FlowStep("app"), FlowStep("db"), FlowStep("pay"), FlowStep("queue"), FlowStep("notif")]),
            Flow("track", 0.2, [FlowStep("lb"), FlowStep("app"), FlowStep("geo"), FlowStep("cache")]),
        ],
        workload=Workload(system_rps=system_rps, description="browse/track geo-heavy; orders write + pay"),
        assumptions=[_assume("food_delivery", "App + geo tiers carry browse/track; orders hit DB + external PSP")],
    )


def build_digital_wallet(system_rps: float = 7_000) -> SystemModel:
    """Digital wallet (HIGH-STAKES): balance reads + transfers, fraud-scored, ACID ledger, KYC/PSP."""
    return SystemModel(
        name="Digital Wallet",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "api": Component("api", ComponentKind.APP_SERVER, "Wallet API", per_instance_rps=3_000,
                             instances=3, base_latency_ms=5.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "ledger": Component("ledger", ComponentKind.SQL_DB, "Balance ledger (replicated)", per_instance_rps=4_000,
                                instances=2, base_latency_ms=5.0, monthly_cost_per_instance=30000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Balance cache", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Transfer events", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "fraud": Component("fraud", ComponentKind.APP_SERVER, "Fraud scoring", per_instance_rps=2_000,
                               instances=2, base_latency_ms=10.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "kyc": Component("kyc", ComponentKind.EXTERNAL_API, "KYC/identity", per_instance_rps=2_000,
                             instances=1, base_latency_ms=80.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "psp": Component("psp", ComponentKind.EXTERNAL_API, "Payment processor", per_instance_rps=5_000,
                             instances=1, base_latency_ms=50.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("transfer", 0.5, [FlowStep("lb"), FlowStep("api"), FlowStep("fraud"), FlowStep("ledger"), FlowStep("queue")]),
            Flow("balance", 0.4, [FlowStep("lb"), FlowStep("api"), FlowStep("cache"), FlowStep("ledger", visit_prob=0.2)]),
            Flow("topup", 0.1, [FlowStep("lb"), FlowStep("api"), FlowStep("ledger"), FlowStep("psp"), FlowStep("kyc", visit_prob=0.3)]),
        ],
        workload=Workload(system_rps=system_rps, description="balance-heavy reads; transfers fraud-scored to ACID ledger"),
        assumptions=[_assume("wallet", "Fraud-scoring tier is the constraint; ledger replicated for durability")],
        domain_flags=["high_stakes:payments"],
    )


def build_search_engine(system_rps: float = 6_000) -> SystemModel:
    """Search engine: query frontend → cache → index shards → doc store; async crawl/index path."""
    return SystemModel(
        name="Search Engine",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "Query frontend", per_instance_rps=3_000,
                             instances=3, base_latency_ms=5.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "index": Component("index", ComponentKind.APP_SERVER, "Index shards", per_instance_rps=2_000,
                               instances=4, base_latency_ms=8.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Query cache", per_instance_rps=100_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Doc store", per_instance_rps=6_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "crawler": Component("crawler", ComponentKind.APP_SERVER, "Crawl/index worker", per_instance_rps=500,
                                 instances=2, base_latency_ms=50.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Raw doc store", per_instance_rps=20_000,
                             instances=1, base_latency_ms=4.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("search", 0.9, [FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("index"), FlowStep("db", visit_prob=0.1)]),
            Flow("index_doc", 0.1, [FlowStep("crawler"), FlowStep("obj"), FlowStep("index"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="query-heavy; index shards are the hot tier"),
        assumptions=[_assume("search_engine", "Index shards bound query throughput; query cache fronts repeats")],
    )


def build_web_crawler(system_rps: float = 800) -> SystemModel:
    """Web crawler: scheduler → URL queue → fetch workers (slow/I-O) → parse → dedup/cache + stores."""
    return SystemModel(
        name="Web Crawler",
        components={
            "sched": Component("sched", ComponentKind.APP_SERVER, "Scheduler/frontier", per_instance_rps=5_000,
                               instances=1, base_latency_ms=3.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "URL queue", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "fetcher": Component("fetcher", ComponentKind.APP_SERVER, "Fetch workers", per_instance_rps=200,
                                 instances=5, base_latency_ms=100.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "parser": Component("parser", ComponentKind.APP_SERVER, "Parse workers", per_instance_rps=500,
                                instances=3, base_latency_ms=30.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Seen-URL dedup", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Crawl metadata", per_instance_rps=6_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Raw page store", per_instance_rps=15_000,
                             instances=1, base_latency_ms=5.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[Flow("crawl", 1.0, [FlowStep("sched"), FlowStep("queue"), FlowStep("fetcher"), FlowStep("parser"),
                                   FlowStep("cache"), FlowStep("db"), FlowStep("obj")])],
        workload=Workload(system_rps=system_rps, description="pages/s; fetch workers (I/O-bound) are the constraint"),
        assumptions=[_assume("web_crawler", "Per-fetcher throughput ~200/s bounds the crawl; queue decouples")],
    )


def build_metrics_monitoring(system_rps: float = 12_000) -> SystemModel:
    """Metrics & monitoring: high-rate ingest → buffer → TSDB writers → time-series DB; query path."""
    return SystemModel(
        name="Metrics & Monitoring",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "Ingest gateway", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Ingest buffer", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "writer": Component("writer", ComponentKind.APP_SERVER, "TSDB writers", per_instance_rps=5_000,
                                instances=3, base_latency_ms=3.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "tsdb": Component("tsdb", ComponentKind.SQL_DB, "Time-series DB", per_instance_rps=8_000,
                              instances=2, base_latency_ms=3.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Hot-window cache", per_instance_rps=100_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "query": Component("query", ComponentKind.APP_SERVER, "Query/dashboard API", per_instance_rps=3_000,
                               instances=1, base_latency_ms=5.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "obj": Component("obj", ComponentKind.OBJECT_STORE, "Cold rollups", per_instance_rps=30_000,
                             instances=1, base_latency_ms=3.0, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("ingest", 0.9, [FlowStep("gw"), FlowStep("queue"), FlowStep("writer"), FlowStep("tsdb")]),
            Flow("query", 0.1, [FlowStep("query"), FlowStep("cache"), FlowStep("tsdb", visit_prob=0.3), FlowStep("obj", visit_prob=0.2)]),
        ],
        workload=Workload(system_rps=system_rps, description="ingest-heavy metrics; writers are the hot tier"),
        assumptions=[_assume("metrics", "TSDB-writer throughput is the constraint; buffer absorbs ingest bursts")],
    )


def build_distributed_cache(system_rps: float = 60_000) -> SystemModel:
    """Distributed cache: LB → proxy/router → cache nodes, backing store on miss, coordinator."""
    return SystemModel(
        name="Distributed Cache",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=120_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "proxy": Component("proxy", ComponentKind.APP_SERVER, "Cache proxy/router", per_instance_rps=30_000,
                               instances=3, base_latency_ms=0.5, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "node": Component("node", ComponentKind.CACHE, "Cache nodes", per_instance_rps=100_000,
                              instances=3, base_latency_ms=0.2, monthly_cost_per_instance=12000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Backing store", per_instance_rps=8_000,
                            instances=1, base_latency_ms=3.0, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "coord": Component("coord", ComponentKind.APP_SERVER, "Coordinator/gossip", per_instance_rps=10_000,
                               instances=1, base_latency_ms=2.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("get", 0.85, [FlowStep("lb"), FlowStep("proxy"), FlowStep("node"), FlowStep("db", visit_prob=0.05)]),
            Flow("set", 0.15, [FlowStep("lb"), FlowStep("proxy"), FlowStep("node")]),
        ],
        workload=Workload(system_rps=system_rps, description="get-heavy; proxy/router tier is the constraint"),
        assumptions=[_assume("distributed_cache", "Proxy/router tier bounds throughput; cache nodes have headroom")],
    )


def build_api_gateway(system_rps: float = 30_000) -> SystemModel:
    """API rate-limiting gateway: LB → gateway → rate-limit store + auth → upstreams; async access log."""
    return SystemModel(
        name="API Rate Limiting Gateway",
        components={
            "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer", per_instance_rps=80_000,
                            instances=1, base_latency_ms=0.3, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "gw": Component("gw", ComponentKind.API_GATEWAY, "Gateway workers", per_instance_rps=20_000,
                            instances=3, base_latency_ms=1.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "ratelimit": Component("ratelimit", ComponentKind.CACHE, "Rate-limit store (Redis)", per_instance_rps=100_000,
                                   instances=1, base_latency_ms=0.3, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "auth": Component("auth", ComponentKind.APP_SERVER, "Auth/token validation", per_instance_rps=10_000,
                              instances=4, base_latency_ms=2.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Response cache", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "upstream": Component("upstream", ComponentKind.EXTERNAL_API, "Upstream services", per_instance_rps=50_000,
                                  instances=1, base_latency_ms=10.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "registry": Component("registry", ComponentKind.APP_SERVER, "Route config", per_instance_rps=10_000,
                                  instances=1, base_latency_ms=2.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "log": Component("log", ComponentKind.QUEUE, "Access-log buffer", per_instance_rps=100_000,
                             instances=1, base_latency_ms=0.2, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("proxy", 0.95, [FlowStep("lb"), FlowStep("gw"), FlowStep("ratelimit"), FlowStep("auth"), FlowStep("cache", visit_prob=0.4), FlowStep("upstream"), FlowStep("log")]),
            Flow("admin", 0.05, [FlowStep("lb"), FlowStep("gw"), FlowStep("registry")]),
        ],
        workload=Workload(system_rps=system_rps, description="proxy traffic with rate-limit + auth checks"),
        assumptions=[_assume("api_gateway", "Gateway + auth tiers are the constraints; rate-limit store has headroom")],
    )


def build_mcp_rag_assistant(system_rps: float = 600) -> SystemModel:
    """RAG + MCP assistant: orchestrator → vector store + cache → LLM; doc ingest path."""
    return SystemModel(
        name="RAG + MCP Assistant",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=10_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2000, provenance="ASSUMPTION"),
            "app": Component("app", ComponentKind.APP_SERVER, "RAG orchestrator", per_instance_rps=400,
                             instances=2, base_latency_ms=40.0, monthly_cost_per_instance=3500, provenance="ASSUMPTION"),
            "vector": Component("vector", ComponentKind.SQL_DB, "Vector store (pgvector)", per_instance_rps=5_000,
                                instances=1, base_latency_ms=8.0, monthly_cost_per_instance=12000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Embedding/result cache", per_instance_rps=30_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "llm": Component("llm", ComponentKind.EXTERNAL_API, "LLM API", per_instance_rps=1_000,
                             instances=1, base_latency_ms=60.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "Docs/sessions", per_instance_rps=4_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("ask", 0.85, [FlowStep("gw"), FlowStep("app"), FlowStep("cache"), FlowStep("vector"), FlowStep("llm")]),
            Flow("ingest_doc", 0.15, [FlowStep("gw"), FlowStep("app"), FlowStep("vector"), FlowStep("db")]),
        ],
        workload=Workload(system_rps=system_rps, description="RAG queries; orchestrator (LLM-bound) is the constraint"),
        assumptions=[_assume("mcp_rag", "Orchestrator per-instance throughput bounds the system, not retrieval")],
    )


def build_multi_agent_supervisor(system_rps: float = 600) -> SystemModel:
    """Multi-agent supervisor: orchestrator → queue → agent workers → LLM, with state/cache."""
    return SystemModel(
        name="Multi-Agent Supervisor",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=10_000,
                            instances=1, base_latency_ms=1.0, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "supervisor": Component("supervisor", ComponentKind.APP_SERVER, "Orchestrator", per_instance_rps=300,
                                    instances=3, base_latency_ms=50.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "worker": Component("worker", ComponentKind.APP_SERVER, "Agent workers", per_instance_rps=200,
                                instances=4, base_latency_ms=80.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Task queue", per_instance_rps=50_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Context cache", per_instance_rps=30_000,
                               instances=1, base_latency_ms=0.5, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "db": Component("db", ComponentKind.SQL_DB, "State/memory store", per_instance_rps=4_000,
                            instances=1, base_latency_ms=4.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "llm": Component("llm", ComponentKind.EXTERNAL_API, "LLM API (pool)", per_instance_rps=1_000,
                             instances=2, base_latency_ms=60.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
        },
        flows=[Flow("task", 1.0, [FlowStep("gw"), FlowStep("supervisor"), FlowStep("queue"), FlowStep("worker"),
                                  FlowStep("llm"), FlowStep("db"), FlowStep("cache")])],
        workload=Workload(system_rps=system_rps, description="agent tasks; worker pool (LLM-bound) is the constraint"),
        assumptions=[_assume("multi_agent", "Agent-worker throughput bounds the system; LLM pool fronts calls")],
    )


def build_mcp_tool_gateway(system_rps: float = 8_000) -> SystemModel:
    """MCP tool gateway: auth + rate-limit → tool router → external tools, with registry."""
    return SystemModel(
        name="MCP Tool Gateway",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "API gateway", per_instance_rps=20_000,
                            instances=2, base_latency_ms=1.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "router": Component("router", ComponentKind.APP_SERVER, "Tool router", per_instance_rps=2_000,
                                instances=5, base_latency_ms=8.0, monthly_cost_per_instance=4500, provenance="ASSUMPTION"),
            "ratelimit": Component("ratelimit", ComponentKind.CACHE, "Rate-limit store", per_instance_rps=100_000,
                                   instances=1, base_latency_ms=0.3, monthly_cost_per_instance=9000, provenance="ASSUMPTION"),
            "auth": Component("auth", ComponentKind.APP_SERVER, "Auth", per_instance_rps=10_000,
                              instances=2, base_latency_ms=2.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Result cache", per_instance_rps=60_000,
                               instances=1, base_latency_ms=0.4, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "tool": Component("tool", ComponentKind.EXTERNAL_API, "Downstream tools", per_instance_rps=12_000,
                              instances=1, base_latency_ms=40.0, monthly_cost_per_instance=0, provenance="ASSUMPTION"),
            "registry": Component("registry", ComponentKind.SQL_DB, "Tool registry", per_instance_rps=6_000,
                                  instances=1, base_latency_ms=3.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("invoke", 0.9, [FlowStep("gw"), FlowStep("auth"), FlowStep("router"), FlowStep("ratelimit"), FlowStep("cache", visit_prob=0.3), FlowStep("tool")]),
            Flow("register", 0.1, [FlowStep("gw"), FlowStep("auth"), FlowStep("registry")]),
        ],
        workload=Workload(system_rps=system_rps, description="tool invocations with auth + rate limiting"),
        assumptions=[_assume("mcp_tool_gateway", "Tool-router tier is the constraint; auth + rate-limit have headroom")],
    )


def build_agent_observability(system_rps: float = 10_000) -> SystemModel:
    """Agent observability: high-rate trace ingest → buffer → writers → trace store; query path."""
    return SystemModel(
        name="Agent Observability Stack",
        components={
            "gw": Component("gw", ComponentKind.API_GATEWAY, "Trace ingest gateway", per_instance_rps=50_000,
                            instances=1, base_latency_ms=0.5, monthly_cost_per_instance=2500, provenance="ASSUMPTION"),
            "queue": Component("queue", ComponentKind.QUEUE, "Ingest buffer", per_instance_rps=80_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=8000, provenance="ASSUMPTION"),
            "writer": Component("writer", ComponentKind.APP_SERVER, "Span/trace writers", per_instance_rps=4_000,
                                instances=3, base_latency_ms=3.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
            "tsdb": Component("tsdb", ComponentKind.SQL_DB, "Trace store", per_instance_rps=8_000,
                              instances=2, base_latency_ms=3.0, monthly_cost_per_instance=6000, provenance="ASSUMPTION"),
            "cache": Component("cache", ComponentKind.CACHE, "Recent-trace cache", per_instance_rps=100_000,
                               instances=1, base_latency_ms=0.3, monthly_cost_per_instance=3000, provenance="ASSUMPTION"),
            "query": Component("query", ComponentKind.APP_SERVER, "Query/dashboard", per_instance_rps=3_000,
                               instances=1, base_latency_ms=5.0, monthly_cost_per_instance=4000, provenance="ASSUMPTION"),
        },
        flows=[
            Flow("ingest", 0.9, [FlowStep("gw"), FlowStep("queue"), FlowStep("writer"), FlowStep("tsdb")]),
            Flow("query", 0.1, [FlowStep("query"), FlowStep("cache"), FlowStep("tsdb", visit_prob=0.3)]),
        ],
        workload=Workload(system_rps=system_rps, description="trace-ingest-heavy; writers are the hot tier"),
        assumptions=[_assume("agent_observability", "Span-writer throughput is the constraint; buffer absorbs bursts")],
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
    # --- batch 3: completes the in-scope corpus (→ 34/34) ---
    ("ecommerce", build_ecommerce, 4_000),
    ("file_hosting", build_file_hosting, 3_000),
    ("image_hosting", build_image_hosting, 4_000),
    ("proximity_service", build_proximity_service, 5_000),
    ("social_feed", build_social_feed, 10_000),
    ("ci_cd", build_ci_cd, 80),
    ("notification_system", build_notification_system, 2_000),
    ("microservices", build_microservices, 16_000),
    ("payment_system", build_payment_system, 5_000),
    ("food_delivery", build_food_delivery, 7_000),
    ("digital_wallet", build_digital_wallet, 7_000),
    ("search_engine", build_search_engine, 6_000),
    ("web_crawler", build_web_crawler, 800),
    ("metrics_monitoring", build_metrics_monitoring, 12_000),
    ("distributed_cache", build_distributed_cache, 60_000),
    ("api_gateway", build_api_gateway, 30_000),
    ("mcp_rag_assistant", build_mcp_rag_assistant, 600),
    ("multi_agent_supervisor", build_multi_agent_supervisor, 600),
    ("mcp_tool_gateway", build_mcp_tool_gateway, 8_000),
    ("agent_observability", build_agent_observability, 10_000),
]
