"""Tests for the curated-benchmark plumbing (docs/12 Phase 1): the datapoint schema, the JSONL
loader, the context-matching CuratedKnowledgeBase, the corpus QA validator, and Component
carrying grounding evidence — plus a regression check that the shipped corpus.jsonl stays
clean. Deterministic; offline.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from keystone.benchmarks.benchmark_corpus import (
    DEFAULT_CORPUS_PATH, BenchmarkDatapoint, CuratedKnowledgeBase, load_corpus,
)
from keystone.benchmarks.validate_corpus import validate_corpus
from keystone.knowledge_base import KnowledgeBase, make_knowledge_base
from keystone.model import Component, ComponentKind
from keystone.provenance import Citation, Grounding


def _cite(note="r7g.medium, 100 clients, 1KB values, synthetic"):
    return Citation("Redis 7.0 redis-benchmark", "https://redis.io/docs/benchmarks", note=note)


def _dp(**over):
    base = dict(
        component_kind="cache", metric="per_instance_rps", value=80_000, unit="rps",
        confidence_low=68_000, confidence_high=92_000, citations=(_cite(),),
        methodology="load_test_synthetic", measured_date="2026-06-15", source_tier="T1",
        instance_type="r7g.medium", workload_shape="read_heavy", region="us-east-1",
    )
    base.update(over)
    return BenchmarkDatapoint(**base)


class TestDatapointValidation(unittest.TestCase):
    def test_valid_datapoint_and_to_grounding(self):
        g = _dp().to_grounding()
        self.assertEqual(g.provenance, "GROUNDED")
        self.assertEqual(g.value, 80_000)
        self.assertEqual(len(g.citations), 1)

    def test_rejects_bad_fields(self):
        for bad in (
            dict(metric="utilization"),          # derived metric (prime directive)
            dict(unit="banana"),                 # not an allowed unit
            dict(source_tier="T9"),              # unknown tier
            dict(methodology="vibes"),           # unknown methodology
            dict(measured_date="2026/06/15"),    # not ISO YYYY-MM-DD
            dict(component_kind="quantum_db"),   # unknown component kind
            dict(confidence_low=90_000),         # band doesn't bracket value
            dict(citations=()),                  # no evidence
        ):
            with self.assertRaises(ValueError, msg=f"should reject {bad}"):
                _dp(**bad)


class TestCorpusLoader(unittest.TestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(load_corpus("/no/such/corpus.jsonl"), [])

    def test_loads_jsonl_and_skips_blank_lines(self):
        line = json.dumps({
            "component_kind": "cache", "metric": "per_instance_rps", "value": 80000, "unit": "rps",
            "confidence_low": 68000, "confidence_high": 92000,
            "citations": [{"source": "Redis", "reference": "https://x", "note": "ctx"}],
            "methodology": "load_test_synthetic", "measured_date": "2026-06-15", "source_tier": "T1",
        })
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.jsonl")
            with open(p, "w") as fh:
                fh.write(line + "\n\n" + line + "\n")   # two datapoints + a blank line
            dps = load_corpus(p)
        self.assertEqual(len(dps), 2)

    def test_malformed_line_fails_closed_with_lineno(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.jsonl")
            with open(p, "w") as fh:
                fh.write("{not valid json}\n")
            with self.assertRaises(ValueError) as cm:
                load_corpus(p)
            self.assertIn("c.jsonl:1", str(cm.exception))


class TestCuratedMatcher(unittest.TestCase):
    def test_grounds_on_context_match(self):
        kb = CuratedKnowledgeBase([_dp()])
        g = kb.ground(ComponentKind.CACHE, "per_instance_rps", context={"instance_type": "r7g.medium"})
        self.assertIsNotNone(g)
        self.assertEqual(g.value, 80_000)

    def test_refuses_on_wrong_context(self):
        kb = CuratedKnowledgeBase([_dp()])
        self.assertIsNone(kb.ground(ComponentKind.CACHE, "per_instance_rps",
                                    context={"instance_type": "m5.large"}))

    def test_single_candidate_no_context_grounds(self):
        kb = CuratedKnowledgeBase([_dp()])
        self.assertIsNotNone(kb.ground(ComponentKind.CACHE, "per_instance_rps"))

    def test_ambiguous_no_context_refuses(self):
        kb = CuratedKnowledgeBase([_dp(workload_shape="read_heavy"),
                                   _dp(value=40_000, confidence_low=34_000, confidence_high=46_000,
                                       workload_shape="write_heavy")])
        # two contexts, nothing to disambiguate → refuse to guess
        self.assertIsNone(kb.ground(ComponentKind.CACHE, "per_instance_rps"))
        # but a disambiguating context resolves it
        g = kb.ground(ComponentKind.CACHE, "per_instance_rps", context={"workload_shape": "write_heavy"})
        self.assertEqual(g.value, 40_000)

    def test_wrong_kind_and_empty_corpus_return_none(self):
        self.assertIsNone(CuratedKnowledgeBase([_dp()]).ground(ComponentKind.SQL_DB, "per_instance_rps"))
        self.assertIsNone(CuratedKnowledgeBase([]).ground(ComponentKind.CACHE, "per_instance_rps"))

    def test_refuses_derived_metric(self):
        with self.assertRaises(ValueError):
            CuratedKnowledgeBase([_dp()]).ground(ComponentKind.CACHE, "utilization")

    def test_partial_context_with_disjoint_candidates_refuses(self):
        # both datapoints share instance_type=r7g.medium; a query that gives ONLY instance_type
        # leaves two candidates whose bands are disjoint (read vs write) → refuse, don't guess
        kb = CuratedKnowledgeBase([
            _dp(workload_shape="read_heavy"),  # [68k, 92k]
            _dp(value=40_000, confidence_low=34_000, confidence_high=46_000, workload_shape="write_heavy"),  # [34k, 46k]
        ])
        self.assertIsNone(kb.ground(ComponentKind.CACHE, "per_instance_rps",
                                    context={"instance_type": "r7g.medium"}))

    def test_partial_context_with_overlapping_candidates_grounds_tightest(self):
        # consistent (overlapping-band) measurements → safe to ground the tightest
        kb = CuratedKnowledgeBase([
            _dp(value=80_000, confidence_low=60_000, confidence_high=100_000, workload_shape="read_a"),  # wide
            _dp(value=82_000, confidence_low=74_000, confidence_high=90_000, workload_shape="read_b"),   # tight, overlaps
        ])
        g = kb.ground(ComponentKind.CACHE, "per_instance_rps", context={"instance_type": "r7g.medium"})
        self.assertEqual(g.value, 82_000)

    def test_unknown_context_dimension_rejected(self):
        with self.assertRaises(ValueError):
            CuratedKnowledgeBase([_dp()]).ground(ComponentKind.CACHE, "per_instance_rps",
                                                 context={"hardware": "r7g.medium"})  # typo'd key


class TestCorpusQAValidator(unittest.TestCase):
    def test_clean_datapoint_has_no_problems(self):
        self.assertEqual(validate_corpus([_dp()]), [])

    def test_flags_band_too_tight_for_tier(self):
        tight = _dp(confidence_low=79_000, confidence_high=81_000)  # ~1.25% half-width, T1 floor 10%
        problems = validate_corpus([tight])
        self.assertTrue(any("too tight" in p for p in problems), problems)

    def test_flags_under_corroborated_tier(self):
        t2_solo = _dp(source_tier="T2")  # T2 needs >=2 independent sources, has 1
        self.assertTrue(any("independent" in p for p in validate_corpus([t2_solo])))

    def test_flags_missing_context_note(self):
        no_note = _dp(citations=(_cite(note=""),))
        self.assertTrue(any("note" in p for p in validate_corpus([no_note])))

    def test_duplicate_source_does_not_count_as_corroboration(self):
        same = Citation("AWS r7g", "https://aws.example/r7g", note="ctx")
        faked = _dp(source_tier="T2", citations=(same, same))   # 2 citations, 1 unique source
        self.assertTrue(any("independent" in p for p in validate_corpus([faked])))

    def test_flags_same_context_contradiction(self):
        a = _dp(value=80_000, confidence_low=68_000, confidence_high=92_000)
        b = _dp(value=40_000, confidence_low=34_000, confidence_high=46_000)  # identical context, different value
        self.assertTrue(any("contradiction" in p for p in validate_corpus([a, b])))

    def test_shipped_corpus_is_clean(self):
        # Regression guard: the REAL corpus.jsonl that ships must always load + pass the curation
        # gates. (Independent human citation review is still required — docs/12 §5 layer 3.)
        dps = load_corpus(DEFAULT_CORPUS_PATH)
        self.assertGreater(len(dps), 0, "a curated corpus is shipped")
        self.assertEqual(validate_corpus(dps), [], "shipped corpus must pass the curation QA")


class TestFactoryAndComponentEvidence(unittest.TestCase):
    def test_default_provider_is_stub_and_grounds_nothing(self):
        # The DEFAULT provider is the stub: it grounds NOTHING, so every value honestly stays
        # ASSUMPTION until the curated provider is explicitly activated (Bifola's trigger).
        kb = make_knowledge_base()  # default -> stub
        self.assertIsNone(kb.ground(ComponentKind.CACHE, "monthly_cost_per_instance"))

    def test_curated_provider_loads_shipped_corpus_and_grounds(self):
        kb = make_knowledge_base("curated")
        self.assertIsInstance(kb, CuratedKnowledgeBase)
        self.assertIsInstance(kb, KnowledgeBase)        # satisfies the protocol
        # grounds a SPECIFIC cloud's cited cost (realistic usage — you name your instance/region)
        self.assertIsNotNone(kb.ground(ComponentKind.CACHE, "monthly_cost_per_instance",
                                       context={"instance_type": "cache.r6g.large"}))
        # multi-cloud safety: asked WITHOUT naming a cloud, the corpus's clouds DISAGREE (AWS ~$150
        # vs GCP ~$403), so it refuses to guess one for you rather than pick (docs/12 — refuse on a
        # poor/ambiguous match; better ASSUMPTION than a wrong number).
        self.assertIsNone(kb.ground(ComponentKind.CACHE, "monthly_cost_per_instance"))
        # app-server throughput now grounds to an honestly-WIDE band (grown corpus, 3x-verified) — the
        # band reflects the workload/framework spread rather than claiming false precision.
        app_rps = kb.ground(ComponentKind.APP_SERVER, "per_instance_rps")
        self.assertIsNotNone(app_rps)
        self.assertTrue(app_rps.confidence_low <= app_rps.value <= app_rps.confidence_high)
        # ...and still grounds NOTHING where we deliberately have no datapoint (app-server service-time
        # latency stayed ASSUMPTION — its proposal didn't survive adversarial review).
        self.assertIsNone(kb.ground(ComponentKind.APP_SERVER, "base_latency_ms"))

    def test_component_reports_grounded_per_metric(self):
        g = Grounding(80_000, "rps", 68_000, 92_000, (_cite(),))
        c = Component("cache", ComponentKind.CACHE, "Redis", per_instance_rps=80_000,
                      groundings={"per_instance_rps": g})
        self.assertEqual(c.provenance_of("per_instance_rps"), "GROUNDED")
        self.assertEqual(c.provenance_of("base_latency_ms"), "assumption")   # ungrounded → default
        # an ungrounded component is unchanged (the honest L0 default)
        self.assertEqual(Component("a", ComponentKind.APP_SERVER, "app", per_instance_rps=1).provenance_of("per_instance_rps"),
                         "assumption")


if __name__ == "__main__":
    unittest.main()
