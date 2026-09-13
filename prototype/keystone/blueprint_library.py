"""The blueprint library — reference architectures as DATA, validated before they ship.

Keystone matched four intents. Everything else fell through to a generic shape, which is why typing
"a tool like Telegram" got you a placeholder. The fix is not forty more hand-written Python builders;
it is to make a blueprint a **spec file** (`export.py`) plus a little matching metadata, so the
library grows by adding data and every entry is checked by the engine before it is allowed in.

What "validated" means here is specific, and it is the reason this is worth doing at all:

1. It parses and passes `validate_model` — the engine will accept it.
2. It **simulates** — no crash, and it produces a bottleneck and a breakpoint.
3. It **holds at its own design load** — peak utilisation under the safe ceiling. A reference
   architecture that is already saturated as shipped is not a reference, it is a bug someone will
   copy.
4. It is **priced from the grounded catalogue** — not $0, and not a hand-typed guess. Every
   component that has a per-instance price carries the cited one.

`validate_library_entry` is the gate, and `scripts/validate_blueprint.py` runs it, so the same
check that guards the suite is the one used while authoring. A blueprint that fails does not ship.

Matching is deliberately dumb (keyword overlap, most specific first) for the same reason the old
`_REFERENCES` tuple was: the LLM design path is what generalises to arbitrary intents. The library's
job is to answer the common cases instantly, offline, at $0 — not to be clever.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from functools import lru_cache

from .export import ExportError, from_dict
from .model import Assumption, SystemModel
from .pricing_catalogue import KINDS_WITHOUT_PER_INSTANCE_PRICE
from .simulation import SAFE_UTILIZATION, simulate

__all__ = [
    "LibraryEntry", "library", "match", "load_entry", "validate_library_entry",
    "LIBRARY_DIR", "ValidationReport", "keyword_collisions", "byte_gaps", "BYTE_KINDS",
    "all_matches",
]

LIBRARY_DIR = pathlib.Path(__file__).with_name("blueprints") / "library"


@dataclass(frozen=True)
class LibraryEntry:
    key: str
    name: str
    category: str
    difficulty: str
    summary: str
    keywords: tuple[str, ...]
    path: pathlib.Path

    def build(self) -> SystemModel:
        """The model, with any computed byte gap DECLARED on it as a GAP assumption.

        The gap has to travel with the model, not just sit in the validator's report. A CDN with
        undeclared egress makes the cost figure a FLOOR, and the reader of the report is the person
        who needs to know that — the validator is read by whoever adds a blueprint, once. Writing
        the disclosure by hand into each file was the alternative and it is worse: eleven of the
        twenty affected files had said nothing, and the twenty-first author would forget too.
        Computing it means a blueprint cannot ship the gap silently.

        This is EVIDENCE-ONLY: it appends an assumption and changes no number (docs/03).
        """
        model = load_entry(self.path)[0]
        gaps = byte_gaps(model)
        if gaps:
            model.assumptions = list(model.assumptions) + [
                Assumption(subject=subject, statement=text, confidence="high",
                           source="benchmark", provenance="GAP")
                for subject, text in gaps
            ]
        return model


def load_entry(path: pathlib.Path) -> tuple[SystemModel, dict]:
    """Load one library file → (model, library metadata). Raises ExportError on anything malformed."""
    payload = json.loads(path.read_text(encoding="utf8"))
    meta = payload.get("_library") or {}
    return from_dict(payload), meta


@lru_cache(maxsize=1)
def library() -> tuple[LibraryEntry, ...]:
    """Every blueprint in the library, sorted by key. A file that fails to load is SKIPPED rather
    than crashing the catalogue — but the suite fails on it, so it cannot survive unnoticed."""
    out: list[LibraryEntry] = []
    if not LIBRARY_DIR.is_dir():
        return ()
    for path in sorted(LIBRARY_DIR.glob("*.json")):
        try:
            model, meta = load_entry(path)
        except (ExportError, json.JSONDecodeError, OSError):
            continue
        out.append(LibraryEntry(
            key=path.stem,
            name=model.name,
            category=str(meta.get("category", "uncategorised")),
            difficulty=str(meta.get("difficulty", "unknown")),
            summary=str(meta.get("summary", "")),
            keywords=tuple(str(k).lower() for k in (meta.get("keywords") or [])),
            path=path,
        ))
    return tuple(out)


def all_matches(intent: str) -> list[tuple[LibraryEntry, int, str]]:
    """EVERY library entry the intent hits, best first — (entry, hit count, longest keyword matched).

    `match()` returns one winner and throws the rest away, which is how "Facebook with a crypto
    wallet for all users" came back as a Digital Wallet with no social graph in it and nothing said.
    The library already knew the intent also hit the social blueprints; only the ranking discarded
    that. Keeping the runners-up lets the report name what it did NOT design.
    """
    q = f" {intent.lower().strip()} "
    out: list[tuple[LibraryEntry, int, str]] = []
    for entry in library():
        hits = [k for k in entry.keywords if k and k in q]
        if hits:
            out.append((entry, len(hits), max(hits, key=len)))
    out.sort(key=lambda t: (-t[1], -len(t[2]), t[0].key))
    return out


def match(intent: str) -> LibraryEntry | None:
    """Best library entry for an intent, or None.

    Scores by how many of an entry's keywords appear in the intent, preferring the LONGEST keyword
    matched so a specific phrase ("ride sharing") beats a generic one ("chat") when both hit. Ties
    break on key, so matching is deterministic — the same intent always resolves to the same design.
    """
    q = f" {intent.lower().strip()} "
    best: tuple[int, int, str] | None = None
    winner: LibraryEntry | None = None
    for entry in library():
        hits = [k for k in entry.keywords if k and k in q]
        if not hits:
            continue
        score = (len(hits), max(len(k) for k in hits), entry.key)
        if best is None or score[:2] > best[:2] or (score[:2] == best[:2] and score[2] < best[2]):
            best, winner = score, entry
    return winner


# The kinds with no per-instance price — cdn and object_store — are exactly the ones that carry the
# MOST traffic in media designs (81% of arrivals in the video blueprints) and cost the most in
# reality. Two zero-defaults compound: the component is unpriced per-instance AND ships with zero
# usage volume, while the only cost check is "total != $0", which the compute line alone always
# satisfies. A media blueprint could therefore be wrong by three orders of magnitude and still show
# green.
#
# This is NOT the Little's-Law check the audit also suggested. I tried that first: it flagged
# legitimate high-concurrency proxies (an LLM gateway at 67 rps x 2.4 s is a real shape) and MISSED
# the case it was meant to catch, because a transcode asserted at 0.5 rps x 2000 ms is arithmetically
# consistent — the defect there is that 2 s is the wrong duration for a transcode, a domain judgement
# no formula over these fields can make. Bytes, by contrast, are mechanical: a CDN serving real
# traffic that declares zero egress is provably incomplete.
BYTE_KINDS = ("cdn", "object_store")


def byte_gaps(model: SystemModel) -> list[tuple[str, str]]:
    """(subject, statement) for every byte-carrying component that declares no volume.

    Shared by the gate and by `LibraryEntry.build`, so what the validator warns about and what the
    report discloses are the SAME computation — they cannot drift into disagreeing.
    """
    sim = simulate(model)
    out: list[tuple[str, str]] = []
    for cid, comp in model.components.items():
        if comp.kind.value not in BYTE_KINDS:
            continue
        rps = sim.components[cid].arrival_rps if cid in sim.components else 0.0
        if rps < 1.0:
            continue                                # decorative / idle: nothing to declare
        if comp.egress_gb_per_month or comp.storage_gb:
            continue
        out.append((cid, (
            f"COST IS A FLOOR, not an estimate, for {comp.name}: this {comp.kind.value} carries "
            f"{rps:,.0f} req/s and declares zero egress and zero storage, so its bytes are not in "
            f"the bill below. For a {comp.kind.value} at this rate the byte line is normally the "
            f"LARGEST line, often by orders of magnitude — the total is green only because the "
            f"compute line is non-zero. Fix: set egress_gb_per_month and storage_gb from your own "
            f"traffic before treating this figure as a budget.")))
    return out


@dataclass
class ValidationReport:
    key: str
    ok: bool
    failures: list[str]
    components: int
    flows: int
    peak_utilisation: float | None
    breakpoint_rps: float | None
    monthly_cents: int
    unpriced: list[str]
    spofs: list[str]
    warnings: list[str]

    def summary_line(self) -> str:
        state = "OK  " if self.ok else "FAIL"
        peak = "n/a" if self.peak_utilisation is None else f"{self.peak_utilisation:5.0%}"
        return (f"[{state}] {self.key:<28} {self.components:>2}c {self.flows}f  peak {peak}  "
                f"${self.monthly_cents // 100:>7,}/mo"
                + (f"  {len(self.spofs)} SPOF" if self.spofs else "")
                + (f"  {len(self.warnings)} gap" if self.warnings else "")
                + ("" if self.ok else "  <- " + "; ".join(self.failures)))


def validate_library_entry(path: pathlib.Path, *,
                           ceiling: float = SAFE_UTILIZATION) -> ValidationReport:
    """The gate. A blueprint that does not pass this does not belong in the library."""
    key = path.stem
    failures: list[str] = []
    # A design that is SATURATED is wrong and must not ship. A design whose byte volumes are
    # undeclared is INCOMPLETE — its compute figure is correct and its total is a floor. Those are
    # different claims and deserve different treatment: reject what is wrong, DISCLOSE what is
    # incomplete. Warnings are carried into the report and written onto the model as a GAP
    # assumption, so the incompleteness travels with the number instead of being silently dropped.
    warnings: list[str] = []
    try:
        model, meta = load_entry(path)
    except Exception as e:                                    # noqa: BLE001 — report, never raise
        return ValidationReport(key, False, [f"does not load: {type(e).__name__}: {e}"],
                                0, 0, None, None, 0, [], [], [])

    for field in ("category", "difficulty", "summary", "keywords"):
        if not meta.get(field):
            failures.append(f"_library.{field} is missing")
    if len(meta.get("keywords") or []) < 2:
        failures.append("needs at least 2 keywords to be findable")

    try:
        sim = simulate(model)
    except Exception as e:                                    # noqa: BLE001
        return ValidationReport(key, False, failures + [f"does not simulate: {e}"],
                                len(model.components), len(model.flows), None, None, 0, [], [], [])

    peak = sim.bottleneck_utilization
    if peak is None or peak != peak:                          # NaN guard
        failures.append("no computable peak utilisation")
    elif peak > ceiling:
        failures.append(f"already saturated as shipped: peak {peak:.0%} > {ceiling:.0%} ceiling")

    # BYTE-PLAUSIBILITY FLOOR (audit finding). Rationale lives on `byte_gaps`; `build()` writes the
    # same finding onto the model as a GAP assumption, so the gate and the report never disagree.
    for _subject, statement in byte_gaps(model):
        warnings.append(statement)

    # SPOF VISIBILITY (audit finding). The engine already computes single points of failure and the
    # gate was discarding them. A single-instance primary is not a gate FAILURE — plenty of honest
    # reference designs have one — but shipping it silently is the same defect as shipping a
    # saturated design silently, so it is surfaced on every report.
    spofs = list(sim.spofs)

    # Priced from the grounded catalogue — a reference design must not report $0/month.
    unpriced = [c.name for c in model.components.values()
                if c.monthly_cost_per_instance == 0
                and c.kind.value not in KINDS_WITHOUT_PER_INSTANCE_PRICE]
    if unpriced:
        failures.append(f"{len(unpriced)} priceable component(s) cost 0: {', '.join(unpriced[:3])}")
    if len(model.components) < 3:
        failures.append("too small to be a useful reference (fewer than 3 components)")
    if not model.flows:
        failures.append("no request flows")

    return ValidationReport(
        key=key, ok=not failures, failures=failures,
        components=len(model.components), flows=len(model.flows),
        peak_utilisation=peak, breakpoint_rps=sim.breakpoint_rps_safe,
        monthly_cents=sim.monthly_cost, unpriced=unpriced, spofs=spofs, warnings=warnings,
    )


def keyword_collisions() -> dict[str, list[str]]:
    """Keywords that resolve to a DIFFERENT entry than the one declaring them.

    A blueprint whose own keyword lands on a sibling is unreachable by the words its author chose,
    and the failure is invisible unless you check the WINNER — asserting only that *something*
    matched is how ten of these shipped green. Substring hijacks are the common cause: "x clone"
    inside "netfli-x clone", "rag" inside "sto-rag-e", "consul" inside "consul-ting".
    """
    out: dict[str, list[str]] = {}
    for entry in library():
        for kw in entry.keywords:
            winner = match(f"i want to build {kw}")
            if winner is not None and winner.key != entry.key:
                out.setdefault(entry.key, []).append(f"{kw!r} -> {winner.key}")
    return out
