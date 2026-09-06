"""The offline fallback must never wear a matched design's identity.

Regression guard for a real honesty defect: `generate_architecture` used to
`return url_shortener.build()` when nothing matched, so asking for a video service or a bidding
exchange handed back a model literally named "URL Shortener" — and the design card, verdict, cost,
chaos catalogue and remediation plan all then presented another product's architecture as the
answer, with confident numbers attached (docs/03: the assumption behind a number travels with it).
"""
from __future__ import annotations

import unittest

from keystone.blueprints import payments, ticket_booking, twitter, url_shortener
from keystone.generate import generate_architecture, generic_starting_point, match_reference
from keystone.ingestion import validate_model
from keystone.simulation import simulate

UNMATCHED = [
    "a video streaming service",
    "a real-time bidding exchange",
    "an inventory system for a pharmacy chain",
    "something nobody has ever built before",
]
BLUEPRINT_NAMES = {b().name for b in (url_shortener.build, payments.build,
                                      ticket_booking.build, twitter.build)}


class FallbackIdentityTest(unittest.TestCase):
    def test_unmatched_intents_do_not_return_a_blueprint(self):
        for intent in UNMATCHED:
            with self.subTest(intent):
                self.assertIsNone(match_reference(intent), "fixture must not match")
                model = generate_architecture(intent, provider="stub")
                self.assertNotIn(model.name, BLUEPRINT_NAMES,
                                 "the fallback must not borrow a blueprint's identity")
                self.assertIn("no reference matched", model.name.lower())

    def test_no_component_is_named_after_a_specific_product(self):
        """Component names leak identity too — 'URL Cache' in a video-service design is the same bug."""
        model = generic_starting_point("a video streaming service")
        blob = " ".join(c.name.lower() for c in model.components.values())
        for word in ("url", "tweet", "shorten", "booking", "payment", "checkout"):
            self.assertNotIn(word, blob, f"generic components must not mention {word!r}")

    def test_matched_intents_still_get_their_real_blueprint(self):
        for intent, expected in (("a platform like Twitter", twitter.build),
                                 ("an online store checkout", payments.build),
                                 ("a url shortener", url_shortener.build)):
            with self.subTest(intent):
                self.assertEqual(generate_architecture(intent, provider="stub").name,
                                 expected().name)


class FallbackHonestyTest(unittest.TestCase):
    def test_the_gap_is_declared_on_the_model_itself(self):
        """Not in the chrome — in the assumptions, which travel into the report and the rail."""
        model = generic_starting_point("a video streaming service")
        gaps = [a for a in model.assumptions if a.provenance == "GAP"]
        self.assertGreaterEqual(len(gaps), 2)
        design = next(a for a in gaps if a.subject == "design")
        self.assertIn("not a design of what you asked for", design.statement.lower())
        self.assertIn("placeholder", design.statement.lower())

    def test_the_asked_for_intent_is_quoted_back(self):
        model = generic_starting_point("a real-time bidding exchange")
        self.assertIn("real-time bidding exchange",
                      " ".join(a.statement for a in model.assumptions))

    def test_the_placeholder_workload_is_declared(self):
        model = generic_starting_point("anything")
        workload = next(a for a in model.assumptions if a.subject == "workload")
        self.assertEqual(workload.provenance, "GAP")
        self.assertIn("placeholder", workload.statement.lower())


class FallbackIsUsableTest(unittest.TestCase):
    def test_it_is_a_valid_simulatable_model(self):
        model = generic_starting_point("anything")
        validate_model(model)                      # fail-closed: must not raise
        result = simulate(model)
        self.assertGreater(result.monthly_cost, 0)
        self.assertTrue(result.bottleneck_name)

    def test_it_is_deterministic(self):
        a, b = generic_starting_point("x"), generic_starting_point("x")
        self.assertEqual(simulate(a).monthly_cost, simulate(b).monthly_cost)

    def test_it_holds_at_its_own_placeholder_load(self):
        """A starting point that is already broken is not a starting point."""
        result = simulate(generic_starting_point("anything"))
        self.assertLess(result.bottleneck_utilization, 0.85)


if __name__ == "__main__":
    unittest.main()
