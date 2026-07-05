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

from keystone.council import ADR, ensure_high_stakes_gate
from keystone.llm import LLM, AnthropicLLM
from keystone.model import SystemModel

log = logging.getLogger("keystone.council")


class CouncilError(RuntimeError):
    """Raised when the council cannot produce a usable result (parse/transport)."""


# The provider-agnostic LLM transport (`LLM` protocol + default `AnthropicLLM`) lives
# in keystone.llm so the council and the ingestion layer share one testable seam
# (ADR-001/ADR-002). Inject any `LLM` for $0 offline tests.


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
# Two layers (ADR-001 §3 — the Hybrid policy, because an allowlist of unit
# spellings can NEVER be complete):
#   1. UNIT-ANCHORED patterns (precision) — a magnitude bound to a known
#      performance/cost/throughput/data-rate unit (rps, ms, Gbps, $/mo, …),
#      including ranges/approximations ("50-100ms", "~50ms") so no lower bound
#      survives.
#   2. A NOUN-ANCHORED deny-by-default BACKSTOP (recall) — any magnitude sitting
#      next to an engine-OWNED concept (utilisation/throughput/latency/cost/…) is
#      scrubbed even when its unit spelling is unknown. Keyed on engine-metric
#      NOUNS, never design vocabulary, so "90% of traffic", "shard into 4",
#      "3 availability zones", "5 nodes" are left untouched.
# The integer run `_INT` is BOUNDED and NON-backtrackable: a comma-grouped form (the
# comma repeat is bounded {1,5} — an unbounded `+` is itself quadratic) OR <=15 plain
# digits, with `(?![\d,])` forbidding it from giving back a digit/comma. Bounding BOTH
# branches kills the catastrophic backtracking on a long digit OR comma run (ADR-001
# H2; the plain-only and then comma-only ReDoS were each caught by re-verification)
# AND the leading-digit-eat ("12 nodes" must not become "[…]2 nodes"). The prompt-level
# `_NO_NUMBERS_RULE` is the first line; this guard is the binding control, and report.py
# states only what the guard can prove. Still deliberately NOT matched (left to the
# prompt rule): bare single-letter time ("30s" TTL), bare "us" ("us-east"), spelled-out
# magnitudes ("eight thousand"), bare data VOLUME ("16 GB", ambiguous with sizing).
# Accepted over-redaction (safe direction, ADR-001 L): a configured design DURATION in
# seconds/ms ("TTL of 300 seconds") is scrubbed like a latency — a keyword carve-out was
# tried and removed because it could not be made leak-safe (latency phrasing is
# open-ended; "served in 50ms" has no noun). A typed-duration field is the v2 lever.

_REDACTION = "[engine-owned metric removed]"

_INT = r"(?:\d{1,3}(?:,\d{3}){1,5}|\d{1,15})(?![\d,])"
# Multiplier (k/m/g/b/t) only when NOT followed by a letter/digit, so it cannot eat
# the "m" of "machines"/"million" or the "g" of "gateway".
_MULT = r"(?:[kmgbt](?![a-z\d]))?"
# Spelled-out multiplier so a unit-bound figure survives the word ("2 million rps").
_SPELLED = r"(?:\s?(?:thousand|million|billion|trillion))?"
_NUM = rf"{_INT}(?:\.\d+)?(?:e[+-]?\d+)?{_SPELLED}\s?{_MULT}\s?"
# Range / approximation wrapper so "50-100ms"/"~50ms"/"sub-50ms" collapse whole.
_APPROX = (r"(?:[~≈<>]\s?|sub[\s-]?|about\s|approx\.?\s|roughly\s|around\s|"
           r"under\s|over\s|at\s+least\s|up\s+to\s)?")
_RANGE = rf"(?:{_NUM}(?:\s?(?:-|–|—|to|and|±)\s?))?"
_VAL = rf"{_APPROX}{_RANGE}{_NUM}"

_PERIOD = r"(?:months?|years?|hours?|days?|weeks?|mo|hr|yr|wk)"
_BILL = r"(?:mo|months?|monthly|yr|years?|yearly|annum|annually)"  # billing periods only
_PER = r"(?:/\s?|per\s?)"
_WIN = r"(?:s|sec|secs|second|seconds|min|mins|minute|minutes|hr|hour|hours|day|days)"
_THRU = (r"(?:req|reqs|requests?|transactions?|txns?|ops|operations?|calls?|hits?|"
         r"reads?|writes?|queries|query|messages?|msgs?|packets?|events?)")

# UNIT-ANCHORED patterns (precision). A magnitude bound to a known unit is redacted.
_METRIC_PATTERNS = (
    re.compile(rf"[$€£]\s?{_VAL}(?:{_PER}{_PERIOD})?", re.I),                        # $420/month, $8k, $2.5k/mo
    re.compile(rf"(?<!\w){_VAL}\$", re.I),                                                # 500$
    re.compile(rf"(?<!\w){_VAL}(?:usd|dollars?|cents?|eur|euros?|gbp|pounds?)\b", re.I),  # 500 dollars, 500 EUR
    re.compile(rf"\b(?:usd|eur|gbp)\s?{_VAL}(?:{_PER}{_PERIOD})?", re.I),            # USD 500, USD 5/month
    re.compile(rf"(?<!\w){_VAL}{_PER}{_BILL}\b", re.I),                              # bare cost-rate: 8k/mo, 8000/month
    re.compile(rf"(?<!\w){_VAL}(?:rps|qps|tps|iops)\b", re.I),                            # 8000 rps, 50000 IOPS
    re.compile(rf"(?<!\w){_VAL}{_THRU}\s?{_PER}\s?{_WIN}\b", re.I),                        # 8000 requests/second
    re.compile(rf"(?<!\w){_VAL}{_PER}\s?(?:s|sec|second)\b", re.I),                        # 8000/s, 8000/sec
    re.compile(rf"(?<!\w){_VAL}(?:milliseconds?|millis|msec|ms|microseconds?|µs|μs|"
               rf"nanoseconds?|nsec|ns|seconds?|secs?)\b", re.I),                          # 50ms, 2.5 seconds, 20 ns
    re.compile(rf"(?<!\w){_VAL}(?:[kmgtp]?bps|gbps|mbps|kbps|tbps)\b", re.I),              # 10Gbps, 40 Mbps
    re.compile(rf"(?<!\w){_VAL}[kmgtp]?b(?:it)?\s?{_PER}\s?{_WIN}\b", re.I),               # 10 GB/s, 5 Gbit/s, 2 TB/day
    re.compile(rf"(?<!\w){_VAL}(?:kilo|mega|giga|tera|peta)?(?:bit|byte)s?\s?{_PER}\s?{_WIN}\b", re.I),  # 10 gigabit per second
)

# Deny-by-default backstop: a magnitude next to an engine-OWNED concept (a number the
# deterministic engine PRODUCES — utilisation/latency/throughput/cost/…) is scrubbed
# whatever the unit. Engine OUTPUTS only: cache hit-rate, read/write split, instance
# counts etc. are model INPUTS / design assumptions, deliberately absent (a "hit-rate
# below 70%" kill criterion must survive). "availability" excludes "availability zone".
_ENGINE_NOUN = (
    r"utili[sz]ation|utili[sz]ed|availability(?!\s+zones?)|uptime|downtime|"
    r"saturat(?:ion|ed)|error[\s-]?rate|packet[\s-]?loss|throughput|breakpoint|"
    r"latenc(?:y|ies)|response[\s-]?times?|bandwidth|headroom|p50|p95|p99|p999|iops|"
    r"cost|costs|costing|spend|spends|spent|budget|priced?|pricing|egress|ingress|"
    r"bills?|billed|billing|invoiced?|invoices?"
)
# A ratio (90/10, 99:1), a design count/sizing ("12 nodes", "8 queues"), AND a workload
# INPUT ("50000 users", "DAU") are NOT engine outputs — a magnitude bound to one survives
# even next to an engine noun. The `(?<![\d:/])` on _MAG anchors a number to a clean
# left boundary (so a ratio's right operand "90/10" is not matched as "0"); the forward
# lookahead `(?!\s?[:/]\s?\d)` protects the left operand; the keep-noun lookahead protects
# counts/inputs. report.py renders only what this can prove (no absolute claim).
_DESIGN_COUNT = (r"replicas?|nodes?|instances?|shards?|partitions?|zones?|regions?|"
                 r"copies|cores?|vcpus?|cpus?|workers?|pods?|containers?|nines?|azs?|"
                 r"vms?|machines?|servers?|tables?|columns?|keys?|fields?|tiers?|brokers?|"
                 r"queues?|gateways?|datacent(?:er|re)s?|data[\s-]?cent(?:er|re)s?|clusters?|"
                 r"caches?|microservices?|services?|buckets?|endpoints?|channels?|hops?|"
                 r"topics?|streams?|consumers?|producers?|lambdas?|functions?|"
                 r"users?|dau|mau|customers?|tenants?|subscribers?|accounts?|records?|"
                 r"rows?|documents?|objects?|items?|entities?|sessions?")
_MAG = (rf"(?<![\d:/]){_INT}(?:\.\d+)?(?:e[+-]?\d+)?{_SPELLED}\s?{_MULT}\s?(?:%|percent)?"
        rf"(?!\s?[:/]\s?\d)(?!\s?(?:{_DESIGN_COUNT})\b)")
_GAP = r".{0,22}?"   # bounded -> ReDoS-safe; wide enough for natural connectives

_BACKSTOP = (
    (re.compile(rf"((?:{_ENGINE_NOUN}){_GAP})({_MAG})", re.I), r"\1" + _REDACTION),  # noun … number
    (re.compile(rf"({_MAG})({_GAP}(?:{_ENGINE_NOUN}))", re.I), _REDACTION + r"\2"),  # number … noun
)


def _redact_engine_metrics(text: str) -> tuple[str, int]:
    """Replace any performance/cost magnitude with a neutral marker (ADR-001 §3).

    Returns (clean_text, count). Two layers: unit-anchored patterns (precision) then a
    noun-anchored deny-by-default backstop (recall — an allowlist of unit spellings can
    never be complete). The prime directive forbids the council from producing numbers;
    rather than crash the loop on a stray figure we redact it and flag the ADR
    (transparency, Doc 03 §2). Never silently passes a matched figure through; the count
    drives the transparency flag in `_scrub_adr`."""
    count = 0
    out = text
    for pat in _METRIC_PATTERNS:
        out, n = pat.subn(_REDACTION, out)
        count += n
    for pat, repl in _BACKSTOP:
        out, n = pat.subn(repl, out)
        count += n
    return out, count


def _scrub_adr(adr: ADR, source: str = "claude") -> ADR:
    """Apply the guard across every free-text field of an ADR; flag if it fired. `source` is the
    honest provenance label (<provider>:<model>) stamped on the returned ADR.

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
        confidence=adr.confidence, kill_criteria=kill, source=source,
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


def _as_list(v: object) -> list:
    """Normalise an LLM list-field. A bare string becomes a ONE-element list (one
    bullet), never a per-character explosion: `[str(c) for c in "none"]` would emit
    bullets 'n','o','n','e' into the dissent section (ADR-001 H1). None/scalar -> []
    or [scalar]."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


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


# The peer-review and chairman prompts AGGREGATE every persona's output, so their size grows with
# persona count and verbosity — a verbose model (or many proposals) can exceed a provider's input-token
# cap (e.g. GitHub Models' free tier ~8k → HTTP 413 Payload Too Large). Bound each free-text field and
# cap each aggregated block to a char budget so the synthesis prompt fits any reasonable provider. This
# is qualitative context only (no numbers), so clipping never touches the prime directive or the
# engine's metrics; omissions are NOTED, never silent (Doc 03 honesty).
_FIELD_CLIP = 200          # max chars per free-text field (position/rationale/risk/concern)
_BLOCK_BUDGET = 6000       # max chars per aggregated block (proposals / reviews)


def _clip(text: object, limit: int = _FIELD_CLIP) -> str:
    """Collapse whitespace and truncate a free-text field to `limit` chars ('…' if cut)."""
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[:limit - 1].rstrip() + "…"


def _interleave_by(items: list, key) -> list:
    """Round-robin `items` grouped by `key(item)`, so the FIRST item of every group precedes any
    group's second. Feeding this to `_bounded_block` guarantees every source (persona) is represented
    before any source contributes a second item — so a budget cut drops EXTRA items, never a whole
    viewpoint. This protects the honesty rule ('preserve minority views as named dissent') when the
    aggregated prompt must be trimmed to fit a provider: the YAGNI/AI-infusion minority voices (last in
    PERSONAS order) survive a trim instead of being the first dropped."""
    groups: dict = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    out, rnd = [], 0
    while True:
        row = [g[rnd] for g in groups.values() if rnd < len(g)]
        if not row:
            return out
        out.extend(row)
        rnd += 1


def _bounded_block(lines: list[str], budget: int = _BLOCK_BUDGET) -> str:
    """Join lines under a char budget; on overflow keep the earliest and NOTE how many were dropped
    (never silently — honesty). Pair with `_interleave_by` so 'earliest' means 'one per source first',
    not 'the first few sources'. Returns '' for no lines so the caller can supply a fallback."""
    out, used = [], 0
    for i, ln in enumerate(lines):
        ln = _clip(ln, budget)                       # defensive: no single line can blow the budget
        add = len(ln) + (1 if out else 0)            # the '\n' join-separator only applies between lines
        if out and used + add > budget:
            out.append(f"…({len(lines) - i} more omitted to fit the model input budget)")
            break
        out.append(ln)
        used += add
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# The council
# --------------------------------------------------------------------------- #

class ClaudeCouncil:
    """Real consensus council. Satisfies the `Council` protocol from council.py."""

    def __init__(self, model: str, *, client: LLM | None = None,
                 personas: tuple[Persona, ...] = PERSONAS, source: str = "claude") -> None:
        self._model = model
        self._llm: LLM = client if client is not None else AnthropicLLM(model)
        self._personas = personas
        # Honest provenance stamped on every ADR (Doc 03): "<provider>:<model>", e.g.
        # "github:openai/gpt-4o-mini". The report shows this so a reader knows WHICH model reasoned —
        # never mislabelled "claude" when another vendor ran it. Defaults to "claude" only for direct
        # construction; make_council passes the real provider:model.
        self._source = source

    # -- public interface ---------------------------------------------------- #

    def design(self, model: SystemModel) -> list[ADR]:
        brief = _model_brief(model)
        proposals = self._stage_independent_design(brief)
        reviews = self._stage_blind_peer_review(proposals)
        adrs = self._stage_chairman_synthesis(brief, proposals, reviews)
        # Defence in depth: guard every ADR even though the prompts forbid numbers.
        adrs = [_scrub_adr(a, self._source) for a in adrs]
        # MANDATORY high-stakes gate (Doc 03 §6 — a MUST). Deterministic and shared
        # with the stub; de-dups on the gate's identity, NOT a "review" substring, so
        # a benign "Code review" ADR can never silently drop it (ADR-001 C1).
        return ensure_high_stakes_gate(adrs, model.domain_flags, source=self._source)

    # -- shared LLM call with a one-shot repair retry ----------------------- #

    def _complete_json(self, *, label: str, system: str, user: str, max_tokens: int,
                       expect: str = "array") -> object:
        """Call the model and extract JSON; on a parse failure retry ONCE with a firmer, more compact
        instruction. Small/free models often wrap JSON in prose, add markdown fences, or TRUNCATE a long
        reply — a hard failure the council would otherwise raise on. `_extract_json` already tolerates
        fences/prose, so the remaining failure is a malformed/incomplete reply; a second attempt asking
        for a short, complete JSON usually parses. Costs an extra call only on failure; if the retry also
        fails, the original CouncilError still propagates (fail-loud unchanged). No numbers involved — the
        prime-directive guard still runs on the parsed ADRs downstream."""
        try:
            return _extract_json(self._llm.complete(label=label, system=system, user=user,
                                                    max_tokens=max_tokens), expect=expect)
        except CouncilError:
            log.warning("council reply from [%s] did not parse; retrying once with a compact-JSON reminder",
                        label)
            firmer = (f"{user}\n\nIMPORTANT: reply with ONLY one valid, COMPLETE JSON {expect} — no "
                      "markdown fences, no prose, no commentary. Keep every field to one short sentence.")
            return _extract_json(self._llm.complete(label=f"{label}:retry", system=system, user=firmer,
                                                    max_tokens=max_tokens), expect=expect)

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
            items = self._complete_json(label=f"design:{p.key}", system=system, user=user, max_tokens=4096)
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
        # Interleave by author so a budget trim keeps one proposal per persona before any second — the
        # anonymised P-labels follow this fair order, so no persona's proposal is systematically unseen.
        fair = _interleave_by(proposals, lambda pr: pr.get('_persona', '?'))
        digest_lines = []
        for idx, pr in enumerate(fair, start=1):
            digest_lines.append(
                f"P{idx} [{_clip(pr.get('area', '?'), 60)}]: {_clip(pr.get('position', ''))} "
                f"(rationale: {_clip(pr.get('rationale', ''))}; risk: {_clip(pr.get('risk', ''))})"
            )
        digest = _bounded_block(digest_lines)

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
            items = self._complete_json(label=f"review:{p.key}", system=system, user=user, max_tokens=4096)
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict):
                    it["_reviewer"] = p.title
                    reviews.append(it)
        return reviews

    # -- stage 3: chairman synthesis ---------------------------------------- #

    def _stage_chairman_synthesis(self, brief: str, proposals: list[dict],
                                  reviews: list[dict]) -> list[ADR]:
        # Interleave by author (proposals) / reviewer so a budget trim drops each source's EXTRA items
        # before it drops any source's first — the minority YAGNI/AI voices survive the trim (honesty).
        prop_block = _bounded_block([
            f"- [{_clip(pr.get('_persona', '?'), 40)}] {_clip(pr.get('area', '?'), 60)}: "
            f"{_clip(pr.get('position', ''))} — rationale: {_clip(pr.get('rationale', ''))}; "
            f"risk: {_clip(pr.get('risk', ''))}"
            for pr in _interleave_by(proposals, lambda pr: pr.get('_persona', '?'))
        ])
        review_block = _bounded_block([
            f"- [{_clip(rv.get('_reviewer', '?'), 40)}] on {_clip(rv.get('target', '?'), 20)} "
            f"({_clip(rv.get('severity', '?'), 12)}): {_clip(rv.get('concern', ''))}"
            for rv in _interleave_by(reviews, lambda rv: rv.get('_reviewer', '?'))
        ]) or "(no critiques returned)"

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
        items = self._complete_json(label="chairman", system=_CHAIRMAN_SYSTEM, user=user, max_tokens=8192)
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
                dissent=[str(d) for d in _as_list(it.get("dissent")) if str(d).strip()],
                confidence=conf,
                kill_criteria=[str(k) for k in _as_list(it.get("kill_criteria")) if str(k).strip()],
                source=self._source,
            ))
        if not adrs:
            raise CouncilError("chairman synthesis produced no ADRs")
        return adrs
