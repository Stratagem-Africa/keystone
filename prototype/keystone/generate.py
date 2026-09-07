"""Turn a one-line intent ("a platform like Twitter") into a DEEP, validated SystemModel.

Two paths, same output contract (a SystemModel the engine can simulate + the canvas can render):

- **LLM (when activated)** — `INGEST_PROVIDER` is a real provider (claude|openai|…), or a `client`/`provider`
  is passed: `ClaudeIngestor` DESIGNS a full, layered architecture from the intent (its system prompt now
  asks for 12-25 components across the layers with real request journeys). This is the general case — any
  intent. Requires the LLM layers live (a manual Bifola trigger, issue #182).
- **Reference library ($0, offline, default)** — match the intent to the closest deep REFERENCE
  architecture (the blueprint catalogue — same idea as SysSimulator's blueprints). Works today with no key.

Prime directive intact: this only produces the INPUT *design*; `simulation.simulate` remains the sole
source of every number. Fail-closed: the LLM path validates (raises IngestError on a bad model); the
reference path returns a hand-built, already-valid blueprint.
"""
from __future__ import annotations

import os

from keystone.blueprints import payments, ticket_booking, twitter, url_shortener
from keystone.domains import apply_high_stakes_flags
from keystone.ingestion import Source, make_ingestor
from keystone.model import (
    Assumption, Component, ComponentKind, Flow, FlowStep, SystemModel, Workload,
)

# (keyword triggers, builder, label). First match wins — order most-specific first. The blueprint
# library is the offline "generation" for common intents; the LLM generalises to anything else.
_REFERENCES: tuple[tuple[tuple[str, ...], object, str], ...] = (
    # SCOPE OF EACH TIER-1 TRIGGER — narrowed once the library shipped a better answer.
    # Tier 1 wins on any trigger it claims, so a trigger it should not own is a wrong ANSWER, not a
    # missed opportunity: "instagram" used to return the Twitter design, whose components are named
    # "Tweet Service" and "Timeline Service (fan-out read)" — the identity leak `test_generic_fallback`
    # exists to prevent, arriving through the matcher instead of the fallback. And "an online store"
    # used to return the 5-component payments design, which has no catalogue, no cart and no
    # inventory: a checkout is PART of a storefront, not a storefront. Both now have dedicated,
    # engine-gated library blueprints, so tier 1 gives those words up and keeps only what it is
    # genuinely the deepest answer for.
    (("twitter", "social network", "social media", "social platform", "microblog",
      "tiktok", "news feed", "timeline", "followers", " x "), twitter.build, "social platform"),
    (("payment", "checkout", "billing", "stripe"), payments.build, "payments / checkout"),
    (("ticket", "booking", "reservation", "box office", "seats", "flash sale", "flash-sale",
      "event platform"), ticket_booking.build, "ticket booking"),
    (("url shortener", "link shortener", "short link", "shortlink", "bitly", "tinyurl"),
     url_shortener.build, "URL shortener"),
)


def match_reference(intent: str):
    """Best-matching reference (build_fn, label) for an intent, or None.

    Two tiers, most specific first:
      1. The hand-built deep blueprints in `_REFERENCES` — richer than anything generated (the
         Twitter one carries 20 components and six journeys), so they win where they match.
      2. The BLUEPRINT LIBRARY: spec files under `blueprints/library/`, each of which had to pass
         the engine gate (`blueprint_library.validate_library_entry`) before it shipped — it
         simulates, it holds at its own design load, and its costs come from the grounded
         catalogue rather than a hand-typed guess.

    Keyword matching is deliberately simple in both tiers; the LLM design path is what generalises
    to an arbitrary intent. The library's job is to answer the common cases instantly, offline, $0.
    """
    q = f" {intent.lower()} "
    for triggers, build, label in _REFERENCES:
        if any(t in q for t in triggers):
            return build, label

    from keystone.blueprint_library import match as _match_library   # lazy: keeps import graph flat
    entry = _match_library(intent)
    if entry is not None:
        return entry.build, entry.name
    return None


def generate_architecture(intent: str, *, provider: str | None = None,
                          model: str | None = None, client=None) -> SystemModel:
    """Intent → a deep, validated SystemModel. Uses the LLM to DESIGN it when a live provider/client is
    available (any intent); otherwise falls back to the closest reference architecture (offline, $0)."""
    prov = (provider or os.getenv("INGEST_PROVIDER", "stub")).strip().lower()
    use_llm = client is not None or prov not in ("", "stub")
    if use_llm:
        # A passed client forces the LLM design path even if INGEST_PROVIDER=stub; `claude` is the
        # default transport shape for an injected client (make_ingestor('stub', ...) ignores it).
        eff_provider = provider or (prov if prov not in ("", "stub") else "claude")
        ingestor = make_ingestor(eff_provider, model=model, client=client)
        designed = ingestor.ingest(Source(text=intent, name=(intent[:60] or "intent"))).model
        # Also on the LLM path, and deliberately NOT delegated to the model: whether a human expert
        # is required is not a judgement a language model gets to make about its own output.
        return apply_high_stakes_flags(designed, intent)
    ref = match_reference(intent)
    built = ref[0]() if ref is not None else generic_starting_point(intent)
    # DETECT the high-stakes domain from what the user actually asked for. Until 2026-09-07 the
    # flag could only arrive by being hardcoded on a blueprint, so "a hospital patient records
    # system" and "an election result tallying platform" both returned domain_flags == [] and no
    # expert-review gate — three of docs/03's four mandatory domains failed OPEN. See domains.py.
    return apply_high_stakes_flags(built, intent)


def generic_starting_point(intent: str = "") -> SystemModel:
    """The honest answer when nothing matched: a neutral three-tier shape to edit, that never
    pretends to be a design of the thing you asked for.

    This used to `return url_shortener.build()`. That was a real honesty defect, not a cosmetic one:
    asking for a video service or a bidding exchange handed back a model literally NAMED "URL
    Shortener", and every downstream surface — the design card, the verdict, the cost, the chaos
    catalogue, the remediation plan — then presented another product's architecture as the answer,
    with confident numbers attached. Under docs/03 the assumption behind a printed number has to
    travel WITH it; a single line of chrome saying "generic starting point" does not discharge that
    when the artifact itself is wearing someone else's name.

    So the fallback now carries its own identity and its own GAP assumption, which flows into the
    report's Assumptions section and the canvas rail like any other provenance. The shape is
    deliberately plain — a load balancer, an app tier, a cache and a primary — because a neutral
    starting point is a defensible thing to hand someone and a borrowed blueprint is not.

    The real fix for arbitrary intents is the LLM design path above (issue #182); this keeps the
    offline, $0 default honest until that is activated.
    """
    asked = (intent or "").strip()
    components = {
        "lb": Component("lb", ComponentKind.LOAD_BALANCER, "Load balancer",
                        per_instance_rps=30_000, instances=1, base_latency_ms=1.0,
                        monthly_cost_per_instance=2_500),
        "app": Component("app", ComponentKind.APP_SERVER, "Application tier",
                         per_instance_rps=1_200, instances=4, base_latency_ms=8.0,
                         monthly_cost_per_instance=3_000),
        "cache": Component("cache", ComponentKind.CACHE, "Cache",
                           per_instance_rps=100_000, instances=1, base_latency_ms=0.5,
                           monthly_cost_per_instance=12_000),
        "db": Component("db", ComponentKind.SQL_DB, "Primary database",
                        per_instance_rps=8_000, instances=1, base_latency_ms=5.0,
                        monthly_cost_per_instance=25_000),
    }
    flows = [
        Flow(name="read", share=0.9, path=[
            FlowStep("lb"), FlowStep("app"), FlowStep("cache"), FlowStep("db", visit_prob=0.2)]),
        Flow(name="write", share=0.1, path=[FlowStep("lb"), FlowStep("app"), FlowStep("db")]),
    ]
    return SystemModel(
        name="Generic starting point (no reference matched)",
        components=components,
        flows=flows,
        workload=Workload(system_rps=1_000, description="placeholder load — set this to your own"),
        assumptions=[
            Assumption(
                subject="design",
                statement=(
                    "No reference architecture matched"
                    + (f" \u201c{asked[:80]}\u201d" if asked else " this intent")
                    + ". This is a NEUTRAL three-tier starting point, not a design of what you "
                      "asked for — the shape, the component sizes and the 1,000 req/s load are "
                      "placeholders to edit. Every number below is the engine's arithmetic on "
                      "those placeholders, so it describes this generic shape and nothing else. "
                      "Designing an arbitrary intent needs the LLM design path (issue #182)."),
                confidence="low", source="fallback", provenance="GAP"),
            Assumption(
                subject="workload",
                statement="1,000 req/s placeholder, 90:10 read:write — not derived from your intent",
                confidence="low", source="fallback", provenance="GAP"),
        ],
    )


def reference_catalogue() -> list[str]:
    """Human-readable list of the offline reference architectures (for a 'try one of these' hint)."""
    return [label for _t, _b, label in _REFERENCES]
