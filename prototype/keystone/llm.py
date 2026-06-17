"""Shared LLM transport seam (ADR-001 / ADR-002).

A thin, provider-agnostic interface so the council and the ingestion layer share ONE
testable transport. Inject any object satisfying `LLM` for $0 offline tests; the
default `AnthropicLLM` lazily imports the optional Anthropic SDK so the zero-dependency
engine never pulls it in.
"""
from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("keystone.llm")


class LLMError(RuntimeError):
    """Transport-level failure (e.g. the optional SDK is not installed)."""


class LLM(Protocol):
    """One blocking completion. `label` is for logging/observability only."""
    def complete(self, *, label: str, system: str, user: str, max_tokens: int) -> str:
        ...


class AnthropicLLM:
    """Default transport: a single Claude model via the official Anthropic SDK.

    Reads ANTHROPIC_API_KEY from the environment (per the SDK's default credential
    resolution). `thinking`/`effort` are intentionally omitted so the same call works
    across the configurable model set. The SDK is an OPTIONAL dependency
    (`pip install 'keystone[council]'`), imported lazily so the zero-dependency engine
    never pulls it in. The API key is never logged."""

    def __init__(self, model: str) -> None:
        try:
            import anthropic  # optional dep — only needed for a live provider
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise LLMError(
                "A 'claude' provider needs the Anthropic SDK. "
                "Install it with:  pip install 'keystone[council]'"
            ) from e
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, *, label: str, system: str, user: str, max_tokens: int) -> str:
        log.debug("llm call [%s] model=%s", label, self._model)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")
