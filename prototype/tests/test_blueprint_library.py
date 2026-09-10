"""The blueprint library: reference architectures as DATA, gated by the engine.

The gate is the point. A library entry is not "a JSON file someone wrote" — it is a design the
deterministic engine has confirmed simulates, holds at its own design load, and carries grounded
prices. These tests run that gate over everything in the library, so a bad blueprint cannot ship.
"""
from __future__ import annotations

import json
import unittest

from keystone.blueprint_library import (
    LIBRARY_DIR, byte_gaps, keyword_collisions, library, load_entry, match,
    validate_library_entry,
)
from keystone.generate import match_reference
from keystone.pricing_catalogue import KINDS_WITHOUT_PER_INSTANCE_PRICE
from keystone.simulation import SAFE_UTILIZATION, simulate


class LibraryGateTest(unittest.TestCase):
    """Every shipped blueprint must pass the gate. This is the guard that gives the library value."""

    def test_the_library_is_not_empty(self):
        self.assertTrue(library(), "no blueprints found — the library should ship content")

    def test_every_blueprint_passes_the_engine_gate(self):
        for entry in library():
            with self.subTest(entry.key):
                report = validate_library_entry(entry.path)
                self.assertTrue(report.ok, f"{entry.key}: " + "; ".join(report.failures))

    def test_every_blueprint_holds_at_its_own_design_load(self):
        """A reference architecture that ships saturated is a bug people will copy."""
        for entry in library():
            with self.subTest(entry.key):
                result = simulate(entry.build())
                self.assertLessEqual(result.bottleneck_utilization, SAFE_UTILIZATION)

    def test_every_priceable_component_is_priced(self):
        for entry in library():
            model = entry.build()
            for comp in model.components.values():
                if comp.kind.value in KINDS_WITHOUT_PER_INSTANCE_PRICE:
                    continue
                with self.subTest(f"{entry.key}.{comp.id}"):
                    self.assertGreater(comp.monthly_cost_per_instance, 0,
                                       "a reference design must not report a free component")

    def test_no_blueprint_reports_zero_cost(self):
        for entry in library():
            with self.subTest(entry.key):
                self.assertGreater(simulate(entry.build()).monthly_cost, 0)


class MetadataTest(unittest.TestCase):
    def test_every_entry_carries_findable_metadata(self):
        for entry in library():
            with self.subTest(entry.key):
                self.assertTrue(entry.summary.strip())
                self.assertGreaterEqual(len(entry.keywords), 2)
                self.assertIn(entry.difficulty, ("beginner", "intermediate", "advanced", "unknown"))

    def test_keys_are_unique_and_file_backed(self):
        keys = [e.key for e in library()]
        self.assertEqual(len(keys), len(set(keys)))
        for entry in library():
            self.assertTrue(entry.path.is_file())

    def test_every_file_is_a_valid_spec_that_round_trips(self):
        for path in sorted(LIBRARY_DIR.glob("*.json")):
            with self.subTest(path.name):
                model, meta = load_entry(path)
                self.assertTrue(model.components)
                self.assertIsInstance(meta, dict)


class MatchingTest(unittest.TestCase):
    def test_matching_is_deterministic(self):
        for entry in library():
            with self.subTest(entry.key):
                phrase = entry.keywords[0]
                self.assertEqual(match(phrase), match(phrase))

    def test_each_entry_is_reachable_by_its_own_keywords(self):
        """A blueprint nobody can find is not in the library in any useful sense.

        This test USED TO ASSERT ONLY `assertIsNotNone`, and was green over ten entries whose own
        keywords resolved to a DIFFERENT blueprint — "x clone" in twitter_clone.json swallowing
        "a netflix clone", bare "rag" firing inside "sto-rag-e". Asserting that *something* matched
        is not a reachability test; it has to assert the WINNER.
        """
        for entry in library():
            for kw in entry.keywords:
                with self.subTest(f"{entry.key} <- {kw}"):
                    winner = match(f"I want to build {kw}")
                    self.assertIsNotNone(winner, f"{entry.key}: own keyword {kw!r} matches nothing")
                    self.assertEqual(winner.key, entry.key,
                                     f"{entry.key}: own keyword {kw!r} resolves to {winner.key}")

    def test_no_keyword_collisions_across_the_library(self):
        """A too-generic keyword in one file silently hijacks another author's entry."""
        collisions = keyword_collisions()
        self.assertEqual(collisions, {}, f"keywords resolve to the wrong blueprint: {collisions}")

    def test_the_confirmed_substring_hijacks_stay_fixed(self):
        """Each of these shipped a wrong answer before the audit caught it."""
        for phrase, expected in (("a netflix clone", "video_streaming"),
                                 ("a tool like telegram", "realtime_chat"),
                                 ("an uber clone", "ride_sharing")):
            with self.subTest(phrase):
                winner = match(phrase)
                self.assertIsNotNone(winner, phrase)
                self.assertEqual(winner.key, expected)

    def test_intents_described_rather_than_named_still_match(self):
        """The flagship was findable only by people who already knew the word 'bitly'."""
        for phrase, expected in (("i want to shorten urls", "url_shortener"),
                                 ("a ci pipeline for our monorepo", "ci_cd"),
                                 ("a parking app", "parking_lot")):
            with self.subTest(phrase):
                winner = match(phrase)
                self.assertIsNotNone(winner, f"{phrase!r} matches nothing")
                self.assertEqual(winner.key, expected)

    def test_an_unrelated_intent_matches_nothing(self):
        self.assertIsNone(match("a recipe for banana bread with walnuts"))

    def test_generate_prefers_the_hand_built_deep_blueprints(self):
        """The library must not shadow the richer hand-written references."""
        matched = match_reference("a platform like Twitter")
        self.assertIsNotNone(matched)
        self.assertEqual(matched[1], "social platform")

    def test_generate_falls_through_to_the_library(self):
        matched = match_reference("I need a bitly clone")
        self.assertIsNotNone(matched)


class LibraryFileHygieneTest(unittest.TestCase):
    def test_files_are_stable_json_with_a_library_block(self):
        for path in sorted(LIBRARY_DIR.glob("*.json")):
            with self.subTest(path.name):
                payload = json.loads(path.read_text(encoding="utf8"))
                self.assertIn("_library", payload)
                self.assertIn("spec_version", payload)


if __name__ == "__main__":
    unittest.main()


class ByteGapDisclosureTest(unittest.TestCase):
    """An incomplete cost must reach the REPORT, not just the validator's console output."""

    def test_every_gate_warning_is_declared_on_the_model_it_came_from(self):
        """Every byte gap the gate finds must be declared on the model. SUBSET, not equality.

        This asserted `count(GAP assumptions) == count(byte_gaps())`, which was true only while
        `byte_gaps()` was the ONLY thing that could ever produce a GAP. The moment authors started
        declaring other honest shortfalls — "this design does not model the ledger", "media delivery
        is out of scope" — the test turned an equality into a PROHIBITION on disclosure: ten
        blueprints went red for saying MORE about what they do not cover.

        CLAUDE.md makes GAP the correct provenance for any "state shortfall + fix", not just a byte
        volume. So the test was wrong, not the blueprints. Fixing it by downgrading those
        assumptions to ASSUMPTION would have bought a green suite by deleting disclosures, which is
        the exact trade this repo exists to refuse.

        What actually has to hold: the gate and the report never disagree about a byte gap. Every
        warning the gate raises appears on the model. Extra GAPs are a feature.
        """
        for entry in library():
            with self.subTest(entry.key):
                warnings = validate_library_entry(entry.path).warnings
                declared = [a.statement for a in entry.build().assumptions
                            if a.provenance == "GAP"]
                for w in warnings:
                    self.assertIn(w, declared,
                                  f"{entry.key}: the gate warns about this and the model does not "
                                  f"declare it — {w[:90]}")

    def test_the_disclosure_survives_into_the_rendered_report(self):
        """The end the user actually reads. Asserting on the model would not prove this."""
        from keystone.report import render
        from keystone.simulation import simulate
        entry = next(e for e in library() if e.key == "video_streaming")
        model = entry.build()
        text = render(model, [], simulate(model))
        self.assertIn("COST IS A FLOOR", text)
        self.assertIn("| GAP |", text)

    def test_a_blueprint_that_declares_its_bytes_gets_no_gap(self):
        """The guard must stay silent on a complete design, or it is noise nobody reads."""
        entry = next(e for e in library() if e.key == "video_streaming")
        model = entry.build()
        for comp in model.components.values():
            if comp.kind.value in ("cdn", "object_store"):
                comp.egress_gb_per_month = 1_000_000
        self.assertEqual(byte_gaps(model), [])
