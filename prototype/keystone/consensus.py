"""Multi-model consensus layer (ADR-010; Doc 02 §4 "grounded consensus of AI architects").

Runs the council on a PRIMARY model (the full 3-stage / 7-persona design), then polls N INDEPENDENT
models (different vendors — Claude, OpenAI/ChatGPT, OpenRouter, local Ollama) to VOTE on each synthesized
ADR. Where the models AGREE, the decision is corroborated across vendors; where they DISAGREE, the dissent
is surfaced in the report — never hidden (Doc 03 §6). This is the cross-vendor trust signal the product is
named for.

Prime directive (CLAUDE.md, Doc 03 §2): every model REASONS about design, never produces a number. The
voters carry the same `_NO_NUMBERS_RULE` prompt, and **every vote's free text is run through the same
`_redact_engine_metrics` guard** before it reaches an ADR — so no model (Claude, GPT, or Llama) can leak a
figure into a report. A voter that errors is skipped (best-effort overlay); the primary ADRs always stand.

Cost: the primary runs one full council; each voter casts ONE batched vote over all ADRs — so the cross-
check is cheap, and can use free OpenRouter models or a local Ollama for $0. Stub-default: `make_council`
returns the deterministic stub unless `COUNCIL_PROVIDER` is set, so this stays offline/$0 until activated.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass

from keystone.claude_council import _NO_NUMBERS_RULE, _extract_json, _redact_engine_metrics
from keystone.cost_meter import CostMeter
from keystone.council import ADR, Council
from keystone.llm import LLM, make_llm
from keystone.model import SystemModel

log = logging.getLogger("keystone.consensus")

_VERDICTS = ("AGREE", "CAVEAT", "DISAGREE")


@dataclass(frozen=True)
class Voter:
    """One independent cross-check model: a human label (e.g. "openai gpt-5-mini") + its LLM transport."""
    label: str
    llm: LLM


class ConsensusCouncil:
    """Wraps a primary `Council` with a panel of independent voter models. Satisfies the `Council`
    protocol (`design(model) -> list[ADR]`), so it is a drop-in for the stub/Claude council."""

    def __init__(self, primary: Council, voters: list[Voter]) -> None:
        self._primary = primary
        self._voters = voters

    def design(self, model: SystemModel) -> list[ADR]:
        adrs = self._primary.design(model)
        if not self._voters or not adrs:
            return adrs
        ballots = {}   # voter label -> {presented_index(1-based) -> (verdict, scrubbed_reason)}
        for v in self._voters:
            try:
                ballots[v.label] = self._poll(v, model, adrs)
            except Exception as e:   # a flaky/unavailable voter must not kill the design (best-effort)
                log.warning("consensus voter %r unavailable: %s", v.label, e)
                ballots[v.label] = {}
        return [dataclasses.replace(adr, consensus=self._tally(i + 1, ballots))
                for i, adr in enumerate(adrs)]

    # -- internals ---------------------------------------------------------- #

    def _tally(self, presented_index: int, ballots: dict) -> list[str]:
        """Build the rendered consensus lines for one ADR: a summary + one line per voter that voted."""
        lines, agree, total = [], 0, 0
        for label, votes in ballots.items():
            vote = votes.get(presented_index)
            if vote is None:
                continue
            verdict, reason = vote
            total += 1
            if verdict == "AGREE":
                agree += 1
            lines.append(f"{label}: {verdict}" + (f" — {reason}" if reason else ""))
        if not total:
            return []
        tail = "" if agree == total else " (dissent recorded)"
        return [f"Cross-model consensus: {agree}/{total} models agree{tail}"] + lines

    def _poll(self, voter: Voter, model: SystemModel, adrs: list[ADR]) -> dict:
        """One batched call: the voter votes on every ADR. Reasons are guard-scrubbed (prime directive)."""
        system = (
            "You are an independent senior software architect from a DIFFERENT vendor, doing a cross-model "
            "consensus check on another council's decisions. For EACH decision vote AGREE, CAVEAT (agree "
            "with a reservation), or DISAGREE, with a single-line reason judged on merit.\n" + _NO_NUMBERS_RULE
        )
        listing = "\n".join(f"[{i}] {a.area}: {a.decision}" for i, a in enumerate(adrs, 1))
        user = (
            f"SYSTEM: {model.name} — {model.workload.description}\n\nDECISIONS:\n{listing}\n\n"
            "Reply with ONLY a JSON array, one item per decision:\n"
            '{"index": <the [n]>, "verdict": "AGREE|CAVEAT|DISAGREE", "reason": "<one line>"}'
        )
        raw = voter.llm.complete(label=f"consensus:{voter.label}", system=system, user=user, max_tokens=4096)
        items = _extract_json(raw, expect="array")
        out: dict = {}
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            try:
                idx = int(it.get("index"))
            except (TypeError, ValueError):
                continue
            verdict = str(it.get("verdict", "")).strip().upper()
            if verdict not in _VERDICTS:
                verdict = "CAVEAT"
            # Guard (prime directive) THEN single-line + bound the reason — a voter's free text reaches a
            # markdown report, so strip newlines/sentinels and cap length (defence-in-depth, like Citation).
            reason, _ = _redact_engine_metrics(str(it.get("reason", "")).strip())
            reason = reason.replace("\n", " ").replace("\r", " ").replace("`", "'")[:300]
            out[idx] = (verdict, reason)
        return out


def _voters_from_spec(spec: str, *, meter: CostMeter | None = None) -> list[Voter]:
    """Parse CONSENSUS_VOTERS ('provider:model, provider:model, …') into voter transports. Split on the
    FIRST ':' so model names that contain ':' (e.g. openrouter '…llama-3.1:free') survive. An optional
    `meter` records each voter's own API spend (opt-in telemetry — never a product number)."""
    voters: list[Voter] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw or ":" not in raw:
            continue
        provider, model = (s.strip() for s in raw.split(":", 1))
        voters.append(Voter(label=f"{provider} {model}", llm=make_llm(provider, model, meter=meter)))
    return voters


def make_consensus_council(*, primary: Council, voters: list[Voter] | None = None,
                           meter: CostMeter | None = None) -> ConsensusCouncil:
    """Build a consensus council. `voters` defaults to the `CONSENSUS_VOTERS` env spec
    ('openai:gpt-5-mini, openrouter:meta-llama/llama-3.1-8b-instruct:free, ollama:llama3'). A caller (or
    test) can inject fake voters for $0 offline runs. `meter` is threaded to env-built voters only —
    injected voters own their own metering."""
    if voters is None:
        voters = _voters_from_spec(os.getenv("CONSENSUS_VOTERS", ""), meter=meter)
    return ConsensusCouncil(primary=primary, voters=voters)
