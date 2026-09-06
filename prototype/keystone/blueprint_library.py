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
from .model import SystemModel
from .pricing_catalogue import KINDS_WITHOUT_PER_INSTANCE_PRICE
from .simulation import SAFE_UTILIZATION, simulate

__all__ = [
    "LibraryEntry", "library", "match", "load_entry", "validate_library_entry",
    "LIBRARY_DIR", "ValidationReport",
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
        return load_entry(self.path)[0]


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

    def summary_line(self) -> str:
        state = "OK  " if self.ok else "FAIL"
        peak = "n/a" if self.peak_utilisation is None else f"{self.peak_utilisation:5.0%}"
        return (f"[{state}] {self.key:<28} {self.components:>2}c {self.flows}f  peak {peak}  "
                f"${self.monthly_cents // 100:>7,}/mo"
                + ("" if self.ok else "  <- " + "; ".join(self.failures)))


def validate_library_entry(path: pathlib.Path, *,
                           ceiling: float = SAFE_UTILIZATION) -> ValidationReport:
    """The gate. A blueprint that does not pass this does not belong in the library."""
    key = path.stem
    failures: list[str] = []
    try:
        model, meta = load_entry(path)
    except Exception as e:                                    # noqa: BLE001 — report, never raise
        return ValidationReport(key, False, [f"does not load: {type(e).__name__}: {e}"],
                                0, 0, None, None, 0, [])

    for field in ("category", "difficulty", "summary", "keywords"):
        if not meta.get(field):
            failures.append(f"_library.{field} is missing")
    if len(meta.get("keywords") or []) < 2:
        failures.append("needs at least 2 keywords to be findable")

    try:
        sim = simulate(model)
    except Exception as e:                                    # noqa: BLE001
        return ValidationReport(key, False, failures + [f"does not simulate: {e}"],
                                len(model.components), len(model.flows), None, None, 0, [])

    peak = sim.bottleneck_utilization
    if peak is None or peak != peak:                          # NaN guard
        failures.append("no computable peak utilisation")
    elif peak > ceiling:
        failures.append(f"already saturated as shipped: peak {peak:.0%} > {ceiling:.0%} ceiling")

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
        monthly_cents=sim.monthly_cost, unpriced=unpriced,
    )
