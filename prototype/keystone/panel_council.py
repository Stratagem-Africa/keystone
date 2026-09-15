"""`claude_panel` — run Keystone's seven personas as subagents INSIDE one Claude Code call.

Two decks of deliberation, and Keystone's governance sitting over both.

    deck 1   seven Keystone personas debate as Claude Code SUBAGENTS, in one call
    deck 2   (optional) COUNCIL_PROVIDER=consensus adds independent voter MODELS on top
    -------  ------------------------------------------------------------------------
    always   the prime-directive guard, the provenance stamp, the ADR schema

**Why this exists, beyond novelty.** `ClaudeCouncil` issues one LLM call per persona. On the CLI
transport each call boots a whole Claude Code session, so the measured council run was
**11 ADRs in 1559s** — most of it session start-up, repeated seven times. Claude Code can run
subagents itself, so passing Keystone's own personas via `--agents` collapses that into a single
call in which the personas still deliberate independently. Same seven viewpoints, one session.

**The personas are Keystone's, not Claude Code's.** `PERSONAS` and `_NO_NUMBERS_RULE` are imported
from `claude_council`, so the panel cannot drift from the council: add a persona there and it appears
here, with the no-numbers rule already attached to each agent's own prompt.

**Governance is unchanged and non-optional.** Whatever the panel returns is parsed into the same
`ADR` dataclass and passed through the same `_scrub_adr`, so a figure invented inside a subagent is
redacted exactly as one invented by a single model would be — and the redaction is disclosed in the
ADR rather than applied silently. A second deck of reasoning does not get a weaker guard.

**What it does NOT do.** Subagents inside one session are not independent MODELS; they share a
provider, a context and a moment in time, so their agreement is weaker evidence than ADR-010's
cross-vendor consensus. That is why this is deck 1 and not a replacement for deck 2, and why
`consensus_note` says so on every ADR it produces.
"""
from __future__ import annotations

import dataclasses
import json

from .claude_council import (
    PERSONAS, _NO_NUMBERS_RULE, _extract_json, _scrub_adr,
)
from .council import ADR
from .llm_cli import ClaudeCliLLM
from .llm import LLMError
from .model import SystemModel

__all__ = ["PanelCouncil", "build_agents_payload", "PANEL_CAVEAT"]

PANEL_CAVEAT = (
    "Produced by a PANEL of personas inside a single Claude Code session. They deliberate "
    "independently but share one provider, one context window and one moment — so agreement here is "
    "weaker evidence than cross-vendor consensus (ADR-010). Treat unanimity as 'no one in the room "
    "objected', not as corroboration."
)


def build_agents_payload(personas=PERSONAS) -> str:
    """Keystone's personas as a Claude Code `--agents` JSON object.

    Each agent carries its OWN copy of the no-numbers rule. Putting it only in the outer prompt
    would leave each subagent free to invent a figure that the outer turn then repeats — the rule
    has to travel with the persona that might break it.
    """
    return json.dumps({
        p.key: {
            "description": p.title,
            "prompt": (
                f"You are the {p.title} on an architecture review panel. "
                f"Your remit is strictly: {p.brief}. "
                f"Argue your own corner. Disagree with the other panellists where you genuinely "
                f"disagree — a panel that never dissents has told the reader nothing.\n"
                f"{_NO_NUMBERS_RULE}"
            ),
        }
        for p in personas
    })


_PANEL_INSTRUCTION = (
    "Convene the panel. Ask EVERY agent listed above for its position on this system, then write the "
    "panel's decisions.\n\n"
    "Return ONLY a JSON array. Each element is one architectural decision:\n"
    '  {"area": "...", "decision": "...", "rationale": "...", '
    '"dissent": ["..."], "confidence": "low|med|high", "kill_criteria": ["..."]}\n\n'
    "Rules:\n"
    "- One element per genuinely distinct decision. Six to twelve is the useful range.\n"
    "- `dissent` MUST carry any panellist who disagreed, in their words. An empty dissent array on a "
    "contested call is a failure — never hide disagreement.\n"
    "- `kill_criteria` are the observable conditions that would prove the decision wrong.\n"
    "- No numbers anywhere. No throughput, latency, cost or utilisation figures.\n"
    "Output the JSON array and nothing else."
)


class PanelCouncil:
    """A `Council` that runs Keystone's personas as subagents in one Claude Code call."""

    def __init__(self, *, transport: ClaudeCliLLM | None = None, model: str = "",
                 meter=None, source: str | None = None) -> None:
        self._llm = transport or ClaudeCliLLM(model or None, meter=meter)
        self.source = source or f"claude_panel:{model or 'default'}"

    def design(self, model: SystemModel) -> list[ADR]:
        from .claude_council import _model_brief          # lazy: keeps the import graph flat

        raw = self._llm.complete(
            label="panel:design",
            system="You chair an architecture review panel. You never produce numbers yourself; the "
                   "deterministic engine owns every figure.",
            user=f"{_model_brief(model)}\n\n{_PANEL_INSTRUCTION}",
            max_tokens=8192,
            agents=build_agents_payload(),
        )

        items = _extract_json(raw, expect="array")
        if not isinstance(items, list):
            raise LLMError("panel did not return a JSON array of decisions")

        adrs: list[ADR] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            adr = ADR(
                area=str(item.get("area", "")).strip() or "unspecified",
                decision=str(item.get("decision", "")).strip(),
                rationale=str(item.get("rationale", "")).strip(),
                dissent=tuple(str(d) for d in (item.get("dissent") or [])),
                confidence=(str(item.get("confidence", "med")).strip().lower()
                            if str(item.get("confidence", "")).strip().lower()
                            in ("low", "med", "high") else "med"),
                kill_criteria=tuple(str(k) for k in (item.get("kill_criteria") or [])),
                source=self.source,
            )
            # Same guard as every other council path — a panel does not earn a weaker one.
            adr = _scrub_adr(adr, source=self.source)
            # Say what the panel's agreement is and is not worth, on every ADR it produces.
            adrs.append(dataclasses.replace(adr, consensus=PANEL_CAVEAT))

        if not adrs:
            raise LLMError("panel returned no usable decisions")
        return adrs
