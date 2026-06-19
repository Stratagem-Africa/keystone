"""Tests for the Knowledge Base scaffold (ADR-006).

These lock the trust contract — *no GROUNDED without a resolvable citation* — and the
stub-default/$0 behaviour, so the L0→L1 lever can't later regress into dishonest grounding.
Deterministic; no LLM, no network.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from keystone.knowledge_base import (
    Citation, EmptyKnowledgeBase, Grounding, KnowledgeBase, make_knowledge_base,
)
from keystone.model import ComponentKind


class TestStubAndFactory(unittest.TestCase):
    def test_default_factory_is_the_empty_stub(self):
        kb = make_knowledge_base()
        self.assertIsInstance(kb, EmptyKnowledgeBase)
        self.assertIsInstance(kb, KnowledgeBase)  # satisfies the protocol

    def test_stub_grounds_nothing(self):
        kb = make_knowledge_base("stub")
        for kind in ComponentKind:
            for metric in ("per_instance_rps", "base_latency_ms", "monthly_cost_per_instance"):
                self.assertIsNone(kb.ground(kind, metric),
                                  f"stub must ground nothing, but grounded {kind}/{metric}")

    def test_unbuilt_providers_are_gated(self):
        for p in ("curated", "rag"):
            with self.assertRaises(NotImplementedError):
                make_knowledge_base(p)

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError):
            make_knowledge_base("bogus")

    def test_stub_refuses_to_ground_a_derived_metric(self):
        # prime directive at the seam: you may not even ASK the KB for a derived metric
        kb = make_knowledge_base("stub")
        for derived in ("utilization", "bottleneck", "breakpoint_rps", "p99_latency_ms", "cost_estimate"):
            with self.assertRaises(ValueError):
                kb.ground(ComponentKind.APP_SERVER, derived)


class TestGroundingHonestyContract(unittest.TestCase):
    """The core rule: a GROUNDED value is structurally impossible without evidence."""

    def _cite(self):
        return Citation(source="AWS r7g.large pgbench", reference="https://example.com/benchmark/123")

    def test_grounding_requires_at_least_one_citation(self):
        with self.assertRaises(ValueError):
            Grounding(value=8000, unit="rps", confidence_low=6000, confidence_high=10000, citations=[])

    def test_citation_requires_source_and_resolvable_reference(self):
        with self.assertRaises(ValueError):
            Citation(source="", reference="https://x")
        with self.assertRaises(ValueError):
            Citation(source="benchmark", reference="   ")

    def test_grounding_rejects_non_grounded_provenance(self):
        with self.assertRaises(ValueError):
            Grounding(value=1, unit="rps", confidence_low=0, confidence_high=2,
                      citations=[self._cite()], provenance="ASSUMPTION")

    def test_grounding_rejects_non_finite_values(self):
        for bad in (float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                Grounding(value=bad, unit="rps", confidence_low=0, confidence_high=1, citations=[self._cite()])

    def test_confidence_band_must_bracket_the_value(self):
        with self.assertRaises(ValueError):
            Grounding(value=100, unit="rps", confidence_low=200, confidence_high=300, citations=[self._cite()])

    def test_valid_grounding_constructs_and_carries_evidence(self):
        g = Grounding(value=8000, unit="rps", confidence_low=6000, confidence_high=10000,
                      citations=[self._cite()])
        self.assertEqual(g.provenance, "GROUNDED")
        self.assertEqual(len(g.citations), 1)
        self.assertTrue(g.citations[0].reference)

    def test_citations_cannot_be_emptied_after_construction(self):
        # the evidence contract must survive post-construction mutation attempts
        g = Grounding(value=8000, unit="rps", confidence_low=6000, confidence_high=10000,
                      citations=[self._cite()])
        self.assertIsInstance(g.citations, tuple)        # normalised to an immutable tuple
        with self.assertRaises(AttributeError):
            g.citations.clear()                          # tuple has no .clear()

    def test_replace_cannot_void_the_evidence_contract(self):
        # dataclasses.replace re-runs __post_init__, so the contract is re-checked
        g = Grounding(value=8000, unit="rps", confidence_low=6000, confidence_high=10000,
                      citations=[self._cite()])
        with self.assertRaises(ValueError):
            replace(g, citations=())

    def test_negative_grounded_value_rejected(self):
        with self.assertRaises(ValueError):
            Grounding(value=-100, unit="rps", confidence_low=-200, confidence_high=-50,
                      citations=[self._cite()])

    def test_citation_note_must_be_single_line_string(self):
        with self.assertRaises(ValueError):
            Citation(source="s", reference="https://x", note="line1\nline2")  # newline → markdown-forgery surface
        with self.assertRaises(TypeError):
            Citation(source="s", reference="https://x", note=None)


if __name__ == "__main__":
    unittest.main()
