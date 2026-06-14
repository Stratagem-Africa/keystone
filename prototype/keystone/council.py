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
        # High-stakes guard (Doc 03 §6): never imply production-safety for flagged domains.
        if any(f.startswith("high_stakes") for f in model.domain_flags):
            adrs.append(ADR(
                area="Review gate",
                decision="REQUIRES expert/legal/security review before any production use.",
                rationale="Domain flagged high-stakes; Keystone does not certify safety.",
                confidence="high",
                kill_criteria=["Shipped without independent expert sign-off"],
            ))
        return adrs


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
    raise ValueError(
        f"Unknown COUNCIL_PROVIDER={provider!r}. Use 'stub' or 'claude'. "
        "(openrouter/ollama are a documented v2 lever, not yet built — Doc 02 §4.)"
    )
