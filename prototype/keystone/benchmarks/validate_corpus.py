"""Corpus quality gate (docs/12 §5, QA layer 2) — the curator self-check.

Beyond the structural floor the dataclasses already enforce (citation present, band brackets
value, single-line evidence, allowed metric/unit/tier/methodology), this audits the *curation*
discipline: the confidence band must be at least as wide as the source tier allows (no false
precision), the tier's corroboration requirement must be met, and at least one citation must
carry a context note (records the measured conditions — the thing that defuses context mismatch).

Run:  python3 -m keystone.benchmarks.validate_corpus [path/to/corpus.jsonl]
Exit 0 = clean; non-zero = problems (would block a merge once wired into scripts/check.sh).
NOTE: the independent human citation-review gate (docs/12 §5 layer 3) is NOT automatable — a
reviewer must open every reference and confirm it resolves + contains the claim.
"""
from __future__ import annotations

import sys

from keystone.benchmarks.benchmark_corpus import (
    DEFAULT_CORPUS_PATH, BenchmarkDatapoint, load_corpus,
)

# Minimum relative half-width of the confidence band, by source tier (docs/12 §3) — a tighter
# band than this is unearned precision for that tier.
TIER_MIN_REL_HALFWIDTH = {"T1": 0.10, "T2": 0.15, "T3": 0.30}
# Minimum independent citations (sources) required to ground at each tier.
TIER_MIN_CITATIONS = {"T1": 1, "T2": 2, "T3": 3}
_EPS = 1e-9


def validate_datapoint(i: int, d: BenchmarkDatapoint) -> list[str]:
    tag = f"[{i}] {d.component_kind}/{d.metric}"
    problems: list[str] = []

    floor = TIER_MIN_REL_HALFWIDTH[d.source_tier]
    rel_halfwidth = ((d.confidence_high - d.confidence_low) / 2) / d.value if d.value else float("inf")
    if rel_halfwidth + _EPS < floor:
        problems.append(
            f"{tag}: band too tight for {d.source_tier} — relative half-width "
            f"{rel_halfwidth:.0%} < floor {floor:.0%} (false precision)")

    need = TIER_MIN_CITATIONS[d.source_tier]
    # Corroboration means INDEPENDENT sources — count unique (source, reference) pairs, so the
    # same source listed twice can't fake a tier's corroboration requirement.
    independent = len({(c.source, c.reference) for c in d.citations})
    if independent < need:
        problems.append(
            f"{tag}: {d.source_tier} needs >={need} independent source(s), has {independent} unique")

    if not any(c.note.strip() for c in d.citations):
        problems.append(
            f"{tag}: at least one citation must carry a note recording the measured context "
            "(hardware/workload/payload/concurrency) — this is what prevents context mismatch")

    return problems


def _context_key(d: BenchmarkDatapoint) -> tuple:
    return (d.component_kind, d.metric, d.instance_type, d.workload_shape, d.region, d.concurrency_model)


def validate_corpus(datapoints: list[BenchmarkDatapoint]) -> list[str]:
    problems: list[str] = []
    for i, d in enumerate(datapoints):
        problems.extend(validate_datapoint(i, d))
    # Contradiction gate: the same (kind, metric, FULL context) must be measured at most once — a
    # second value for an identical context is a contradiction (the matcher would silently pick one).
    groups: dict[tuple, list[int]] = {}
    for i, d in enumerate(datapoints):
        groups.setdefault(_context_key(d), []).append(i)
    for key, idxs in groups.items():
        if len(idxs) > 1:
            problems.append(
                f"contradiction: {key[0]}/{key[1]} measured {len(idxs)}× for one identical context "
                f"(datapoints {idxs}) — one context, one value; reconcile or split the context")
    return problems


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else DEFAULT_CORPUS_PATH
    try:
        datapoints = load_corpus(path)   # structural validation happens here (fail closed)
    except ValueError as e:
        print(f"❌ corpus failed to load: {e}")
        return 1
    problems = validate_corpus(datapoints)
    if problems:
        print(f"❌ {len(problems)} problem(s) in {len(datapoints)} datapoint(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"✅ corpus clean: {len(datapoints)} datapoint(s) pass the curation gates "
          "(structural + tier/band/corroboration/note). Independent citation review still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
