"""Curated benchmark corpus (docs/12 §4, ADR-006) — the `curated` KB provider.

A `BenchmarkDatapoint` is one cited, context-keyed measurement. They live in a git-tracked
JSONL file (one datapoint per line — clean diffs, human review, $0, stdlib `json`). The
`CuratedKnowledgeBase` loads them and grounds a value ONLY when the query's context matches a
datapoint's measured context — otherwise it returns None and the caller keeps the value as
ASSUMPTION (the safe direction; never force a benchmark from the wrong hardware/workload).

No real data ships yet: the default corpus is absent → grounds nothing (honest L0). Curating
real datapoints goes through the QA gate (validate_corpus + independent citation review).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from keystone.model import ComponentKind
from keystone.provenance import (
    GROUNDABLE_UNITS, Citation, Grounding, require_groundable_metric,
)

METHODOLOGIES = frozenset({
    "vendor_datasheet", "load_test_synthetic", "load_test_realistic", "production_metric", "paper",
})
SOURCE_TIERS = frozenset({"T1", "T2", "T3"})
_KINDS = frozenset(k.value for k in ComponentKind)
# Context dimensions a query can constrain; a datapoint only matches if every dim the query
# names equals the datapoint's (an unset datapoint dim does NOT match a specific query value).
CONTEXT_DIMS = ("instance_type", "workload_shape", "region", "concurrency_model")

DEFAULT_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "corpus.jsonl")


@dataclass(frozen=True)
class BenchmarkDatapoint:
    component_kind: str          # a ComponentKind value
    metric: str                  # in GROUNDABLE_METRICS
    value: float
    unit: str                    # in GROUNDABLE_UNITS
    confidence_low: float
    confidence_high: float
    citations: tuple[Citation, ...]
    methodology: str             # in METHODOLOGIES
    measured_date: str           # ISO YYYY-MM-DD
    source_tier: str             # T1 | T2 | T3
    instance_type: str = ""      # --- match context (the "why this number") ---
    workload_shape: str = ""
    region: str = ""
    config_notes: str = ""
    concurrency_model: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "citations", tuple(self.citations))
        require_groundable_metric(self.metric)
        if self.component_kind not in _KINDS:
            raise ValueError(f"unknown component_kind {self.component_kind!r}")
        if self.unit not in GROUNDABLE_UNITS:
            raise ValueError(f"unit {self.unit!r} not in {sorted(GROUNDABLE_UNITS)}")
        if self.methodology not in METHODOLOGIES:
            raise ValueError(f"methodology {self.methodology!r} not in {sorted(METHODOLOGIES)}")
        if self.source_tier not in SOURCE_TIERS:
            raise ValueError(f"source_tier {self.source_tier!r} not in {sorted(SOURCE_TIERS)}")
        if not (isinstance(self.measured_date, str) and len(self.measured_date) == 10
                and self.measured_date[4] == "-" and self.measured_date[7] == "-"):
            raise ValueError(f"measured_date must be ISO YYYY-MM-DD, got {self.measured_date!r}")
        if not self.citations:
            raise ValueError("a BenchmarkDatapoint needs >=1 citation")
        self.to_grounding()   # validates value/band (finite, non-negative, brackets) via the contract

    def to_grounding(self) -> Grounding:
        # Surface the MEASURED context (hardware / workload / region / concurrency) so a reader can judge
        # whether this evidence fits their setup. Display-only — does not affect the value/band/matching.
        ctx = " · ".join(p.strip() for p in (self.instance_type, self.workload_shape, self.region,
                                             self.concurrency_model) if p and p.strip())
        return Grounding(value=self.value, unit=self.unit, confidence_low=self.confidence_low,
                         confidence_high=self.confidence_high, citations=self.citations,
                         measured_context=ctx[:200])

    def context_matches(self, context: dict | None) -> bool:
        if not context:
            return True
        for dim in CONTEXT_DIMS:
            want = context.get(dim)
            if want and getattr(self, dim) != want:
                return False
        return True


def _parse_datapoint(d: dict) -> BenchmarkDatapoint:
    cites = tuple(Citation(source=c["source"], reference=c["reference"], note=c.get("note", ""))
                  for c in d["citations"])
    return BenchmarkDatapoint(
        component_kind=d["component_kind"], metric=d["metric"], value=float(d["value"]),
        unit=d["unit"], confidence_low=float(d["confidence_low"]),
        confidence_high=float(d["confidence_high"]), citations=cites,
        methodology=d["methodology"], measured_date=d["measured_date"], source_tier=d["source_tier"],
        instance_type=d.get("instance_type", ""), workload_shape=d.get("workload_shape", ""),
        region=d.get("region", ""), config_notes=d.get("config_notes", ""),
        concurrency_model=d.get("concurrency_model", ""))


def load_corpus(path: str) -> list[BenchmarkDatapoint]:
    """Load datapoints from a JSONL file. Missing file → [] (honest: no corpus, grounds nothing).
    A malformed line raises with its line number (fail closed — never load a half-broken corpus)."""
    if not os.path.exists(path):
        return []
    out: list[BenchmarkDatapoint] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(_parse_datapoint(json.loads(raw)))
            except (ValueError, KeyError, TypeError) as e:
                raise ValueError(f"{os.path.basename(path)}:{lineno}: invalid datapoint — {e}") from e
    return out


class CuratedKnowledgeBase:
    """Grounds a value from the curated corpus only when context matches; else returns None.
    Refuses to guess on an ambiguous match (multiple candidates, no disambiguating context)."""

    def __init__(self, datapoints: list[BenchmarkDatapoint]) -> None:
        self._dp = list(datapoints)

    @classmethod
    def from_file(cls, path: str) -> "CuratedKnowledgeBase":
        return cls(load_corpus(path))

    @classmethod
    def from_default_corpus(cls) -> "CuratedKnowledgeBase":
        return cls.from_file(DEFAULT_CORPUS_PATH)

    def __len__(self) -> int:
        return len(self._dp)

    def ground(self, kind: ComponentKind, metric: str, *,
               context: dict | None = None) -> Grounding | None:
        require_groundable_metric(metric)   # prime directive at the seam
        if context:
            unknown = set(context) - set(CONTEXT_DIMS)
            if unknown:
                raise ValueError(f"unknown context dimension(s) {sorted(unknown)}; allowed: {CONTEXT_DIMS}")
        cands = [d for d in self._dp
                 if d.component_kind == kind.value and d.metric == metric and d.context_matches(context)]
        if not cands:
            return None
        # CONTEXT-SPECIFICITY tiering (v2): prefer the candidate whose context is CLOSEST to the query —
        # the fewest SET context dims the query did NOT name. So a NO-context query picks the GENERIC
        # (context-free) datapoint, NOT a tighter vendor/instance-specific one; a query naming a context
        # (e.g. instance_type="stripe") picks the matching specific datapoint. Backward-compatible: with one
        # datapoint per kind+metric (today's corpus) the best tier is trivially that single datapoint.
        # CURATION INVARIANT (read before adding vendor #2): "generic" here means "fewest SET context dims",
        # not a separate flag. A no-context query prefers the candidate with the lowest _extra, so a
        # context-SPECIFIC (e.g. vendor) datapoint MUST carry strictly MORE set context dims than the
        # generic blend for that kind+metric — else a no-context query could tie on specificity and route to
        # the vendor's narrower band (or refuse on disjoint bands). E.g. the external_api generic carries 2
        # dims and stripe carries 3. test_grounding_seam.test_untagged_external_api_still_grounds_generic_blend
        # pins this; keep that green when curating a second vendor.
        # Count a dim as "named" only if it carries a NON-EMPTY value — matching context_matches(),
        # which ignores a falsy `want`. Otherwise a no-op key like {"region": ""} (how an UNSET dim
        # serialises off a Component) would discount that dim and wrongly collapse the tier, pulling in
        # a tighter specific band a context-free query never asked for.
        named = {dim for dim, want in (context or {}).items() if want}
        def _extra(d):
            return sum(1 for dim in CONTEXT_DIMS if getattr(d, dim) and dim not in named)
        best_specificity = min(_extra(d) for d in cands)
        tier = [d for d in cands if _extra(d) == best_specificity]
        if len(tier) > 1:
            # Multiple candidates at the SAME (best) specificity. Safe to ground only if they AGREE — all
            # bands overlap (corroborating). If any pair is disjoint, the query failed to disambiguate
            # genuinely different contexts at this tier → refuse to guess and stay ASSUMPTION (same-context
            # contradictions are caught earlier, by validate_corpus). The tightest (most precise) band wins.
            if max(c.confidence_low for c in tier) > min(c.confidence_high for c in tier):
                return None
        return min(tier, key=lambda d: d.confidence_high - d.confidence_low).to_grounding()
