"""What the design DOESN'T cover — the half of the intent the matcher quietly dropped.

Found 2026-09-07 by tracing a real request through the shipped path:

    "I wanna build an app like Uber with video call capabilities"
      -> matched 'ride_sharing' on the word "uber"
      -> returned an 8-component design with no media server, no signalling, no TURN
      -> and said nothing about it

Every number on that report is correct FOR A RIDE-SHARING APP. None of it accounts for the video
calling the user explicitly asked for, and the report presented the result as the answer to the
whole question. That is the same defect class `generate.py` fixed for the fallback path: a design
that is about something narrower than what was asked, printed with confident numbers and no
disclosure. Matching on a fragment is fine — the reference library exists to answer the common
shape instantly. Matching on a fragment and staying SILENT about the remainder is not.

So: after a reference is matched, check the intent for capabilities the resulting model plainly
does not contain, and write each one onto the model as a GAP assumption. The report, the studio
rail and the arch map all render assumptions, so the disclosure travels with the numbers instead
of living in a docstring.

DESIGN NOTES

* **A capability counts as MISSING only if the intent asks for it AND nothing in the model looks
  like it.** The component check is deliberately loose (substring over component names and kinds),
  because a false "you're missing X" when X is present is noise that trains people to ignore the
  section — the one failure mode that would make this worthless.
* **No LLM.** Same reason as `domains.py`: a disclosure about the model's own blind spots must not
  be authored by a model.
* **This adds an assumption and changes no number** (docs/03, evidence-only). The engine never
  reads it. The design is not silently extended to cover the gap — Keystone says what is missing
  and leaves adding it to the person, because inventing components would invent their capacity,
  their cost and their latency too.
"""
from __future__ import annotations

from .model import Assumption

__all__ = ["CAPABILITIES", "missing_capabilities", "declare_coverage_gaps", "unbuilt_matches"]

# asked-for capability -> (phrases that request it, substrings that would prove it is present,
#                          what it actually costs you to add, so the gap is actionable)
CAPABILITIES: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "real-time video or voice calling": (
        ("video call", "video calling", "video chat", "voice call", "audio call", "webrtc",
         "face time", "facetime", "video conferencing", "live video", "voip"),
        ("webrtc", "sfu", "media server", "turn", "stun", "signalling", "signaling", "video"),
        "a signalling service, a TURN/STUN relay for clients behind NAT, and either peer-to-peer "
        "media or an SFU if more than two people join a call. Media is bandwidth-priced, not "
        "request-priced, so it lands on a different cost line from everything modelled here.",
    ),
    "live text messaging": (
        ("chat", "messaging", "direct message", "instant messag", "im "),
        ("websocket", "chat", "message", "messaging", "presence", "pubsub", "pub/sub"),
        "a persistent-connection tier (WebSocket) plus presence and fan-out, which is sized by "
        "CONCURRENT CONNECTIONS rather than by requests per second.",
    ),
    "taking payments": (
        ("payment", "pay ", "paying", "checkout", "billing", "subscription", "wallet", "payout"),
        # NOT bare "gateway": it matches "API Gateway (auth + routing)", which serves no payment
        # at all. A generic evidence term silently marks a real gap as covered — the exact failure
        # this module exists to prevent, so the evidence has to be as specific as the capability.
        ("payment", "billing", "ledger", "wallet", "stripe", "payment gateway", "psp", "checkout"),
        "a payment gateway, an idempotent ledger and a reconciliation path. Money is a harm-floor "
        "area: it needs integer minor units and exactly-once semantics, not best effort.",
    ),
    "search over user content": (
        ("search", "full text", "full-text", "discovery feed", "autocomplete", "typeahead"),
        ("search", "elastic", "opensearch", "index", "typeahead", "solr"),
        "a search index kept in sync with the primary store, which is a second copy of the data "
        "with its own consistency lag and its own failure mode.",
    ),
    "push notifications": (
        ("push notification", "notify user", "notifications", "alerts to users"),
        ("push", "notif", "fcm", "apns", "sms", "email"),
        "a notification queue and a third-party push provider, whose throughput is a contract you "
        "buy rather than capacity you provision.",
    ),
    "machine learning or LLM inference": (
        ("machine learning", " ml ", "recommendation", "llm", "ai model", "inference",
         "chatbot", "embedding", "rag"),
        ("inference", "llm", "gpu", "embedding", "vector", "recommend", "model api"),
        "an inference tier or a model API. Token or GPU-second spend is usually the dominant cost "
        "line and it is not proportional to request count.",
    ),
    "video streaming or playback": (
        ("video streaming", "watch video", "vod", "live stream", "streaming video"),
        ("cdn", "transcode", "hls", "dash", "stream", "video", "media"),
        "transcoding (a batch workload sized by backlog-drain deadline, not by rps) and CDN "
        "delivery, which is bytes-priced and normally dwarfs the compute bill.",
    ),
    "file or media uploads": (
        ("upload", "file sharing", "photo upload", "attach file"),
        ("object_store", "s3", "storage", "bucket", "media", "upload", "blob"),
        "object storage plus a presigned-upload path, so raw bytes bypass your servers. Storage "
        "and egress are volume-priced and are not in a compute estimate.",
    ),
}


def missing_capabilities(intent: str, model) -> list[tuple[str, str]]:
    """(capability, what adding it involves) for everything the intent asks for and the model lacks.

    A capability is present if any of its evidence substrings appears in a component NAME or KIND.
    Loose on purpose: over-reporting a gap that is actually covered is the failure that makes the
    whole section ignorable.
    """
    if not intent or model is None:
        return []
    hay = f" {intent.lower()} "
    haystack = " ".join(
        f"{c.name.lower()} {c.kind.value.lower()}" for c in model.components.values()
    )
    out: list[tuple[str, str]] = []
    for capability, (asks, evidence, cost) in CAPABILITIES.items():
        if not any(a in hay for a in asks):
            continue
        if any(e in haystack for e in evidence):
            continue
        out.append((capability, cost))
    return out


def unbuilt_matches(intent: str, model) -> list[tuple[str, str]]:
    """(name, summary) for library designs this intent ALSO asked for and did not get.

    The matcher returns ONE blueprint and silently drops the rest. "Facebook with a crypto wallet
    for all users" came back as a Digital Wallet — correct for the wallet half, with no social graph
    anywhere and not a word about it. The library already knew the intent hit a social blueprint
    too; only the ranking threw it away.

    So: ask the library for EVERY entry the intent hits, drop the one we actually built, and report
    the rest. This is not a guess — each is a design Keystone has, gated and simulatable, that the
    reader asked for and is not looking at.
    """
    from .blueprint_library import all_matches          # local: keeps the import graph flat
    built = (model.name or "").strip().lower()
    out: list[tuple[str, str]] = []
    for entry, _hits, _kw in all_matches(intent):
        if entry.name.strip().lower() == built:
            continue
        out.append((entry.name, entry.summary))
    return out


def declare_coverage_gaps(model, intent: str):
    """Write each missing capability onto the model as a GAP assumption, in place.

    Evidence-only: appends assumptions, changes no number. Returns the model for inline use.
    """
    extra = [
        Assumption(
            subject="coverage",
            statement=(
                f"YOU ASKED FOR TWO THINGS AND THIS IS ONE OF THEM. Your description also matches "
                f"Keystone's \"{name}\" design — {summary} — and none of it is in the architecture "
                f"below. Every figure here describes {model.name} alone. Design the other half "
                f"separately, then decide how the two systems talk to each other; that boundary is "
                f"usually where the real work is."
            ),
            confidence="high", source="benchmark", provenance="GAP",
        )
        for name, summary in unbuilt_matches(intent, model)
    ]
    if extra:
        model.assumptions = list(model.assumptions) + extra

    gaps = missing_capabilities(intent, model)
    if not gaps:
        return model
    model.assumptions = list(model.assumptions) + [
        Assumption(
            subject="coverage",
            statement=(
                f"NOT IN THIS DESIGN: you asked for {capability}, and nothing in this architecture "
                f"provides it. Every figure below — the bottleneck, the breakpoint, the latency and "
                f"the cost — describes the system as drawn, WITHOUT that capability, so treat them "
                f"as a floor rather than an estimate for what you actually described. Adding it "
                f"needs {cost}"
            ),
            confidence="high",
            source="benchmark",
            provenance="GAP",
        )
        for capability, cost in gaps
    ]
    return model
