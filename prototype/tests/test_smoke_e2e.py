"""End-to-end smoke test for the offline loop (CLAUDE.md: the full intent -> ingest ->
council -> simulate -> report loop runs offline at $0). Prior art: Genesys keeps a
deliberate unit/smoke split (docs/13 ADOPT-NOW).

These assert STRUCTURE only -- never a metric value. The engine owns the numbers; a smoke
test that pinned a figure would both duplicate the engine's unit tests and risk re-importing
a number into the test suite. The point is: the loop runs, and the mandatory honesty section
(Doc 03) and the generated 'show your work' trace are always present.

Run from prototype/:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from keystone.blueprints import ticket_booking, url_shortener
from keystone.council import make_council
from keystone.ingestion import Source, make_ingestor, validate_model
from keystone.report import render
from keystone.simulation import simulate


class TestEndToEndSmoke(unittest.TestCase):

    def _assert_well_formed(self, md: str, name: str) -> None:
        self.assertTrue(md.startswith("# Keystone Stress-Test Report"))
        for needle in (
            f"# Keystone Stress-Test Report — {name}",
            "L0 (Directional)",
            "## Verdict",
            "## Component load",
            "## How these numbers were computed",
            "## Where this is wrong (read before trusting a number)",
        ):
            self.assertIn(needle, md, f"report is missing {needle!r}")

    def test_intent_to_report_runs_offline(self):
        # intent -> ingest (stub) -> council (stub) -> simulate -> report, all $0 / no key.
        res = make_ingestor("stub").ingest(Source(text="a url shortener with a cache and a database"))
        validate_model(res.model)                      # stub model is connected
        adrs = make_council("stub").design(res.model)
        sim = simulate(res.model)
        md = render(res.model, adrs, sim, None)
        self._assert_well_formed(md, res.model.name)

    def test_blueprint_report_shows_its_working(self):
        model = url_shortener.build()
        sim = simulate(model)
        md = render(model, make_council("stub").design(model), sim, None)
        self._assert_well_formed(md, model.name)
        # the generated derivation trace is non-empty and ordered before "where this is wrong".
        self.assertTrue(sim.derivation)
        self.assertLess(md.index("## How these numbers were computed"),
                        md.index("## Where this is wrong"))

    def test_whatif_section_renders(self):
        model = ticket_booking.build()
        sim = simulate(model)
        whatifs = [("flash sale", simulate(ticket_booking.flash_sale()))]
        md = render(model, make_council("stub").design(model), sim, whatifs)
        self._assert_well_formed(md, model.name)
        self.assertIn("## What-if interrogation", md)


if __name__ == "__main__":
    unittest.main()
