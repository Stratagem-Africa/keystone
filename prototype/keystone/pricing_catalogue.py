"""Grounded COMPUTE prices — what an instance of a given class actually costs per month.

`grounded_pricing_rates.json` already grounds Keystone's USAGE rates (egress, storage, requests).
Compute was the hole: every blueprint hardcoded `monthly_cost_per_instance` tagged ASSUMPTION with no
citation, and compute is the DOMINANT line — so the "$X / month" a user reads was the least grounded
number in the product. This module closes that with cited, adversarially-verified prices.

Two operations, deliberately kept apart because they are different promises:

* `price_for(kind, instance_class)` — a LOOKUP. Used to CHOOSE an input where none was given (the
  LLM design path sets cost to 0 on purpose, because the council must never author a number). Keystone
  picking a documented default and citing it is a different act from a model inventing one.
* `grounding_for(...)` — EVIDENCE. Mirrors `grounding.ground_pricing`: it attaches a citation to a
  value that already matches the catalogue, and never changes a number. Fails closed — a component
  priced differently is left ungrounded rather than shown as cited.

**What this file refuses to price**, and why that matters more than what it prices: an API gateway,
an object store, a CDN and a load balancer have NO per-instance price. `model.py` computes
`monthly_cost_per_instance * instances`, so putting an ALB's hourly floor there would multiply a
per-load-balancer charge by the instance count, and CloudFront's flat plan is priced per
DISTRIBUTION. Those kinds stay ungrounded on purpose; `KINDS_WITHOUT_PER_INSTANCE_PRICE` says so,
with the reason, so a caller can explain the gap instead of filling it with a plausible number.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from functools import lru_cache

from .grounding import Citation, Grounding
from .model import ComponentKind

__all__ = [
    "PricedInstance", "KINDS_WITHOUT_PER_INSTANCE_PRICE", "DEFAULT_CLASS",
    "catalogue", "price_for", "default_price_for_kind", "grounding_for",
]

_PATH = pathlib.Path(__file__).with_name("benchmarks") / "compute_prices.json"


@dataclass(frozen=True)
class PricedInstance:
    key: str
    component_kind: str
    instance_class: str
    monthly_cents: int
    low_cents: int
    high_cents: int
    band_basis: str
    citation_url: str
    scope: str
    note: str
    vcpu: float
    memory_gib: float


@lru_cache(maxsize=1)
def _doc() -> dict:
    return json.loads(_PATH.read_text(encoding="utf8"))


@lru_cache(maxsize=1)
def catalogue() -> dict[str, PricedInstance]:
    """Every priced instance class, keyed by `<kind>.<class>`."""
    return {
        r["key"]: PricedInstance(
            key=r["key"], component_kind=r["component_kind"], instance_class=r["instance_class"],
            monthly_cents=int(r["monthly_cents"]), low_cents=int(r["low_cents"]),
            high_cents=int(r["high_cents"]), band_basis=r["band_basis"],
            citation_url=r["citation_url"], scope=r["scope"], note=r["note"],
            vcpu=float(r.get("vcpu") or 0), memory_gib=float(r.get("memory_gib") or 0),
        )
        for r in _doc()["rows"]
    }


@lru_cache(maxsize=1)
def _no_price() -> dict[str, str]:
    return dict(_doc()["no_per_instance_price"])


KINDS_WITHOUT_PER_INSTANCE_PRICE: dict[str, str] = _no_price()

# The class Keystone picks when a design does not name one. A modest, general-purpose default per
# kind — chosen so an unspecified design is priced conservatively rather than flatteringly, and
# always disclosed as a Keystone choice rather than a measurement of the user's stack.
DEFAULT_CLASS: dict[str, str] = {
    "app_server": "m6i.large",
    "sql_db": "db.m6i.large",
    "replica": "db.m6i.large",
    "cache": "cache.r6g.large",
    "queue": "kafka.m5.large",
}


def price_for(kind: str | ComponentKind, instance_class: str) -> PricedInstance | None:
    """The catalogue row for this kind + class, or None if it is not priced."""
    k = kind.value if isinstance(kind, ComponentKind) else str(kind)
    return catalogue().get(f"{k}.{instance_class}")


def default_price_for_kind(kind: str | ComponentKind) -> PricedInstance | None:
    """The row Keystone uses when a design names no instance class.

    Returns None for the kinds that genuinely have no per-instance price — the caller must then
    explain the gap (see `KINDS_WITHOUT_PER_INSTANCE_PRICE`) rather than substitute a number.
    """
    k = kind.value if isinstance(kind, ComponentKind) else str(kind)
    cls = DEFAULT_CLASS.get(k)
    return price_for(k, cls) if cls else None


def grounding_for(priced: PricedInstance) -> Grounding:
    """Evidence for a cost that already equals `priced.monthly_cents`.

    The band is whatever the row's `band_basis` says it is — a real deployment spread for RDS, and
    zero-width for the classes whose list rate has no variance in scope. A zero-width band is an
    honest statement that the price is exact within the stated scope, not a missing band; the things
    that DO move the bill (month length, burst credits, Savings Plans, Multi-AZ) are named in the
    note instead of being blurred into a range.
    """
    return Grounding(
        value=float(priced.monthly_cents),
        unit="usd_minor_per_month",
        confidence_low=float(priced.low_cents),
        confidence_high=float(priced.high_cents),
        citations=(Citation(source="AWS first-party pricing", reference=priced.citation_url,
                            note=priced.note),),
        provenance="GROUNDED",
        measured_context=f"{priced.instance_class} — {priced.scope}. Band: {priced.band_basis}",
    )
