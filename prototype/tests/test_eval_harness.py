"""Tests for the eval harness (docs/03 §4): the reconciliation eval scores planted conflicts
correctly, and the report card is HONEST — it carries the L0 disclaimer + the explicit limits
and never fabricates a latency/throughput error envelope or a single bragging accuracy number.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from keystone.benchmarks.eval_harness import (
    render_eval_report, run_eval, run_grounding_eval, run_recon_eval, score_recon_case, recon_cases,
)


class TestReconEval(unittest.TestCase):
    def test_every_planted_case_passes(self):
        # The deterministic reconciler must surface every planted conflict, halt exactly when it
        # must, and invent no hard conflict — a regression guard on F2 (docs/04).
        for s in run_recon_eval():
            self.assertTrue(s.recall_ok, f"{s.name}: missed a planted conflict (detected {set(s.detected_kinds)})")
            self.assertTrue(s.halt_ok, f"{s.name}: halt expectation mismatch")
            self.assertTrue(s.no_spurious_hard, f"{s.name}: invented a hard conflict")
            self.assertTrue(s.passed)

    def test_clean_case_detects_no_conflict_and_kind_mismatch_halts(self):
        scores = {c.name: score_recon_case(c) for c in recon_cases()}
        clean = next(s for n, s in scores.items() if "clean" in n)
        self.assertEqual(clean.detected_kinds, frozenset())   # nothing invented on a clean merge
        hard = next(s for n, s in scores.items() if "hard conflict" in n)
        self.assertIn("component-kind", hard.detected_kinds)  # the planted contradiction is caught
        self.assertTrue(hard.halt_ok)


class TestGroundingCoverageEval(unittest.TestCase):
    def test_coverage_tallies_are_consistent(self):
        cov = run_grounding_eval()
        self.assertEqual(cov.total, cov.grounded_in_band + cov.reconcile + cov.ungrounded)
        self.assertEqual(cov.evidence_backed, cov.grounded_in_band + cov.reconcile)
        self.assertGreater(cov.models, 0)
        self.assertGreater(cov.total, 0)
        self.assertGreater(cov.evidence_backed, 0)          # the grown corpus grounds SOMETHING
        self.assertGreater(cov.ungrounded, 0)               # ...but honestly far from all

    def test_report_has_honest_grounding_section(self):
        md = render_eval_report(run_eval())
        self.assertIn("## Input grounding", md)
        self.assertIn("provenance", md.lower())
        # must NOT claim it's engine-output accuracy / certification
        self.assertIn("not engine-output accuracy", md.lower())
        self.assertIn("still assumption", md.lower())        # the honest "early L1" read


class TestReportHonesty(unittest.TestCase):
    def setUp(self):
        self.md = render_eval_report(run_eval())

    def test_carries_L0_disclaimer_and_limits_section(self):
        self.assertIn("L0 (Directional)", self.md)
        self.assertIn("CANNOT say more", self.md)
        # the specific honest limits must be present — these are load-bearing (Doc 03)
        self.assertIn("no per-component error envelope", self.md)
        self.assertIn("council", self.md.lower())                 # council eval is gated, said so
        self.assertIn("prime directive", self.md.lower())

    def test_does_not_overclaim(self):
        low = self.md.lower()
        for forbidden in ("100% accurate", "pristine", "certified", "guaranteed accurate", "elite accuracy"):
            self.assertNotIn(forbidden, low, f"report must not overclaim ({forbidden!r})")

    def test_reports_fractions_not_a_single_headline_number(self):
        # scores are shown as N/M against a named dimension (e.g. '34/34'), not one bragging figure
        self.assertIn("/34", self.md)
        self.assertIn("/4", self.md)


if __name__ == "__main__":
    unittest.main()
