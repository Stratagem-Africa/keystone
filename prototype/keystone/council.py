"""Consensus council layer (Doc 04 F4).

The council REASONS (designs, justifies, critiques); it never produces metrics.
Real implementation: independent design -> blind peer review -> chairman synthesis,
run as a single Claude model with multiple persona system-prompts (cost control,
Doc 02 §4), grounded in the Knowledge Base.

This file defines the interface plus a DETERMINISTIC STUB so the whole Phase-0 loop
runs end-to-end with no API key. The stub's ADRs are illustrative, not live reasoning
-- clearly tagged. Drop in ClaudeCouncil (provider: claude) to activate real design.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from keystone.model import ComponentKind, SystemModel

# Cheap dev default (Doc 02 §4 — one model, control cost). Mirrors .env.example;
# set COUNCIL_MODEL=claude-opus-4-8 for a production-grade council.
DEFAULT_COUNCIL_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class ADR:
    """Architecture Decision Record with recorded dissent (schema per Doc 04 F4,
    borrowed from the LLM-Council-Decide output shape)."""
    area: str
    decision: str
    rationale: str
    dissent: list[str] = field(default_factory=list)
    confidence: str = "med"           # low | med | high
    kill_criteria: list[str] = field(default_factory=list)
    source: str = "stub"              # "stub" | "<provider>:<model>" (honest council provenance)
    # Cross-model consensus votes (ADR-010 multi-LLM): one rendered line per voter model
    # (e.g. "openai gpt-5: AGREE — …"). Empty for the single-model / stub path (backward-compatible).
    # Each vote's free text is scrubbed by the prime-directive guard before it lands here.
    consensus: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# High-stakes review gate (Doc 03 §6 MUST; ADR-001 C1) — shared by both councils
# --------------------------------------------------------------------------- #
# The mandatory expert-review block's presence is a DETERMINISTIC function of
# model.domain_flags, never contingent on LLM wording. De-dup keys on the gate's
# OWN identity (canonical area/decision), NOT on a loose "review" substring of an
# LLM-authored ADR area — that substring let a benign "Code review process" ADR
# silently drop the MUST block (ADR-001 finding C1).
HIGH_STAKES_AREA = "Review gate"
HIGH_STAKES_DECISION = "REQUIRES expert/legal/security review before any production use."


def is_high_stakes(domain_flags: list[str]) -> bool:
    """True if any flag marks a high-stakes domain. Normalised (case/space/hyphen)
    so the gate fails CLOSED on front-door variants ('HIGH_STAKES:', ' high-stakes:')
    once the ingestion layer can emit them (ADR-001 M3)."""
    return any(
        f.strip().lower().replace("-", "_").startswith("high_stakes")
        for f in domain_flags
    )


def _high_stakes_gate_adr(source: str) -> ADR:
    return ADR(
        area=HIGH_STAKES_AREA,
        decision=HIGH_STAKES_DECISION,
        rationale="Domain flagged high-stakes; Keystone does not certify safety.",
        confidence="high",
        kill_criteria=["Shipped without independent expert sign-off"],
        source=source,
    )


def ensure_high_stakes_gate(adrs: list[ADR], domain_flags: list[str], *, source: str) -> list[ADR]:
    """Guarantee the mandatory expert-review block for high-stakes domains (Doc 03
    §6 MUST). The gate is KEYSTONE-OWNED, never LLM-substitutable: any incoming ADR
    that impersonates the reserved gate (its canonical area OR decision) is stripped,
    then the authoritative gate is appended unconditionally. This closes both ADR-001
    C1 (a benign 'Code review' area could suppress it) and the re-verification finding
    that a chairman could forge a 'Review gate' ADR carrying 'no external review needed'
    to suppress the real one. Operates in place; idempotent (the canonical gate gets
    stripped then re-appended on a repeat call, leaving exactly one)."""
    if not is_high_stakes(domain_flags):
        return adrs
    adrs[:] = [
        a for a in adrs
        if not (a.area == HIGH_STAKES_AREA or a.decision.strip() == HIGH_STAKES_DECISION)
    ]
    adrs.append(_high_stakes_gate_adr(source))
    return adrs


class Council(Protocol):
    def design(self, model: SystemModel) -> list[ADR]:
        ...


class DeterministicStubCouncil:
    """Stand-in for the real council so the pipeline runs without an LLM.
    Clearly-labelled illustrative ADRs, derived from the model. NOT live reasoning."""

    def design(self, model: SystemModel) -> list[ADR]:
        """ADRs derived from THIS model's own structure.

        These used to be three hardcoded decisions about a URL shortener — "the mapping table",
        "cache-aside on the redirect (read) path", "create (write) traffic exceeds ~30%" — returned
        for every model, because `design()` took `model` and ignored it. The committed golden
        `outputs/ticket_booking_report.md` therefore shipped, under the heading "Design decisions
        (council)", three decisions about a different product entirely.

        That is exactly the defect `generate.py` calls out for the fallback path: presenting another
        product's architecture as the answer, and a label saying "illustrative" does not discharge
        it when the artifact itself is describing someone else's system. A stub may be shallow — it
        must not be about the wrong thing.

        So each decision is now composed from what the engine can actually see in this model: the
        datastores present, whether a cache sits on the dominant read path, and which components are
        single points of failure. No numbers (prime directive) — structure and names only.
        """
        stores = [c for c in model.components.values()
                  if c.kind in (ComponentKind.SQL_DB, ComponentKind.OBJECT_STORE)]
        caches = [c for c in model.components.values() if c.kind == ComponentKind.CACHE]
        replicas = [c for c in model.components.values() if c.kind == ComponentKind.REPLICA]
        queues = [c for c in model.components.values() if c.kind == ComponentKind.QUEUE]
        externals = [c for c in model.components.values() if c.kind == ComponentKind.EXTERNAL_API]
        spofs = [c.name for c in model.components.values() if c.is_spof]
        subject = model.name

        def names(cs, empty="none in this design"):
            return ", ".join(c.name for c in cs) if cs else empty

        adrs: list[ADR] = []

        adrs.append(ADR(
            area="Datastore",
            decision=(f"{subject} keeps its system of record in {names(stores)}."
                      if stores else
                      f"{subject} declares no database — state lives outside the modelled system."),
            rationale=("A relational primary is the boring, reliable default; it is the component "
                       "whose write path cannot be scaled out by adding instances, so the design "
                       "hangs on it."
                       if stores else
                       "Nothing here owns durable state, so there is no write bottleneck to reason "
                       "about — confirm that is deliberate and not an omission in the model."),
            dissent=["Data engineer: if writes dominate, a partitioned or KV store scales that path "
                     "more cheaply than a single primary; revisit if the write share rises."],
            confidence="high" if stores else "low",
            kill_criteria=["Write traffic outgrows what one primary can serve",
                           "A second service needs write access to the same tables"],
        ))

        adrs.append(ADR(
            area="Caching",
            decision=(f"Reads are shielded by {names(caches)}"
                      + (f", with {names(replicas)} behind it." if replicas else ".")
                      if caches else
                      f"{subject} has no cache tier; reads go straight to the system of record."),
            rationale=("The read path dominates, and a cache keeps that volume off the primary."
                       if caches else
                       "Every read is paid for at the datastore. That is simpler and correct, and "
                       "it is the first thing to revisit when the read path binds."),
            dissent=["YAGNI-skeptic: a cache is a second source of truth and a new failure mode; "
                     "do not add one before the read path is demonstrably the constraint."],
            confidence="med",
            kill_criteria=["Cache hit-rate falls far enough that the primary sees the read storm",
                           "Stale reads become user-visible in a way the product cannot accept"],
        ))

        if queues or externals:
            adrs.append(ADR(
                area="Asynchronous work and third parties",
                decision=(f"Work is deferred through {names(queues)}." if queues else "")
                         + (f" {subject} depends on {names(externals)}, which it does not own."
                            if externals else ""),
                rationale=("Deferring work keeps the request path short. A dependency you do not "
                           "own cannot be scaled by adding your own instances — its limit is "
                           "contractual, so it has to be designed around rather than provisioned "
                           "away." if externals else
                           "Deferring work keeps the request path short and absorbs bursts."),
                dissent=["SRE: a queue converts a fast failure into a slow backlog; decide now what "
                         "happens to messages that cannot be delivered."],
                confidence="med",
                kill_criteria=["Backlog drain time exceeds what the product can tolerate",
                               "A third party's quota becomes the binding constraint"],
            ))

        adrs.append(ADR(
            area="Resilience",
            decision=(f"Single points of failure in this design: {', '.join(spofs)}."
                      if spofs else
                      "No single points of failure — every tier in this design is replicated."),
            rationale=("Each of these is one instance; losing it takes the system with it."
                       if spofs else
                       "Every component carries more than one instance, so no single loss is total."),
            dissent=["YAGNI-skeptic: acceptable to defer for a prototype (Tier-0), but NOT for "
                     "external traffic (Tier-1)."],
            confidence="med" if spofs else "high",
            kill_criteria=["Going to external/production traffic with a single-instance tier"],
        ))

        # High-stakes guard (Doc 03 §6): never imply production-safety for flagged
        # domains. Shared, identity-based gate (ADR-001 C1) — same as the real council.
        return ensure_high_stakes_gate(adrs, model.domain_flags, source="stub")
        # High-stakes guard (Doc 03 §6): never imply production-safety for flagged
        # domains. Shared, identity-based gate (ADR-001 C1) — same as the real council.
        return ensure_high_stakes_gate(adrs, model.domain_flags, source="stub")


def make_council(provider: str | None = None, model: str | None = None,
                 *, client=None, meter=None) -> Council:
    """Build the configured council.

    Defaults to the deterministic stub so the whole loop runs with no API key and
    at $0 (CLAUDE.md cost rule). Reads COUNCIL_PROVIDER and COUNCIL_MODEL from the
    environment when not passed explicitly. The real council is PROVIDER-AGNOSTIC
    (ADR-010): COUNCIL_PROVIDER may be `stub`, `consensus`, or any single LLM
    provider — `claude`/`anthropic` (SDK) or `openai | openrouter | gemini | groq |
    ollama` (OpenAI-compatible transport). It reasons through the shared `LLM` seam
    and the prime-directive guard scrubs its output regardless of vendor, so a
    free-tier Gemini/Groq key or a local Ollama drives the real council at $0. Every
    provider is imported lazily, so the zero-dependency engine never pulls in the
    Anthropic SDK (or any transport) just by importing this module.

    `client` lets a caller (or a test) inject an LLM transport for ANY non-stub
    provider — the path used for $0 offline testing (no network, no key).

    `meter` is an optional `CostMeter` (keystone.cost_meter) threaded to every real
    transport so a run can report Keystone's own API spend. It is opt-in operational
    telemetry — it changes NO product number and is untouched on the stub path.
    """
    provider = (provider or os.getenv("COUNCIL_PROVIDER", "stub")).strip().lower()
    if provider == "stub":
        return DeterministicStubCouncil()
    if provider == "claude_panel":
        # DECK 1: Keystone's seven personas run as SUBAGENTS inside one Claude Code call, instead of
        # one call per persona. Same personas, same prime-directive guard, one session.
        # COUNCIL_PROVIDER=consensus can still wrap this as DECK 2 with independent voter MODELS.
        from keystone.panel_council import PanelCouncil  # lazy
        return PanelCouncil(model=model or os.getenv("COUNCIL_MODEL", ""), meter=meter)
    if provider == "consensus":
        # Multi-model consensus (ADR-010): a PRIMARY council (CONSENSUS_PRIMARY, default claude) wrapped
        # with independent voter models (CONSENSUS_VOTERS). The primary spec is `provider:model`, so the
        # primary can now be ANY provider (e.g. gemini:gemini-2.0-flash). Lazy; stays $0 until configured.
        from keystone.consensus import make_consensus_council  # lazy
        # The primary may itself be `claude_panel`, which is what makes the stack double-decker:
        # a panel of personas underneath, independent voter models on top.
        prim_provider, _, prim_model = os.getenv("CONSENSUS_PRIMARY", "claude").partition(":")
        primary = make_council(prim_provider.strip() or "claude", prim_model.strip() or None,
                               client=client, meter=meter)
        return make_consensus_council(primary=primary, meter=meter)

    # Any single LLM provider drives the REAL council — it is provider-agnostic (ADR-010): the council
    # REASONS through the `LLM` seam and the prime-directive guard scrubs its output regardless of vendor.
    # `claude`/`anthropic` keep the SDK default + the default model; every other provider is built via
    # `make_llm` and REQUIRES an explicit COUNCIL_MODEL (no sensible cross-vendor default). A free-tier
    # Gemini/Groq key or a local Ollama therefore runs the real council at $0.
    from keystone.claude_council import ClaudeCouncil  # lazy: optional dep
    if provider in ("claude", "anthropic"):
        claude_model = model or os.getenv("COUNCIL_MODEL", DEFAULT_COUNCIL_MODEL)
        return ClaudeCouncil(model=claude_model, client=client, source=f"claude:{claude_model}", meter=meter)
    # Validate the provider NAME before anything else, so a blank/typo'd provider gives one clear
    # error (not a misleading "needs a model") — preserving main's diagnostic on the fail-closed path.
    from keystone.llm import make_llm, known_providers  # lazy: transport built only for a live provider
    if provider not in known_providers():
        raise ValueError(
            f"Unknown COUNCIL_PROVIDER={provider!r}. Use one of: stub | consensus | claude | "
            "claude_cli | openai | openrouter | gemini | groq | cerebras | xai | github | nvidia "
            "| ollama."
        )
    council_model = model or os.getenv("COUNCIL_MODEL")
    # The local CLI reads its own configured default model from the user's Claude Code settings, so
    # COUNCIL_MODEL is optional there — unlike a raw API transport, where there is no sensible
    # cross-vendor default and a missing model has to be an error.
    model_optional = provider == "claude_cli"
    if not council_model and not model_optional:
        raise ValueError(
            f"COUNCIL_PROVIDER={provider!r} needs an explicit model — set COUNCIL_MODEL "
            "(e.g. gemini-2.0-flash, llama-3.3-70b-versatile, llama3.2:3b)."
        )
    return ClaudeCouncil(model=council_model or "", 
                         source=f"{provider}:{council_model or 'default'}", meter=meter,
                         client=client if client is not None else make_llm(provider, council_model, meter=meter))
