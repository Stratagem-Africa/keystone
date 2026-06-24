"""Knowledge Base / grounding layer (ADR-006) — capacities → evidence.

The L0→L1 lever: attaches **resolvable evidence** to an input value (a component's service
rate, a cost) so it can move ASSUMPTION → GROUNDED. The honesty contract + the evidence types
live in `provenance.py`; this module is the **seam**: the `KnowledgeBase` interface, the
stub-default `EmptyKnowledgeBase` (grounds nothing — the honest L0 state), and the env-driven
factory. The `curated` provider (a cited JSONL benchmark corpus) lives in
`benchmarks/benchmark_corpus.py` and is loaded lazily; `rag` (pgvector) is a future ADR.

Prime directive (ADR-002 boundary): the KB grounds **inputs** only, never a derived metric —
the engine (simulation.py) remains the sole producer of those.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from keystone.model import ComponentKind
# Re-exported so callers can `from keystone.knowledge_base import Grounding, Citation`.
from keystone.provenance import (  # noqa: F401
    GROUNDABLE_METRICS, Citation, Grounding, require_groundable_metric,
)


@runtime_checkable
class KnowledgeBase(Protocol):
    """Grounds an INPUT value for a component kind + metric, or returns None if there is
    no evidence. Never returns a derived metric (prime directive)."""
    def ground(self, kind: ComponentKind, metric: str, *,
               context: dict | None = None) -> Grounding | None: ...


class EmptyKnowledgeBase:
    """Default stub: no curated data, so it grounds NOTHING — every value honestly stays
    ASSUMPTION. Deterministic, $0, offline (CLAUDE.md cost rule)."""
    def ground(self, kind: ComponentKind, metric: str, *,
               context: dict | None = None) -> Grounding | None:
        require_groundable_metric(metric)   # reject derived-metric requests at the seam (prime directive)
        return None


_KNOWN_PROVIDERS = ("stub", "curated", "rag")


def make_knowledge_base(provider: str | None = None) -> KnowledgeBase:
    """Env-driven factory (`KB_PROVIDER`), default 'stub'.

    - `stub`    → `EmptyKnowledgeBase` (grounds nothing).
    - `curated` → `CuratedKnowledgeBase` over the cited JSONL corpus (grounds nothing until a
                  corpus is curated + a human review gate passes; activation is a Bifola trigger).
    - `rag`     → gated (future ADR).
    """
    # Treat unset OR set-but-empty/whitespace KB_PROVIDER as the stub default (a `export KB_PROVIDER=`
    # or empty CI secret must not crash the run — keeps the default-off/$0/offline promise).
    provider = (provider or os.getenv("KB_PROVIDER") or "stub").strip().lower() or "stub"
    if provider not in _KNOWN_PROVIDERS:
        raise ValueError(f"unknown KB provider {provider!r} (expected one of {_KNOWN_PROVIDERS})")
    if provider == "stub":
        return EmptyKnowledgeBase()
    if provider == "curated":
        from keystone.benchmarks.benchmark_corpus import CuratedKnowledgeBase  # lazy: avoids a cycle
        return CuratedKnowledgeBase.from_default_corpus()
    raise NotImplementedError(
        f"KB provider {provider!r} is not built yet (ADR-006: rag is a future ADR). "
        "The stub grounds nothing; RAG retrieval awaits a corpus worth retrieving over.")
