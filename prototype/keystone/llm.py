"""Shared LLM transport seam (ADR-001 / ADR-002).

A thin, provider-agnostic interface so the council and the ingestion layer share ONE
testable transport. Inject any object satisfying `LLM` for $0 offline tests; the
default `AnthropicLLM` lazily imports the optional Anthropic SDK so the zero-dependency
engine never pulls it in.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Protocol

from keystone.cost_meter import CostMeter, anthropic_usage, openai_usage
from keystone.rate_limit import RateLimiter

log = logging.getLogger("keystone.llm")

_DEFAULT_MAX_REQUESTS_PER_MINUTE = 30
_DEFAULT_ANTHROPIC_TIMEOUT = 120   # seconds — the SDK's own default is 600s, which lets one slow/
# rate-limited call dominate a ~16-call sequential run; 120s comfortably covers a normal completion
# (including the chairman's 8192-max-token call) while bounding the worst case. Env-tunable, same
# pattern as OLLAMA_TIMEOUT below, for anyone who needs more headroom.


def _default_rate_limiter() -> RateLimiter:
    """One rate limiter per transport instance (a single council/ingestion call reuses one
    instance across all its persona/stage calls). Sized from LLM_MAX_REQUESTS_PER_MINUTE —
    default 30/min comfortably covers one council run (~15 calls: 7 design + 7 review + 1
    chairman) while still throttling a runaway loop hard."""
    max_calls = int(os.getenv("LLM_MAX_REQUESTS_PER_MINUTE", str(_DEFAULT_MAX_REQUESTS_PER_MINUTE)))
    return RateLimiter(max_calls=max_calls, period_seconds=60.0)


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

    def __init__(self, model: str, *, meter: CostMeter | None = None,
                 provider: str = "claude", rate_limiter: RateLimiter | None = None) -> None:
        try:
            import anthropic  # optional dep — only needed for a live provider
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise LLMError(
                "A 'claude' provider needs the Anthropic SDK. "
                "Install it with:  pip install 'keystone[council]'"
            ) from e
        timeout = int(os.getenv("ANTHROPIC_TIMEOUT", str(_DEFAULT_ANTHROPIC_TIMEOUT)))
        self._client = anthropic.Anthropic(timeout=timeout)
        self._model = model
        self._meter = meter          # operational spend telemetry, opt-in (never a product number)
        self._provider = provider
        self._rate_limiter = rate_limiter or _default_rate_limiter()

    def complete(self, *, label: str, system: str, user: str, max_tokens: int) -> str:
        log.debug("llm call [%s] model=%s", label, self._model)
        if self._meter is not None:
            self._meter.check_budget()   # pre-flight spend cap — no-op unless one is configured
        self._rate_limiter.acquire()     # blocks if over the per-minute cap; a runaway-loop backstop
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if self._meter is not None:
            self._meter.record(self._provider, self._model, *anthropic_usage(resp))
        return "".join(b.text for b in resp.content if b.type == "text")


class OpenAICompatibleLLM:
    """OpenAI-compatible `/chat/completions` transport over **stdlib HTTP** — covers OpenAI (ChatGPT),
    OpenRouter (hundreds of models, including free ones), and a local **Ollama** server, which all speak
    the same wire API. `base_url` + the API-key env var select the provider; no SDK dependency
    (stdlib-first, CLAUDE.md). The key is read from the environment and **never logged**.

    Same `LLM` seam as `AnthropicLLM`, so the council/ingestion/consensus layers are provider-agnostic.
    Inject a fake `LLM` for $0 offline tests; this transport only runs when a real provider is selected."""

    def __init__(self, model: str, *, base_url: str, api_key_env: str | None = None, timeout: int = 120,
                 meter: CostMeter | None = None, provider: str | None = None,
                 rate_limiter: RateLimiter | None = None) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = os.getenv(api_key_env) if api_key_env else None
        if api_key_env and not self._api_key:
            raise LLMError(f"{api_key_env} is not set — required for the {base_url} provider.")
        self._timeout = timeout
        self._meter = meter          # operational spend telemetry, opt-in (never a product number)
        self._provider = provider    # telemetry label so a $0 provider (ollama/github/:free) is priced right
        self._rate_limiter = rate_limiter or _default_rate_limiter()

    def complete(self, *, label: str, system: str, user: str, max_tokens: int) -> str:
        log.debug("llm call [%s] model=%s base=%s", label, self._model, self._base_url)
        if self._meter is not None:
            self._meter.check_budget()   # pre-flight spend cap — no-op unless one is configured
        self._rate_limiter.acquire()     # blocks if over the per-minute cap; a runaway-loop backstop
        body = json.dumps({
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"   # never logged
        req = urllib.request.Request(f"{self._base_url}/chat/completions", data=body,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:   # noqa: S310 (https only by config)
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:   # transport/HTTP/JSON failure — fail loud, never silently empty
            raise LLMError(f"{label}: {self._base_url} call failed: {e}") from e
        if self._meter is not None:
            self._meter.record(self._provider, self._model, *openai_usage(data))
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"{label}: unexpected response shape from {self._base_url}") from e


# Provider registry for the OpenAI-compatible transport: name -> (base_url | None, api_key_env | None).
# Ollama's base comes from OLLAMA_BASE_URL (local, no key); the rest are hosted + keyed. Every base URL
# below is verified against the provider's own OpenAI-compatibility docs (the transport appends
# `/chat/completions`). Providers with a genuine FREE tier — Gemini (AI Studio, no card), Groq,
# Cerebras, GitHub Models (free with a GitHub PAT), xAI (Grok, console credits) — let a free key drive
# the real council at $0 (ADR-010 vendor-neutrality; the prime-directive guard runs on every vendor).
# Note: GitHub Models uses a GitHub PAT (scope `models:read`) as the bearer token; model ids are
# `publisher/model` (e.g. openai/gpt-4.1). xAI models are grok-3 / grok-2 etc.
_OPENAI_COMPATIBLE = {
    "openai":     ("https://api.openai.com/v1",   "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "groq":       ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "cerebras":   ("https://api.cerebras.ai/v1",  "CEREBRAS_API_KEY"),
    "xai":        ("https://api.x.ai/v1",         "XAI_API_KEY"),
    "github":     ("https://models.github.ai/inference", "GITHUB_MODELS_TOKEN"),
    "ollama":     (None,                           None),
}


def known_providers() -> frozenset:
    """Every provider name `make_llm` accepts — one source of truth so callers (e.g. the council
    factory) can validate a provider up front and give a clear 'unknown provider' error."""
    return frozenset({"claude", "anthropic"} | set(_OPENAI_COMPATIBLE))


def make_llm(provider: str, model: str, *, meter: CostMeter | None = None) -> LLM:
    """Build an `LLM` transport by provider name (lazy; the engine never imports any of these):
    `claude`/`anthropic` → `AnthropicLLM` (SDK); every other registered provider (openai | openrouter |
    gemini | groq | cerebras | xai | github | ollama) → `OpenAICompatibleLLM` (stdlib HTTP). Used by the
    council factory + the multi-model consensus layer. An optional `meter` records this transport's
    token-usage as Keystone's own API spend (opt-in telemetry — never a product number)."""
    p = provider.strip().lower()
    if p in ("claude", "anthropic"):
        return AnthropicLLM(model, meter=meter, provider=p)
    if p == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        # Local inference (CPU/Metal) is far slower than a hosted API — one big generation (e.g. the
        # peer-review stage over 7 proposals) can exceed the 120s default and time out mid-council.
        # Give Ollama a longer, env-tunable timeout so a full local run completes.
        return OpenAICompatibleLLM(model, base_url=base, api_key_env=None,
                                   timeout=int(os.getenv("OLLAMA_TIMEOUT", "600")),
                                   meter=meter, provider=p)
    if p in _OPENAI_COMPATIBLE:
        base, key_env = _OPENAI_COMPATIBLE[p]
        return OpenAICompatibleLLM(model, base_url=base, api_key_env=key_env, meter=meter, provider=p)
    raise LLMError(f"unknown LLM provider {provider!r} (expected: claude | openai | openrouter | "
                   "gemini | groq | cerebras | xai | github | ollama)")
