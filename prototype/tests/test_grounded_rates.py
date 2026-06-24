"""The cost RATES are grounded against `benchmarks/grounded_pricing_rates.json` (researched + 3x
adversarially verified, 2026-06-23). This test ties the engine's seed values to that evidence record so
the two cannot silently drift apart, and checks the record's own integrity (bands bracket the central,
each rate carries enough independent citations for its tier). Provenance: AI proposes, Bifola ratifies."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import keystone.benchmarks as _bench
from keystone.model import COMPUTE_PRICING_RETAINED_BP, PricingRates

_EVIDENCE = Path(_bench.__file__).parent / "grounded_pricing_rates.json"
_TIER_MIN_CITATIONS = {"T1": 1, "T2": 2, "T3": 3}


class TestGroundedRates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(_EVIDENCE.read_text())
        cls.rates = {r["id"]: r for r in cls.doc["rates"]}

    def test_pricing_rates_seed_values_match_evidence(self):
        pr = PricingRates()
        actual = {
            "egress": pr.egress_micro_usd_per_gb,
            "storage": pr.storage_micro_usd_per_gb_month,
            "requests": pr.request_micro_usd_per_thousand,
            "llm_input": pr.llm_input_micro_usd_per_1k_tokens,
            "llm_output": pr.llm_output_micro_usd_per_1k_tokens,
        }
        for rid, val in actual.items():
            self.assertEqual(val, self.rates[rid]["engine_value"],
                             f"{rid}: PricingRates default {val} != grounded {self.rates[rid]['engine_value']}")

    def test_discount_basis_points_match_evidence(self):
        for rid in ("reserved_1yr", "reserved_3yr", "spot"):
            self.assertEqual(COMPUTE_PRICING_RETAINED_BP[rid], self.rates[rid]["engine_value"], rid)

    def test_bands_bracket_the_central(self):
        for rid, r in self.rates.items():
            lo, hi = r["engine_band"]
            self.assertLessEqual(lo, r["engine_value"], f"{rid}: band low above central")
            self.assertLessEqual(r["engine_value"], hi, f"{rid}: band high below central")

    def test_each_rate_meets_its_tier_citation_floor(self):
        for rid, r in self.rates.items():
            unique = {(c["source"], c["url"]) for c in r["citations"]}
            need = _TIER_MIN_CITATIONS[r["tier"]]
            self.assertGreaterEqual(len(unique), need,
                                    f"{rid} ({r['tier']}) needs >={need} independent sources, has {len(unique)}")

    def test_every_citation_resolves_to_a_url_and_quote(self):
        # Guards against a citation that was dropped to a bare claim (an unresolvable citation is invented).
        for rid, r in self.rates.items():
            for c in r["citations"]:
                self.assertTrue(c["url"].startswith("http"), f"{rid}: citation without a URL: {c}")
                self.assertTrue(c["quoted"].strip(), f"{rid}: citation without a quoted number: {c}")

    def test_all_eight_rates_present(self):
        self.assertEqual(set(self.rates), {
            "egress", "storage", "requests", "llm_input", "llm_output",
            "reserved_1yr", "reserved_3yr", "spot",
        })


if __name__ == "__main__":
    unittest.main()
