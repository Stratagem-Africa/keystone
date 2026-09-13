"""The grounded compute-price catalogue.

The guards that matter are honesty guards. This corpus exists because compute was the single
largest ungrounded number in the product, and the adversarial pass that produced it REFUTED the
first attempt — the bands were one list rate re-multiplied by 672 and 744 hours, calendar arithmetic
dressed as a price range. These tests pin the corrected shape so that cannot come back.
"""
from __future__ import annotations

import json
import unittest

from keystone.model import Component, ComponentKind
from keystone.pricing_catalogue import (
    DEFAULT_CLASS, KINDS_WITHOUT_PER_INSTANCE_PRICE, catalogue, default_price_for_kind,
    grounding_for, price_for,
)


class ShapeTest(unittest.TestCase):
    def test_every_row_is_well_formed(self):
        for key, row in catalogue().items():
            with self.subTest(key):
                self.assertGreater(row.monthly_cents, 0)
                self.assertIsInstance(row.monthly_cents, int, "money stays integer (ADR-008)")
                self.assertLessEqual(row.low_cents, row.monthly_cents)
                self.assertGreaterEqual(row.high_cents, row.monthly_cents)
                self.assertTrue(row.citation_url.startswith("https://"))
                self.assertTrue(row.band_basis.strip(), "a band must say what it means")
                self.assertTrue(row.scope.strip())

    def test_keys_match_kind_and_class(self):
        for key, row in catalogue().items():
            self.assertEqual(key, f"{row.component_kind}.{row.instance_class}")

    def test_it_covers_the_kinds_that_have_instances(self):
        kinds = {r.component_kind for r in catalogue().values()}
        self.assertEqual(kinds, {"app_server", "sql_db", "replica", "cache", "queue"})


class BandHonestyTest(unittest.TestCase):
    """The refuted-first-attempt guards."""

    def test_no_band_is_calendar_arithmetic(self):
        """The original bands were central x 672/730 and x 744/730. That ratio must never return."""
        for key, row in catalogue().items():
            if row.low_cents == row.monthly_cents:
                continue                                    # zero-width is fine
            with self.subTest(key):
                ratio = row.low_cents / row.monthly_cents
                self.assertFalse(0.919 < ratio < 0.922,
                                 f"{key}: low/central = {ratio:.5f} ~ 672/730 — this is month-length "
                                 f"arithmetic wearing a band's clothes")

    def test_a_widened_band_states_a_real_deployment_spread(self):
        widened = [r for r in catalogue().values() if r.high_cents > r.monthly_cents]
        self.assertTrue(widened, "the RDS rows should carry a real Single-AZ -> Multi-AZ band")
        for row in widened:
            with self.subTest(row.key):
                self.assertIn("Multi-AZ", row.band_basis)
                self.assertEqual(row.high_cents, row.monthly_cents * 2)

    def test_zero_width_bands_name_their_out_of_band_modifiers(self):
        for row in catalogue().values():
            if row.low_cents != row.high_cents:
                continue
            with self.subTest(row.key):
                self.assertIn("zero-width", row.band_basis.lower())

    def test_burstable_classes_disclose_the_surcharge(self):
        """A t4g at sustained load can bill ~2.9x list. That must be visible, not hidden in a band."""
        for row in catalogue().values():
            if row.instance_class.startswith(("t4g.", "cache.t4g")) and row.component_kind == "app_server":
                with self.subTest(row.key):
                    self.assertIn("BURSTABLE", row.scope + row.note)
                    self.assertIn("0.04", row.note)


class RefusalTest(unittest.TestCase):
    """What the catalogue will NOT price is the most important thing in it."""

    def test_the_unpriceable_kinds_are_declared_with_reasons(self):
        for kind, why in KINDS_WITHOUT_PER_INSTANCE_PRICE.items():
            with self.subTest(kind):
                self.assertGreater(len(why), 60, f"{kind} must explain, not just refuse")

    def test_no_row_exists_for_a_kind_that_has_no_per_instance_price(self):
        """model.py multiplies monthly_cost_per_instance by instances — an ALB floor there would be
        multiplied by instance count, and CloudFront's plan is priced per distribution."""
        priced = {r.component_kind for r in catalogue().values()}
        for kind in ("api_gateway", "object_store", "cdn", "load_balancer"):
            self.assertNotIn(kind, priced, f"{kind} has no per-instance price and must not be priced")

    def test_default_lookup_returns_none_for_those_kinds(self):
        for kind in (ComponentKind.API_GATEWAY, ComponentKind.OBJECT_STORE,
                     ComponentKind.CDN, ComponentKind.LOAD_BALANCER):
            with self.subTest(kind.value):
                self.assertIsNone(default_price_for_kind(kind))


class LookupTest(unittest.TestCase):
    def test_price_for_finds_a_known_class(self):
        row = price_for(ComponentKind.APP_SERVER, "m6i.large")
        self.assertIsNotNone(row)
        self.assertEqual(row.monthly_cents, 7008)

    def test_price_for_returns_none_for_an_unknown_class(self):
        self.assertIsNone(price_for(ComponentKind.APP_SERVER, "not.a.real.class"))

    def test_every_default_class_actually_resolves(self):
        """A default that does not resolve would silently leave a component unpriced."""
        for kind, cls in DEFAULT_CLASS.items():
            with self.subTest(kind):
                self.assertIsNotNone(price_for(kind, cls), f"{kind} default {cls} is not in the corpus")

    def test_a_priced_default_can_build_a_valid_component(self):
        row = default_price_for_kind(ComponentKind.APP_SERVER)
        c = Component("x", ComponentKind.APP_SERVER, "X", per_instance_rps=1000.0,
                      monthly_cost_per_instance=row.monthly_cents)
        self.assertEqual(c.monthly_cost, row.monthly_cents)


class GroundingTest(unittest.TestCase):
    def test_grounding_carries_a_resolvable_citation_and_the_band_meaning(self):
        g = grounding_for(price_for(ComponentKind.SQL_DB, "db.r6g.large"))
        self.assertEqual(g.provenance, "GROUNDED")
        self.assertEqual(g.unit, "usd_minor_per_month")
        self.assertTrue(g.citations[0].reference.startswith("https://"))
        self.assertIn("Band:", g.measured_context)
        self.assertLessEqual(g.confidence_low, g.value)
        self.assertGreaterEqual(g.confidence_high, g.value)

    def test_the_corpus_records_what_the_adversarial_pass_changed(self):
        import pathlib
        doc = json.loads((pathlib.Path("keystone/pricing_catalogue.py").parent
                          / "benchmarks" / "compute_prices.json").read_text())
        self.assertGreaterEqual(len(doc["corrections_applied"]), 5)
        joined = " ".join(doc["corrections_applied"]).lower()
        self.assertIn("672", joined, "the refuted calendar-arithmetic band must stay on the record")
        self.assertIn("ratify", doc["_about"].lower(), "AI proposes; a human ratifies")


if __name__ == "__main__":
    unittest.main()
