"""High-stakes DOMAIN DETECTION — the missing half of the expert-review gate.

`council.py` has always had the enforcement half: `is_high_stakes()` reads `model.domain_flags`
and `ensure_high_stakes_gate()` re-inserts the expert-review ADR if a model tried to omit it. That
is real defence against a *forged* ADR. What did not exist was DETECTION — nothing ever looked at
what the user asked for and decided the flag belonged there.

The consequence, measured on the shipped path 2026-09-07 by calling the exact function `/generate`
calls:

    'a payments checkout system'            -> ['high_stakes:payments']
    'a hospital patient records system'     -> []
    'an election result tallying platform'  -> []
    'a medication dosing calculator'        -> []
    'a flight control telemetry dashboard'  -> []

Only payments fired, and only because `blueprints/payments.py` HARDCODES the flag on that one
model. `docs/03-Accuracy-and-Trust-Charter.md` names four mandatory domains — "elections, payments,
health, safety" — and three of the four failed OPEN, returning a priced design with percentiles and
a "medium-high confidence" string and no expert-review block anywhere. The gate was armoured
against forgery and had no eyes.

DESIGN RULES, all pointing the same way — toward over-flagging:

* **Fail LOUD, not silent.** A false positive costs a reader one extra paragraph telling them to get
  a domain expert. A false negative ships an unreviewed election-tallying or drug-dosing design.
  Those are not comparable, so the matching is deliberately generous.
* **Substrings, and word-boundary-free on purpose.** "cardiology", "ballots", "avionics" should all
  fire. The cost of a stray hit is the paragraph above.
* **This ADDS flags, never removes them.** A blueprint that hardcodes its own flag keeps it; the
  detector unions on top. Nothing here can clear a flag another layer set.
* **No LLM.** Detection that decides whether a human expert is required must not itself depend on a
  language model's wording — that is the same reason `is_high_stakes` reads structured flags rather
  than prose (council.py:46).

This is DETECTION, not judgement: it decides that a domain needs an expert, never what the expert
should conclude.
"""
from __future__ import annotations

__all__ = ["HIGH_STAKES_TERMS", "detect_high_stakes", "apply_high_stakes_flags"]

# Keyed by the domain name that ends up in the flag: "high_stakes:<key>". The four keys are exactly
# the four docs/03 names. Terms are lowercase substrings.
HIGH_STAKES_TERMS: dict[str, tuple[str, ...]] = {
    "elections": (
        "election", "ballot", "polling station", "vote count", "vote tally", "voting",
        "voter", "referendum", "electoral", "psepholog", "constituency result",
    ),
    "payments": (
        "payment", "checkout", "billing", "invoice", "payout", "settlement", "remittance",
        "money transfer", "wallet", "bank", "banking", "card processing", "stripe", "paystack",
        "flutterwave", "paypal", "ledger", "escrow", "payroll", "lending", "loan", "credit score",
        "insurance claim", "trading", "brokerage", "exchange rate", "crypto", "tax filing",
    ),
    "health": (
        "health", "medical", "patient", "clinic", "hospital", "diagnos", "prescription",
        "medication", "dosing", "dosage", "pharmac", "ehr", "emr", "phi", "hipaa", "triage",
        "radiolog", "cardiolog", "oncolog", "telemedicine", "mental health", "therapy",
        "clinical trial", "lab result", "vaccin", "surgery", "icu", "ambulance",
    ),
    "safety": (
        "safety-critical", "safety critical", "life support", "aviation", "avionic",
        "flight control", "air traffic", "railway signal", "rail signal", "autonomous driving",
        "self-driving", "collision avoidance", "nuclear", "reactor", "industrial control",
        "scada", "emergency dispatch", "911 ", "999 ", "112 ", "firefight", "fire alarm",
        "gas leak", "structural monitoring", "elevator control", "medical device",
        "weapon", "defence system", "defense system", "power grid", "water treatment",
    ),
}


def detect_high_stakes(text: str) -> tuple[str, ...]:
    """Every `high_stakes:<domain>` flag the text earns, sorted and de-duplicated.

    Matching is substring and case-insensitive, so "Cardiology" and "e-Voting" both fire. Returns an
    empty tuple for ordinary intents — the common case must stay quiet or the flag means nothing.
    """
    if not text:
        return ()
    hay = text.lower()
    return tuple(sorted(
        f"high_stakes:{domain}"
        for domain, terms in HIGH_STAKES_TERMS.items()
        if any(t in hay for t in terms)
    ))


def apply_high_stakes_flags(model, intent: str):
    """Union the intent's detected flags onto a model's `domain_flags`, in place.

    Unions rather than assigns: `payments.build()` sets its own flag from the design itself, and a
    detector must never be able to clear a flag some other layer had good reason to set. Returns the
    model so it can be used inline.
    """
    detected = detect_high_stakes(intent)
    if not detected:
        return model
    existing = list(model.domain_flags or [])
    model.domain_flags = sorted(set(existing) | set(detected))
    return model
