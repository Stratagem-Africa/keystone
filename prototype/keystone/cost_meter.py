"""Operational API-cost telemetry — what KEYSTONE spends to run a live council.

⚠️ SCOPE / PRIME-DIRECTIVE BOUNDARY. This module measures **Keystone's own LLM
inference spend** — the dollars we pay a provider to run the council — from the
providers' returned token-usage. It is *operational telemetry about our own infra*,
NOT a product metric: it never enters a `SimulationResult`, never appears in a
user-facing architecture report, and has nothing to do with the *user's system's*
cost. That number (`monthly_cost`) is produced solely by `simulation.py`. Keeping
the two apart is the same separation the prime directive protects — do not surface
this in the honesty report or let it touch a `Metric`.

No LLM is involved: token counts come from the provider response `usage` field, and
prices are a static, dated, cited snapshot. Money is integer **micro-USD (µUSD)** —
cents are too coarse for token-level costs — honouring the harm-floor
integer-minor-unit rule (ADR-008); only the final display is formatted as a float.
Unknown models are FLAGGED, never priced at a fake $0 (honesty): the meter reports
what it can prove and names what it cannot.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_MICRO = 1_000_000            # 1 USD = 1_000_000 µUSD
_SNAPSHOT = "2026-07"         # pricing snapshot date (extend rows WITH a cited source)

# List price, integer µUSD per 1,000,000 tokens: model id -> (input, output).
# These are LIST prices for ESTIMATION only — verify against your invoice. Keyed on
# the exact model id the transport sends (OpenAICompatibleLLM/AnthropicLLM `_model`).
# Extend the same way we grow the grounding corpus: one cited source per row.
_LIST_PRICES: dict[str, tuple[int, int]] = {
    # Moonshot Kimi line — OpenRouter public pricing, snapshot 2026-07
    # https://openrouter.ai/moonshotai
    "moonshotai/kimi-k3":          (3_000_000, 15_000_000),
    "moonshotai/kimi-k2.7-code":   (  720_000,  3_500_000),
    "moonshotai/kimi-k2.6":        (  660_000,  3_410_000),
    "moonshotai/kimi-k2.5":        (  375_000,  2_025_000),
    "moonshotai/kimi-k2-thinking": (  600_000,  2_500_000),
    "moonshotai/kimi-k2-0905":     (  600_000,  2_500_000),
    "moonshotai/kimi-k2":          (  570_000,  2_300_000),
    # Anthropic — the DEFAULT council model (.env.example COUNCIL_MODEL / CONSENSUS_PRIMARY),
    # so the common path prices honestly instead of reading a fake $0. Standard API list price
    # $1/M in · $5/M out, snapshot 2026-07 (anthropic.com/pricing; corroborated). Batch/cache
    # discounts NOT modelled — AnthropicLLM sends no cache_control today (see anthropic_usage).
    "claude-haiku-4-5-20251001":   (1_000_000,  5_000_000),
    # Other OpenAI/Gemini/etc. list prices intentionally OMITTED until a cited snapshot exists —
    # an un-cited price would be an invented number (honesty charter). Such a model is reported
    # "unpriced (cost unknown)", never $0.
}

# Genuinely-zero-cost paths (recognised as $0, NOT "unknown"):
#   - provider 'ollama'  : local inference, no API charge
#   - provider 'github'  : GitHub Models free tier (snapshot 2026-07)
#   - model id '…:free'  : OpenRouter free-tier slug
_FREE_PROVIDERS = frozenset({"ollama", "github"})


def _price(provider: str | None, model: str) -> tuple[int, int] | None:
    """Resolve (input_µUSD_per_M, output_µUSD_per_M) for a call, or None if the price
    is genuinely unknown. Known-zero paths return (0, 0) — an honest zero, distinct
    from an unknown one."""
    p = (provider or "").strip().lower()
    if p in _FREE_PROVIDERS:
        return (0, 0)
    if str(model).strip().lower().endswith(":free"):
        return (0, 0)
    return _LIST_PRICES.get(model)


def _int_or_none(v: object) -> int | None:
    """A non-negative token count, or None (missing/garbage usage — never faked to 0)."""
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if v >= 0 else None


@dataclass(frozen=True)
class _Call:
    provider: str | None
    model: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass
class CostMeter:
    """Accumulates provider token-usage across one run and prices it deterministically.

    Opt-in: a transport records into it only when one is injected, so an un-metered or
    stub run leaves it empty (`summary()` == "$0, no live calls"). Thread-unaware —
    build one per run; the council calls are sequential."""
    calls: list[_Call] = field(default_factory=list)

    def record(self, provider: str | None, model: str,
               input_tokens: object, output_tokens: object) -> None:
        self.calls.append(_Call(provider, str(model),
                                _int_or_none(input_tokens), _int_or_none(output_tokens)))

    def total_micro_usd(self) -> int:
        """Integer µUSD over calls with a KNOWN price and PRESENT usage. Round-half-up,
        pure-integer (harm floor). Unknown-model calls are EXCLUDED (and surfaced via
        `unpriced_models`), never silently counted as $0."""
        total = 0
        for c in self.calls:
            price = _price(c.provider, c.model)
            if price is None:
                continue
            in_micro, out_micro = price
            if c.input_tokens:
                total += (c.input_tokens * in_micro + _MICRO // 2) // _MICRO
            if c.output_tokens:
                total += (c.output_tokens * out_micro + _MICRO // 2) // _MICRO
        return total

    @property
    def unpriced_models(self) -> set[str]:
        """Models whose price we cannot prove — reported as unknown, not zero."""
        return {c.model for c in self.calls if _price(c.provider, c.model) is None}

    @property
    def calls_missing_usage(self) -> int:
        """Calls where the provider returned no token usage (cost uncountable)."""
        return sum(1 for c in self.calls
                   if c.input_tokens is None and c.output_tokens is None)

    def total_tokens(self) -> tuple[int, int]:
        return (sum(c.input_tokens or 0 for c in self.calls),
                sum(c.output_tokens or 0 for c in self.calls))

    def summary(self) -> str:
        """One honest human line for the run console/log. Never presents a precise dollar
        figure as if COMPLETE when some calls are unpriced — a partial/floor is marked `≥`
        (or "not fully priceable" when nothing priced), so an unpriced paid model can never
        be read as a fake $0. Carries the snapshot and names anything it could not price or
        count. The $0 of a hosted free tier is itself a dated assumption (see `_SNAPSHOT`)."""
        if not self.calls:
            return "Keystone API spend: no live LLM calls (stub / offline) — $0.00"
        priced_micro = self.total_micro_usd()
        usd = priced_micro / _MICRO                    # display-only float formatting
        tin, tout = self.total_tokens()
        unpriced = sorted(self.unpriced_models)
        if unpriced and priced_micro == 0:
            head = "Keystone API spend: not fully priceable (0 priced calls)"
        elif unpriced:
            head = f"Keystone API spend ≥ ${usd:.4f} (PARTIAL — priced calls only)"
        else:
            head = f"Keystone API spend ≈ ${usd:.4f}"
        parts = [f"{head} (list/free-tier prices, snapshot {_SNAPSHOT})",
                 f"{len(self.calls)} call(s) · {tin:,} in / {tout:,} out tokens"]
        if unpriced:
            parts.append("unpriced, cost unknown: " + ", ".join(unpriced))
        if self.calls_missing_usage:
            parts.append(f"{self.calls_missing_usage} call(s) returned no usage")
        return " · ".join(parts)


def openai_usage(data: object) -> tuple[int | None, int | None]:
    """(prompt, completion) token counts from an OpenAI-compatible `/chat/completions`
    response body, defensively (usage may be absent/partial on some providers)."""
    u = data.get("usage") if isinstance(data, dict) else None
    u = u if isinstance(u, dict) else {}
    return _int_or_none(u.get("prompt_tokens")), _int_or_none(u.get("completion_tokens"))


def anthropic_usage(resp: object) -> tuple[int | None, int | None]:
    """(input, output) token counts from an Anthropic SDK message response.

    Reads `input_tokens`/`output_tokens` only — exact today because `AnthropicLLM.complete`
    sends no `cache_control`, so `input_tokens` is the full billed input. If prompt caching
    is ever enabled, add the `cache_read_input_tokens`/`cache_creation_input_tokens` dimensions
    here (billed at different rates) so the meter stays honest."""
    u = getattr(resp, "usage", None)
    return _int_or_none(getattr(u, "input_tokens", None)), _int_or_none(getattr(u, "output_tokens", None))
