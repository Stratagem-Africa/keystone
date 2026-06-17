"""Tests for the Ticket Booking blueprint (case #2) + its flash-sale what-if (F6)."""
from __future__ import annotations

import unittest

from keystone.blueprints import ticket_booking
from keystone.benchmarks import syssimulator_blueprints as corpus
from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.ingestion import validate_model  # reuse the fail-closed structural validator
from keystone.simulation import simulate


class TestTicketBookingModel(unittest.TestCase):
    def test_model_is_structurally_valid(self):
        validate_model(ticket_booking.build())  # does not raise

    def test_matches_corpus_shape(self):
        truth = {b[0]: b for b in corpus.BLUEPRINTS}["ticket_booking"]
        _, _, category, comps_truth, lo, hi, in_scope = truth
        model = ticket_booking.build()
        self.assertEqual(category, "event_driven")
        self.assertTrue(in_scope)
        self.assertEqual(len(model.components), comps_truth)   # 8 components
        # baseline compute cost lands inside the documented band
        self.assertTrue(lo <= simulate(model).monthly_cost <= hi)

    def test_baseline_bottleneck_is_app_tier(self):
        sim = simulate(ticket_booking.build())
        self.assertEqual(sim.bottleneck_id, "app")
        self.assertLess(sim.bottleneck_utilization, 1.0)   # not saturated at steady state


class TestFlashSaleWhatIf(unittest.TestCase):
    """F6: the flash-sale spike must shift the bottleneck to the seat-inventory DB."""

    def test_flash_sale_shifts_bottleneck_to_inventory_db(self):
        baseline = simulate(ticket_booking.build())
        flash = simulate(ticket_booking.flash_sale(system_rps=40_000, book_share=0.5))
        self.assertEqual(baseline.bottleneck_id, "app")
        self.assertEqual(flash.bottleneck_id, "db", "flash sale should melt the inventory DB")
        self.assertGreater(flash.bottleneck_utilization, 1.0)   # saturated
        # the safe breakpoint collapses under the booking spike
        self.assertLess(flash.breakpoint_rps_safe, baseline.breakpoint_rps_safe)

    def test_book_share_drives_write_pressure(self):
        # more booking share -> higher inventory-DB utilisation at the same load
        low = simulate(ticket_booking.build(system_rps=10_000, book_share=0.05))
        high = simulate(ticket_booking.build(system_rps=10_000, book_share=0.5))
        self.assertGreater(high.components["db"].utilization, low.components["db"].utilization)


class TestRegisteredForScoring(unittest.TestCase):
    def test_in_reference_models(self):
        self.assertIn("ticket_booking", [k for k, _, _ in REFERENCE_MODELS])


if __name__ == "__main__":
    unittest.main()
