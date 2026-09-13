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

# Intents the library genuinely does not cover. This list is PERISHABLE by design: every blueprint
# added shrinks the space of unmatched intents, and "a video streaming service" was retired from it
# the day video_streaming.json landed — the fixture went stale, not the behaviour. When one of these
# starts matching, check WHY: a new blueprint legitimately covering it means replace the fixture; a
# too-generic keyword hijacking it means fix the keyword (see test_blueprint_library).
UNMATCHED = [
    "a real-time bidding exchange",
    "an inventory system for a pharmacy chain",
    "a scheduling tool for a hair salon",
    "something nobody has ever built before",
]
BLUEPRINT_NAMES = {b().name for b in (url_shortener.build, payments.build,
                                      ticket_booking.build, twitter.build)}


class FallbackIdentityTest(unittest.TestCase):
    def test_unmatched_intents_do_not_return_a_blueprint(self):
        for intent in UNMATCHED:
            with self.subTest(intent):
                hit = match_reference(intent)
                self.assertIsNone(hit, f"stale fixture: {intent!r} now matches "
                                       f"{hit[1] if hit else ''} — this test needs an intent the "
                                       f"library does NOT cover; pick another or fix the keyword")
                model = generate_architecture(intent, provider="stub")
                self.assertNotIn(model.name, BLUEPRINT_NAMES,
                                 "the fallback must not borrow a blueprint's identity")
                self.assertIn("no reference matched", model.name.lower())

    def test_no_component_is_named_after_a_specific_product(self):
        """Component names leak identity too — 'URL Cache' in a video-service design is the same bug."""
        model = generic_starting_point("a real-time bidding exchange")
        blob = " ".join(c.name.lower() for c in model.components.values())
        for word in ("url", "tweet", "shorten", "booking", "payment", "checkout"):
            self.assertNotIn(word, blob, f"generic components must not mention {word!r}")

    def test_matched_intents_still_get_their_real_blueprint(self):
        for intent, expected in (("a platform like Twitter", twitter.build),
                                 ("a checkout flow with stripe", payments.build),
                                 ("a url shortener", url_shortener.build)):
            with self.subTest(intent):
                self.assertEqual(generate_architecture(intent, provider="stub").name,
                                 expected().name)


class MatcherIdentityTest(unittest.TestCase):
    """The same identity leak the fallback guards, arriving through the MATCHER instead.

    A too-broad tier-1 trigger is not a missed opportunity — it is a wrong answer, and a confident
    one. `"instagram"` used to return the Twitter blueprint, so the design handed back contained a
    component literally called "Tweet Service"; `"an online store"` used to return the 5-component
    payments design, which models no catalogue, no cart and no inventory. Both had a dedicated,
    engine-gated library blueprint sitting unused behind the shadowing trigger.
    """

    def test_an_intent_gets_the_blueprint_for_ITS_product(self):
        for intent, expected in (("an instagram clone", "Instagram Clone"),
                                 ("a photo sharing app", "Instagram Clone"),
                                 ("an online store", "E-Commerce Platform"),
                                 ("a storefront for my shop", "E-Commerce Platform"),
                                 ("an ecommerce site", "E-Commerce Platform")):
            with self.subTest(intent):
                hit = match_reference(intent)
                self.assertIsNotNone(hit, f"{intent!r} matches nothing")
                self.assertEqual(hit[1], expected)

    def test_tier_one_keeps_the_intents_it_is_genuinely_deepest_for(self):
        """Narrowing must not go too far the other way — these are the 20-component worked cases."""
        for intent, expected in (("a platform like twitter", "social platform"),
                                 ("a payment system", "payments / checkout"),
                                 ("stripe billing", "payments / checkout"),
                                 ("a url shortener", "URL shortener")):
            with self.subTest(intent):
                hit = match_reference(intent)
                self.assertIsNotNone(hit, f"{intent!r} matches nothing")
                self.assertEqual(hit[1], expected)

    def test_no_matched_design_contains_another_products_component(self):
        """The check that would have caught this: read the COMPONENTS, not just the label."""
        for intent, forbidden in (("an instagram clone", ("tweet", "shorten")),
                                  ("an online store", ("tweet", "shorten")),
                                  ("a url shortener", ("tweet", "seat"))):
            with self.subTest(intent):
                model = generate_architecture(intent, provider="stub")
                blob = " ".join(c.name.lower() for c in model.components.values())
                for word in forbidden:
                    self.assertNotIn(word, blob,
                                     f"{intent!r} returned a design mentioning {word!r}")


class FallbackHonestyTest(unittest.TestCase):
    def test_the_gap_is_declared_on_the_model_itself(self):
        """Not in the chrome — in the assumptions, which travel into the report and the rail."""
        model = generic_starting_point("a real-time bidding exchange")
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
