"""Keystone canonical system model (Doc 05).

The single source of truth. Every front door (docs/voice/text/diagram) normalises
into this; every output (simulation/report/export) derives from it. Pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from keystone.provenance import Grounding  # evidence types (pure stdlib; no cycle)


class ComponentKind(str, Enum):
    CLIENT = "client"
    CDN = "cdn"
    LOAD_BALANCER = "load_balancer"
    API_GATEWAY = "api_gateway"
    APP_SERVER = "app_server"
    CACHE = "cache"
    SQL_DB = "sql_db"
    REPLICA = "replica"
    QUEUE = "queue"
    OBJECT_STORE = "object_store"
    EXTERNAL_API = "external_api"


# Component kinds that are a single point of failure when run as one instance.
_SPOF_KINDS = {
    ComponentKind.SQL_DB,
    ComponentKind.CACHE,
    ComponentKind.LOAD_BALANCER,
    ComponentKind.API_GATEWAY,
    ComponentKind.QUEUE,
}


@dataclass
class Component:
    id: str
    kind: ComponentKind
    name: str
    per_instance_rps: float           # service capacity per instance (req/s)
    instances: int = 1
    base_latency_ms: float = 1.0      # service time with no contention
    monthly_cost_per_instance: int = 0  # integer MINOR UNITS (USD cents/month) — harm floor: no float money (ADR-008)
    # Usage-based cost inputs (ADR-009 Tier 1). Declarative monthly volumes the engine multiplies by
    # the model's `PricingRates`. Default 0 → no usage cost, so existing models are byte-for-byte
    # unchanged. Non-negative ints (they drive money — harm floor). ASSUMPTION until grounded.
    egress_gb_per_month: int = 0      # GB egressed (internet / cross-region) per month
    storage_gb: int = 0               # GB stored (object/block/DB storage)
    requests_per_month: int = 0       # billable requests/month (API gateway, serverless, queue ops)
    provenance: str = "assumption"    # component default: GROUNDED | GAP | ASSUMPTION
    # Per-metric grounding evidence (ADR-006/docs/12). A capacity becomes GROUNDED only when the
    # KB attaches a `Grounding` (value + band + citations) under that metric name; otherwise the
    # metric keeps the component `provenance` default. Empty = nothing grounded (the honest L0 state).
    # Set at construction (immutable evidence); the engine NEVER reads it (prime directive — grounding
    # changes the input number, never the math). `scaled()` shares components, which is correct: a
    # what-if keeps the same capacities, so the same groundings apply.
    groundings: dict[str, Grounding] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Harm floor (ADR-008): money is integer minor units (cents) — never a float (rounding
        # corrupts money). `bool` is an int subclass, so exclude it explicitly.
        c = self.monthly_cost_per_instance
        if isinstance(c, bool) or not isinstance(c, int):
            raise TypeError(
                f"monthly_cost_per_instance must be an int in minor units (cents), not {type(c).__name__} "
                f"({c!r}) — float money is forbidden by the harm floor")
        if c < 0:
            raise ValueError(f"monthly_cost_per_instance must be non-negative, got {c}")
        # Usage volumes drive money, so hold them to the same harm-floor discipline: non-negative ints.
        for name in ("egress_gb_per_month", "storage_gb", "requests_per_month"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(f"{name} must be a non-negative int, not {type(v).__name__} ({v!r})")
            if v < 0:
                raise ValueError(f"{name} must be non-negative, got {v}")

    def provenance_of(self, metric: str) -> str:
        """GROUNDED if this metric carries grounding evidence, else the component default."""
        g = self.groundings.get(metric)
        return g.provenance if g else self.provenance

    @property
    def capacity_rps(self) -> float:
        return self.per_instance_rps * self.instances

    @property
    def monthly_cost(self) -> float:
        return self.monthly_cost_per_instance * self.instances

    @property
    def is_spof(self) -> bool:
        return self.instances <= 1 and self.kind in _SPOF_KINDS


@dataclass
class FlowStep:
    component_id: str
    visit_prob: float = 1.0           # P(component is hit on this flow), e.g. cache-miss


@dataclass
class Flow:
    name: str
    share: float                      # fraction of total requests (Sum of shares == 1.0)
    path: list[FlowStep]


@dataclass
class Workload:
    system_rps: float
    description: str = ""


@dataclass
class Assumption:
    subject: str
    statement: str
    confidence: str = "med"           # low | med | high
    source: str = "assumption"        # llm_inferred | benchmark | user
    provenance: str = "ASSUMPTION"    # GROUNDED | GAP | ASSUMPTION


@dataclass
class PricingRates:
    """Per-unit cloud rates for usage-based cost (ADR-009 Tier 1). Stored as integer **micro-USD**
    per unit (1 USD = 1_000_000 micro-USD; 1 cent = 10_000 micro-USD) so sub-cent rates are exact;
    the engine rounds the usage TOTAL to integer cents (harm floor, ADR-008 — money is never a float).
    Defaults are real-ballpark AWS-class **ASSUMPTION** seeds; grounding them with citations (like the
    per-instance costs) is a tracked follow-up."""
    egress_micro_usd_per_gb: int = 90_000          # ~$0.09/GB internet egress (AWS-class) — ASSUMPTION
    storage_micro_usd_per_gb_month: int = 23_000   # ~$0.023/GB-month (S3 Standard-class) — ASSUMPTION
    request_micro_usd_per_thousand: int = 1_000    # ~$1.00 per million requests — ASSUMPTION

    def __post_init__(self) -> None:
        for name in ("egress_micro_usd_per_gb", "storage_micro_usd_per_gb_month", "request_micro_usd_per_thousand"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError(f"{name} must be a non-negative int (micro-USD), got {v!r}")


@dataclass
class SystemModel:
    name: str
    components: dict[str, Component]
    flows: list[Flow]
    workload: Workload
    assumptions: list[Assumption] = field(default_factory=list)
    domain_flags: list[str] = field(default_factory=list)  # e.g. "high_stakes:elections"
    pricing: PricingRates = field(default_factory=PricingRates)  # usage rates (ADR-009 Tier 1)

    def scaled(self, system_rps: float) -> "SystemModel":
        """Return a copy with a different offered load (for what-if runs)."""
        return SystemModel(
            name=self.name,
            components=self.components,
            flows=self.flows,
            workload=Workload(system_rps=system_rps, description=f"what-if @ {system_rps:.0f} rps"),
            assumptions=self.assumptions,
            domain_flags=self.domain_flags,
            pricing=self.pricing,
        )
