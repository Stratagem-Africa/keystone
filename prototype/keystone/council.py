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

from keystone.model import SystemModel

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
    source: str = "stub"              # stub | claude
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
    Returns canned, clearly-labelled ADRs. NOT live reasoning."""

    def design(self, model: SystemModel) -> list[ADR]:
        adrs = [
            ADR(
                area="Datastore",
                decision="Single relational primary (PostgreSQL) for the mapping table.",
                rationale="Workload is simple key->value with strong-read tolerance once "
                          "cached; a relational primary is the boring, reliable default.",
                dissent=["Data engineer: a KV store (DynamoDB) scales writes more cheaply "
                         "at very high create volume; revisit if write share rises."],
                confidence="high",
                kill_criteria=["Create (write) traffic exceeds ~30% of total",
                               "Mapping table exceeds single-primary write capacity"],
            ),
            ADR(
                area="Caching",
                decision="Cache-aside on the redirect (read) path with a high hit-rate cache.",
                rationale="Redirects dominate traffic and are highly cacheable; the cache "
                          "shields the primary from the read storm.",
                dissent=["SRE: the cache is now load-bearing -- a cold cache or stampede "
                         "melts the DB. Add request-coalescing / stampede protection."],
                confidence="high",
                kill_criteria=["Cache hit-rate falls below ~70% in production",
                               "No stampede protection before launch"],
            ),
            ADR(
                area="Resilience",
                decision="Add a read replica and cache failover before production.",
                rationale="A single primary and single cache are single points of failure.",
                dissent=["YAGNI-skeptic: acceptable to defer for a prototype (Tier-0), but "
                         "NOT for external traffic (Tier-1)."],
                confidence="med",
                kill_criteria=["Going to external/production traffic with 1 DB + 1 cache"],
            ),
        ]
        # High-stakes guard (Doc 03 §6): never imply production-safety for flagged
        # domains. Shared, identity-based gate (ADR-001 C1) — same as the real council.
        return ensure_high_stakes_gate(adrs, model.domain_flags, source="stub")


def make_council(provider: str | None = None, model: str | None = None,
                 *, client=None) -> Council:
    """Build the configured council.

    Defaults to the deterministic stub so the whole loop runs with no API key and
    at $0 (CLAUDE.md cost rule). Reads COUNCIL_PROVIDER (stub | claude) and
    COUNCIL_MODEL from the environment when not passed explicitly. The Claude
    provider is imported lazily, so the zero-dependency engine never pulls in the
    Anthropic SDK just by importing this module.

    `client` lets a caller (or a test) inject an LLM transport for the claude
    provider — the path used for $0 offline testing.
    """
    provider = (provider or os.getenv("COUNCIL_PROVIDER", "stub")).strip().lower()
    if provider == "stub":
        return DeterministicStubCouncil()
    if provider == "claude":
        from keystone.claude_council import ClaudeCouncil  # lazy: optional dep
        return ClaudeCouncil(
            model=model or os.getenv("COUNCIL_MODEL", DEFAULT_COUNCIL_MODEL),
            client=client,
        )
    if provider == "consensus":
        # Multi-model consensus (ADR-010): a PRIMARY council (CONSENSUS_PRIMARY, default claude) wrapped
        # with independent voter models (CONSENSUS_VOTERS). Lazy import; stays $0 until env-configured.
        from keystone.consensus import make_consensus_council  # lazy
        prim_provider, _, prim_model = os.getenv("CONSENSUS_PRIMARY", "claude").partition(":")
        primary = make_council(prim_provider.strip() or "claude", prim_model.strip() or None, client=client)
        return make_consensus_council(primary=primary)
    raise ValueError(
        f"Unknown COUNCIL_PROVIDER={provider!r}. Use 'stub', 'claude', or 'consensus'. "
        "(Voter/primary models can be openai | openrouter | ollama via the consensus env config.)"
    )
