"""Real Claude consensus council (Doc 04 F4, Doc 02 §4).

Implements the `Council` interface (`design(model) -> list[ADR]`) with the
three-stage consensus pattern, run as ONE Claude model wearing multiple persona
system-prompts for cost control (Doc 02 §4):

    1. Independent design   — each persona proposes in its area, blind to the others.
    2. Blind peer review    — each persona critiques the ANONYMISED proposal set
                              (identities stripped to reduce herding, Doc 04 F4).
    3. Chairman synthesis   — converges to one ADR per decision area, carrying
                              named dissent, confidence, and kill criteria.

Prime directive (CLAUDE.md, Doc 03 §2): the LLM REASONS; it never produces a
metric. These prompts forbid throughput/latency/cost figures, and a defence-in-
depth guard (`_redact_engine_metrics`) scrubs any that leak through before they
reach an ADR. The deterministic engine (`simulation.py`) owns every number.

The Anthropic SDK is an OPTIONAL dependency (`pip install 'keystone[council]'`);
it is imported lazily so the zero-dependency engine never pulls it in. For tests
and $0 offline runs, inject any object satisfying the `LLM` protocol via `client=`.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

from keystone.council import ADR
from keystone.model import SystemModel

log = logging.getLogger("keystone.council")


class CouncilError(RuntimeError):
    """Raised when the council cannot produce a usable result (parse/transport)."""


# --------------------------------------------------------------------------- #
# LLM transport — a thin seam so the council is provider-agnostic and testable
# --------------------------------------------------------------------------- #

class LLM(Protocol):
    """One blocking completion. `label` is for logging/observability only."""
    def complete(self, *, label: str, system: str, user: str, max_tokens: int) -> str:
        ...


class AnthropicLLM:
    """Default transport: a single Claude model via the official Anthropic SDK.

    Reads ANTHROPIC_API_KEY from the environment (per the SDK's default
    credential resolution). `thinking`/`effort` are intentionally omitted so the
    same call works across the configurable model set — `effort` 400s on Haiku
    4.5 and adaptive thinking is a 4.6+ mode. Enabling adaptive thinking for
    Opus-tier councils is a deliberate future enhancement (ADR territory)."""

    def __init__(self, model: str) -> None:
        try:
            import anthropic  # optional dep — only needed for the real council
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise CouncilError(
                "The 'claude' council provider needs the Anthropic SDK. "
                "Install it with:  pip install 'keystone[council]'"
            ) from e
        self._client = anthropic.Anthropic()
        self._model = model

    def complete(self, *, label: str, system: str, user: str, max_tokens: int) -> str:
        log.debug("council call [%s] model=%s", label, self._model)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


# --------------------------------------------------------------------------- #
# Personas — one Claude model, many system-prompts (Doc 02 §4)
# --------------------------------------------------------------------------- #

# The prime-directive contract, appended to EVERY persona + the chairman.
_NO_NUMBERS_RULE = (
    "HARD RULE — you reason about design only. You MUST NOT state any throughput, "
    "latency, capacity, or cost figure (no rps/qps, no ms/seconds, no $/month). A "
    "separate deterministic engine owns every number; inventing one is a critical "
    "violation. Describe trade-offs qualitatively (e.g. 'the cache shields the "
    "primary from the read storm'), never quantitatively. Ratios and counts that "
    "are design choices (a 90/10 read:write split, 'shard into 4') are fine; "
    "performance/cost magnitudes are not."
)


@dataclass(frozen=True)
class Persona:
    key: str
    title: str
    brief: str  # what this persona is responsible for


PERSONAS: tuple[Persona, ...] = (
    Persona("backend", "Backend / application architect",
            "service decomposition, API style, component communication, statefulness"),
    Persona("data", "Data engineer",
            "datastore choice, schema/partitioning, consistency model, read/write paths"),
    Persona("security", "Security & privacy engineer",
            "authN/authZ, tenant isolation, data-at-rest/in-transit, attack surface"),
    Persona("sre", "Site reliability engineer",
            "single points of failure, failover, stampede/back-pressure, operability"),
    Persona("finops", "Cloud / FinOps architect",
            "managed-vs-self-hosted, right-sizing posture, cost drivers (qualitatively)"),
    Persona("ai", "AI-infusion specialist",
            "where ML genuinely helps AND where it must NOT go (money/vote/safety paths)"),
    Persona("yagni", "YAGNI skeptic",
            "challenge premature scale, over-engineering, and unjustified complexity"),
)

_CHAIRMAN_SYSTEM = (
    "You are the chairman of an architecture council. You receive independent "
    "design proposals and a round of blind peer review, and you converge them "
    "into Architecture Decision Records — one per distinct decision area. You do "
    "NOT invent new positions; you reconcile what the council produced, preserving "
    "minority views as named dissent rather than synthesising them away "
    "(Doc 03 §6 — never hide dissent).\n" + _NO_NUMBERS_RULE
)


# --------------------------------------------------------------------------- #
# Prime-directive guard — scrub any engine-owned metric the LLM leaks
# --------------------------------------------------------------------------- #

# Unit-anchored on purpose: these match a number ONLY when bound to a
# performance/cost unit, so legitimate design language ("30% of traffic",
# "99:1 read:write", "shard into 4", "t4g.medium x12") is left untouched.
#
# `_NUM` carries an optional thousands separator, decimal, AND magnitude
# multiplier (k/M/G/B/T) — because an LLM writes "8k rps" and "$2.5k/mo", not
# just "8000 rps". `_PERIOD` is ordered longest-first ("month" before "mo") so a
# match never strands a suffix like "nth". Deliberately NOT matched, to avoid
# corrupting valid prose: bare single-letter time units (a "30s" TTL, "1.2s"),
# bare "us" (a "us-east" region), and "minute(s)" (a cron interval / RTO target).
# The prompt-level rule still forbids those; this guard is defence-in-depth.
_NUM = r"\d[\d,]*(?:\.\d+)?\s?[kmgbt]?\s?"
_PERIOD = r"(?:months?|years?|hours?|days?|mo|hr|yr)"

_METRIC_PATTERNS = (
    re.compile(rf"[$€£]\s?{_NUM}(?:(?:/|per)\s?{_PERIOD})?", re.I),    # leading currency symbol
    re.compile(rf"\b{_NUM}\$", re.I),                                  # trailing "$" (e.g. "500$")
    re.compile(rf"\b{_NUM}(?:usd|dollars?|cents?)\b", re.I),           # spelled-out currency
    re.compile(rf"\b{_NUM}(?:rps|qps|tps|req/s|reqs?/s|requests?\s?/\s?s|requests?\s+per\s+second)\b", re.I),
    re.compile(rf"\b{_NUM}(?:milliseconds?|millis|msec|ms|microseconds?|µs|nanoseconds?|nsec|ns|seconds?|secs?)\b", re.I),
)

_REDACTION = "[engine-owned metric removed]"


def _redact_engine_metrics(text: str) -> tuple[str, int]:
    """Replace any performance/cost magnitude with a neutral marker.

    Returns (clean_text, count). The prime directive forbids the council from
    producing numbers; rather than crash the loop on a stray figure, we redact
    it and flag the ADR (transparency, Doc 03 §2). Never silently passes through."""
    count = 0
    out = text
    for pat in _METRIC_PATTERNS:
        out, n = pat.subn(_REDACTION, out)
        count += n
    return out, count


def _scrub_adr(adr: ADR) -> ADR:
    """Apply the guard across every free-text field of an ADR; flag if it fired.

    `area` is included: report.py renders it verbatim as a section header, so an
    LLM-embedded figure there ('Caching (8k rps tier)') would bypass the guard at
    the most prominent point in the report. `confidence` is the only text field
    left untouched — it is already constrained to the low/med/high enum upstream."""
    hits = 0
    area, n = _redact_engine_metrics(adr.area);          hits += n
    decision, n = _redact_engine_metrics(adr.decision);  hits += n
    rationale, n = _redact_engine_metrics(adr.rationale); hits += n
    dissent = []
    for d in adr.dissent:
        d2, n = _redact_engine_metrics(d); hits += n; dissent.append(d2)
    kill = []
    for k in adr.kill_criteria:
        k2, n = _redact_engine_metrics(k); hits += n; kill.append(k2)
    if hits:
        log.warning("council emitted %d engine-owned metric(s) in ADR %r; redacted", hits, area)
        rationale += (
            " [Prime-directive guard: the council emitted a performance/cost figure; "
            "it was removed. All numbers come from the deterministic engine.]"
        )
    return ADR(
        area=area, decision=decision, rationale=rationale, dissent=dissent,
        confidence=adr.confidence, kill_criteria=kill, source="claude",
    )


# --------------------------------------------------------------------------- #
# Model serialisation + tolerant JSON parsing
# --------------------------------------------------------------------------- #

def _model_brief(model: SystemModel) -> str:
    """A compact, qualitative description of the system for the personas to reason
    over. Numbers that appear here are CONTEXT the LLM reads, never numbers it is
    asked to produce — and anything it echoes back is caught by the guard."""
    lines = [f"SYSTEM: {model.name}", f"Workload profile: {model.workload.description}"]
    if model.domain_flags:
        lines.append(f"Domain flags: {', '.join(model.domain_flags)}")
    lines.append("\nComponents (topology to reason about — capacities are engine inputs, not yours):")
    for c in model.components.values():
        lines.append(f"  - {c.id}: {c.kind.value} — {c.name} (instances: {c.instances})")
    lines.append("\nRequest flows:")
    for f in model.flows:
        hops = " -> ".join(s.component_id for s in f.path)
        lines.append(f"  - {f.name} (share {f.share:.0%}): {hops}")
    if model.assumptions:
        lines.append("\nStated assumptions (context only):")
        for a in model.assumptions:
            lines.append(f"  - {a.subject}: {a.statement}")
    return "\n".join(lines)


def _extract_json(text: str, *, expect: str) -> object:
    """Pull the first JSON array/object out of an LLM reply, tolerating prose or
    code fences around it. `expect` is 'array' or 'object'.

    Uses raw_decode from each candidate opening bracket, so it parses the FIRST
    complete value and ignores trailing prose — even when that prose contains the
    same bracket character (an LLM footnote like '[2]' or an aside '{like this}').
    A naive find/rfind slice would swallow that trailing junk and fail the run."""
    open_ch = "[" if expect == "array" else "{"
    dec = json.JSONDecoder()
    idx = text.find(open_ch)
    while idx != -1:
        try:
            obj, _ = dec.raw_decode(text, idx)
            return obj
        except json.JSONDecodeError:
            idx = text.find(open_ch, idx + 1)
    raise CouncilError(f"expected a JSON {expect} in council reply; got:\n{text[:400]}")


# --------------------------------------------------------------------------- #
# The council
# --------------------------------------------------------------------------- #

class ClaudeCouncil:
    """Real consensus council. Satisfies the `Council` protocol from council.py."""

    def __init__(self, model: str, *, client: LLM | None = None,
                 personas: tuple[Persona, ...] = PERSONAS) -> None:
        self._model = model
        self._llm: LLM = client if client is not None else AnthropicLLM(model)
        self._personas = personas

    # -- public interface ---------------------------------------------------- #

    def design(self, model: SystemModel) -> list[ADR]:
        brief = _model_brief(model)
        proposals = self._stage_independent_design(brief)
        reviews = self._stage_blind_peer_review(proposals)
        adrs = self._stage_chairman_synthesis(brief, proposals, reviews)
        # Defence in depth: guard every ADR even though the prompts forbid numbers.
        adrs = [_scrub_adr(a) for a in adrs]
        # MANDATORY high-stakes gate (Doc 03 §6 — a MUST). Enforced deterministically,
        # NOT left to LLM discretion, so activating the real council can never silently
        # drop the expert-review block the stub guarantees. Refuse to imply prod-safety.
        if any(f.startswith("high_stakes") for f in model.domain_flags) and not any(
            "review" in a.area.lower() for a in adrs
        ):
            adrs.append(ADR(
                area="Review gate",
                decision="REQUIRES expert/legal/security review before any production use.",
                rationale="Domain flagged high-stakes; Keystone does not certify safety.",
                confidence="high",
                kill_criteria=["Shipped without independent expert sign-off"],
                source="claude",
            ))
        return adrs

    # -- stage 1: independent design ---------------------------------------- #

    def _stage_independent_design(self, brief: str) -> list[dict]:
        proposals: list[dict] = []
        for p in self._personas:
            system = (
                f"You are the {p.title} on an architecture council. Your remit: {p.brief}.\n"
                f"{_NO_NUMBERS_RULE}"
            )
            user = (
                f"{brief}\n\n"
                "Propose your design positions for THIS system, in your area only. "
                "Reply with ONLY a JSON array, each item:\n"
                '{"area": "<decision area>", "position": "<the recommendation>", '
                '"rationale": "<why, qualitatively>", "risk": "<the main risk or trade-off>"}'
            )
            raw = self._llm.complete(label=f"design:{p.key}", system=system, user=user, max_tokens=4096)
            items = _extract_json(raw, expect="array")
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict):
                    it["_persona"] = p.title
                    proposals.append(it)
        if not proposals:
            raise CouncilError("independent-design stage produced no proposals")
        return proposals

    # -- stage 2: blind peer review (anonymised) ---------------------------- #

    def _stage_blind_peer_review(self, proposals: list[dict]) -> list[dict]:
        # Anonymise: identities stripped, proposals labelled P1..Pn to cut herding.
        digest_lines = []
        for idx, pr in enumerate(proposals, start=1):
            digest_lines.append(
                f"P{idx} [{pr.get('area', '?')}]: {pr.get('position', '')} "
                f"(rationale: {pr.get('rationale', '')}; risk: {pr.get('risk', '')})"
            )
        digest = "\n".join(digest_lines)

        reviews: list[dict] = []
        for p in self._personas:
            system = (
                f"You are the {p.title} on an architecture council, doing BLIND peer "
                f"review. The proposals below are anonymised — judge them on merit, not "
                f"authorship. Your remit: {p.brief}.\n{_NO_NUMBERS_RULE}"
            )
            user = (
                f"Anonymised proposals:\n{digest}\n\n"
                "Critique these from your perspective: where are they wrong, risky, or "
                "missing something? Reply with ONLY a JSON array, each item:\n"
                '{"target": "P<n>", "concern": "<the critique>", '
                '"severity": "low|med|high"}'
            )
            raw = self._llm.complete(label=f"review:{p.key}", system=system, user=user, max_tokens=4096)
            items = _extract_json(raw, expect="array")
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict):
                    it["_reviewer"] = p.title
                    reviews.append(it)
        return reviews

    # -- stage 3: chairman synthesis ---------------------------------------- #

    def _stage_chairman_synthesis(self, brief: str, proposals: list[dict],
                                  reviews: list[dict]) -> list[ADR]:
        prop_block = "\n".join(
            f"- [{pr.get('_persona', '?')}] {pr.get('area', '?')}: {pr.get('position', '')} "
            f"— rationale: {pr.get('rationale', '')}; risk: {pr.get('risk', '')}"
            for pr in proposals
        )
        review_block = "\n".join(
            f"- [{rv.get('_reviewer', '?')}] on {rv.get('target', '?')} "
            f"({rv.get('severity', '?')}): {rv.get('concern', '')}"
            for rv in reviews
        ) or "(no critiques returned)"

        user = (
            f"{brief}\n\n"
            f"INDEPENDENT PROPOSALS:\n{prop_block}\n\n"
            f"BLIND PEER REVIEW:\n{review_block}\n\n"
            "Synthesise these into Architecture Decision Records, one per distinct "
            "decision area. Preserve minority views as named dissent — do not erase "
            "disagreement. Reply with ONLY a JSON array, each item:\n"
            '{"area": "<decision area>", "decision": "<the chosen decision>", '
            '"rationale": "<why this won>", '
            '"dissent": ["<role>: <the minority position and why>", ...], '
            '"confidence": "low|med|high", '
            '"kill_criteria": ["<condition that would force revisiting this>", ...]}'
        )
        raw = self._llm.complete(label="chairman", system=_CHAIRMAN_SYSTEM, user=user, max_tokens=8192)
        items = _extract_json(raw, expect="array")
        adrs: list[ADR] = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            conf = str(it.get("confidence", "med")).lower()
            if conf not in ("low", "med", "high"):
                conf = "med"
            adrs.append(ADR(
                area=str(it.get("area", "Decision")),
                decision=str(it.get("decision", "")),
                rationale=str(it.get("rationale", "")),
                dissent=[str(d) for d in it.get("dissent", []) if str(d).strip()],
                confidence=conf,
                kill_criteria=[str(k) for k in it.get("kill_criteria", []) if str(k).strip()],
                source="claude",
            ))
        if not adrs:
            raise CouncilError("chairman synthesis produced no ADRs")
        return adrs
