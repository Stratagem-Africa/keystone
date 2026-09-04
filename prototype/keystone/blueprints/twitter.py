"""A Twitter/X-scale microservice architecture as a Keystone canonical model — a DEPTH reference.

Point: show what "I want to build a platform like Twitter" should produce — a full, layered,
multi-service topology (edge → gateway → services → cache → data → async → external) with
real request journeys (post a tweet, load the home timeline, follow, search, upload media,
fan-out notifications), not a 4-box sketch. Hand-built here to define the TARGET depth; in the
product the LLM council DERIVES this from the intent. Capacities are seed benchmarks
(provenance=ASSUMPTION) — to be grounded/field-calibrated; the engine still owns every number.
"""
from __future__ import annotations

from keystone.model import (
    SystemModel, Component, ComponentKind, Flow, FlowStep, Workload, Assumption,
)

K = ComponentKind


def _c(cid, kind, name, rps, inst, lat, cost):
    return Component(cid, kind, name, per_instance_rps=rps, instances=inst,
                     base_latency_ms=lat, monthly_cost_per_instance=cost, provenance="ASSUMPTION")


def build(system_rps: float = 60_000) -> SystemModel:
    components = {c.id: c for c in [
        # edge
        _c("cdn",        K.CDN,           "CDN (media + static)",       120_000, 1, 20, 4_000),
        _c("lb",         K.LOAD_BALANCER, "Edge Load Balancer",          80_000, 2,  1, 2_500),
        # gateway
        _c("gw",         K.API_GATEWAY,   "API Gateway (auth + routing)", 12_000, 6,  5, 3_000),
        # services (compute)
        _c("web",        K.APP_SERVER,    "Web/Edge API",                 6_000, 20, 6, 3_500),
        _c("tweetsvc",   K.APP_SERVER,    "Tweet Service",                4_000, 12, 8, 3_500),
        _c("timelinesvc",K.APP_SERVER,    "Timeline Service (fan-out read)",5_000, 24, 7, 3_500),
        _c("usersvc",    K.APP_SERVER,    "User/Graph Service",           5_000, 8,  6, 3_500),
        _c("mediasvc",   K.APP_SERVER,    "Media Service",                3_000, 6,  9, 3_500),
        _c("searchsvc",  K.APP_SERVER,    "Search Service",               3_000, 8, 12, 3_500),
        _c("fanoutsvc",  K.APP_SERVER,    "Fan-out Service",              4_000, 10, 5, 3_500),
        _c("notifsvc",   K.APP_SERVER,    "Notification Service",         4_000, 6,  6, 3_500),
        # cache
        _c("tlcache",    K.CACHE,         "Timeline Cache (Redis)",      120_000, 6, 0.4, 18_000),
        _c("usercache",  K.CACHE,         "User/Session Cache (Redis)",  120_000, 3, 0.4, 18_000),
        # data
        _c("tweetsdb",   K.SQL_DB,        "Tweets DB (primary)",          9_000, 1,  5, 42_000),
        _c("tweetsrepl", K.REPLICA,       "Tweets DB Read Replicas",      9_000, 4,  5, 30_000),
        _c("usersdb",    K.SQL_DB,        "Users/Graph DB (primary)",     9_000, 1,  5, 42_000),
        _c("mediastore", K.OBJECT_STORE,  "Media Object Store (S3)",       6_000, 1, 30, 2_000),
        # async + external
        _c("fanoutq",    K.QUEUE,         "Fan-out Queue",               40_000, 3,  2, 4_000),
        _c("notifq",     K.QUEUE,         "Notification Queue",          40_000, 2,  2, 4_000),
        _c("pushapi",    K.EXTERNAL_API,  "Push/Email Provider (batched)",  6_000, 1,140, 0),
    ]}
    flows = [
        Flow("load home timeline", 0.55, [FlowStep("cdn"), FlowStep("lb"), FlowStep("gw"),
             FlowStep("web"), FlowStep("timelinesvc"), FlowStep("tlcache"),
             FlowStep("tweetsrepl", visit_prob=0.25)]),
        Flow("post a tweet", 0.15, [FlowStep("lb"), FlowStep("gw"), FlowStep("web"),
             FlowStep("tweetsvc"), FlowStep("tweetsdb"), FlowStep("fanoutq"), FlowStep("fanoutsvc")]),
        Flow("follow / graph", 0.10, [FlowStep("lb"), FlowStep("gw"), FlowStep("web"),
             FlowStep("usersvc"), FlowStep("usercache"), FlowStep("usersdb", visit_prob=0.4)]),
        Flow("search", 0.10, [FlowStep("lb"), FlowStep("gw"), FlowStep("web"),
             FlowStep("searchsvc"), FlowStep("tweetsrepl")]),
        Flow("upload media", 0.05, [FlowStep("cdn"), FlowStep("lb"), FlowStep("gw"),
             FlowStep("web"), FlowStep("mediasvc"), FlowStep("mediastore")]),
        Flow("fan-out notifications", 0.05, [FlowStep("fanoutq"), FlowStep("notifsvc"),
             FlowStep("notifq"), FlowStep("pushapi")]),
    ]
    assumptions = [
        Assumption("workload", f"{system_rps:,.0f} req/s peak; read-heavy (timeline reads dominate)",
                   confidence="med", source="llm_inferred"),
        Assumption("fan-out", "Write-time fan-out on post; timeline reads served from cache (~75% hit)",
                   confidence="low", source="llm_inferred"),
    ]
    return SystemModel(name="Twitter-scale platform", components=components, flows=flows,
                       workload=Workload(system_rps=system_rps, description="read-heavy social feed"),
                       assumptions=assumptions)
