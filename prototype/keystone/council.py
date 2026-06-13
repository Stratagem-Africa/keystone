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

from dataclasses import dataclass, field
from typing import Protocol

from keystone.model import SystemModel


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
