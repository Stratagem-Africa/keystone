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
from keystone.ingestion import Source, make_ingestor
from keystone.model import SystemModel

# (keyword triggers, builder, label). First match wins — order most-specific first. The blueprint
# library is the offline "generation" for common intents; the LLM generalises to anything else.
_REFERENCES: tuple[tuple[tuple[str, ...], object, str], ...] = (
    (("twitter", "social network", "social media", "social platform", "microblog", "instagram",
      "tiktok", "news feed", "timeline", "followers", " x "), twitter.build, "social platform"),
    (("payment", "checkout", "billing", "e-commerce", "ecommerce", "commerce", "online shop",
      "online store", "storefront", "stripe", "cart"), payments.build, "payments / checkout"),
    (("ticket", "booking", "reservation", "box office", "seats", "flash sale", "flash-sale",
      "event platform"), ticket_booking.build, "ticket booking"),
    (("url shortener", "link shortener", "short link", "shortlink", "bitly", "tinyurl"),
     url_shortener.build, "URL shortener"),
)


def match_reference(intent: str):
    """Best-matching reference (build_fn, label) for an intent, or None. Keyword match — deliberately
    simple; the LLM path is what generalises beyond the catalogue."""
    q = f" {intent.lower()} "
    for triggers, build, label in _REFERENCES:
        if any(t in q for t in triggers):
            return build, label
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
        return ingestor.ingest(Source(text=intent, name=(intent[:60] or "intent"))).model
    ref = match_reference(intent)
    if ref is not None:
        return ref[0]()
    # No LLM and no catalogue match: hand back a real, deep starting point the user can edit on the
    # canvas — honest about the limit (arbitrary-intent generation needs the LLM activated, #182).
    return url_shortener.build()


def reference_catalogue() -> list[str]:
    """Human-readable list of the offline reference architectures (for a 'try one of these' hint)."""
    return [label for _t, _b, label in _REFERENCES]
