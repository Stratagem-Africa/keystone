"""The grounding seam (`keystone.grounding.enrich`) — ADR-006 L0→L1 wiring.

Locks the trust-critical guarantees: (1) under the stub KB it is a strict no-op (engine + report
byte-identical); (2) in default/evidence-only mode it NEVER moves a value, so the engine output is
identical (the prime-directive proof); (3) it only ever probes the 3 INPUT metrics; (4) the curated
corpus produces the honest mixed report (in-band GROUNDED + out-of-band RECONCILE, value kept);
(5) override is opt-in and money stays integer cents.
"""
from __future__ import annotations

import unittest

from keystone.benchmarks.benchmark_corpus import CuratedKnowledgeBase
from keystone.blueprints import url_shortener
from keystone.grounding import enrich
from keystone.knowledge_base import EmptyKnowledgeBase
from keystone.provenance import GROUNDABLE_METRICS
from keystone.report import render
from keystone.council import make_council
from keystone.simulation import simulate


def _curated() -> CuratedKnowledgeBase:
    return CuratedKnowledgeBase.from_default_corpus()


def _find(res, cid, metric):
    return next((g for g in res.groundings if g.component_id == cid and g.metric == metric), None)


def _engine_numbers(sim):
    return (sim.monthly_cost, tuple(sorted(sim.cost_breakdown.items())), sim.bottleneck_id,
            sim.bottleneck_utilization, sim.breakpoint_rps_safe, sim.breakpoint_rps_theoretical,
            sim.mean_latency_ms, sim.p50_ms, sim.p95_ms, sim.p99_ms)


class TestGroundingSeam(unittest.TestCase):
    def test_stub_enrich_is_strict_identity(self):
        m = url_shortener.build()
        res = enrich(m, EmptyKnowledgeBase())
        self.assertIs(res.model, m)                # same object — no copy made
        self.assertEqual(res.groundings, [])
        self.assertFalse(any(c.groundings for c in res.model.components.values()))

    def test_default_mode_leaves_engine_output_identical(self):
        # The prime-directive proof: attaching evidence must not move any number the engine computes.
        m = url_shortener.build()
        before = simulate(m)
        after = simulate(enrich(m, _curated()).model)   # evidence-only (override defaults False)
        self.assertEqual(_engine_numbers(before), _engine_numbers(after))

    def test_stub_report_has_no_grounding_section(self):
        m = enrich(url_shortener.build(), EmptyKnowledgeBase()).model
        md = render(m, make_council().design(m), simulate(m))
        self.assertNotIn("## Grounding", md)

    def test_enrich_only_probes_groundable_metrics(self):
        # A spy KB records every metric asked; the seam must never request a derived metric.
        asked: list[str] = []

        class Spy:
            def ground(self, kind, metric, *, context=None):
                asked.append(metric)
                return None

        enrich(url_shortener.build(), Spy())
        self.assertTrue(asked)                                  # it did probe
        self.assertTrue(set(asked) <= GROUNDABLE_METRICS)       # only input metrics

    def test_curated_attaches_and_classifies_in_and_out_of_band(self):
        res = enrich(url_shortener.build(), _curated())
        # in-band → GROUNDED
        self.assertTrue(_find(res, "cache", "base_latency_ms").in_band)
        self.assertTrue(_find(res, "db", "per_instance_rps").in_band)
        # out-of-band → RECONCILE (value far from a kind-matched but context-mismatched benchmark)
        self.assertFalse(_find(res, "lb", "per_instance_rps").in_band)
        self.assertFalse(_find(res, "db", "monthly_cost_per_instance").in_band)
        self.assertEqual(len(res.out_of_band), 2)

    def test_default_mode_keeps_out_of_band_value(self):
        # The modeler's out-of-band LB capacity + DB cost must be KEPT, never silently clobbered.
        m = url_shortener.build()
        res = enrich(m, _curated())   # default: no override
        self.assertEqual(res.model.components["lb"].per_instance_rps, 30_000)
        self.assertEqual(res.model.components["db"].monthly_cost_per_instance, 42_000)
        # but the evidence IS attached (so the report can show RECONCILE)
        self.assertIn("per_instance_rps", res.model.components["lb"].groundings)

    def test_context_free_disjoint_does_not_ground_app_server(self):
        # app_server cost datapoints span disjoint vendor bands → the KB refuses to guess (returns None).
        res = enrich(url_shortener.build(), _curated())
        self.assertIsNone(_find(res, "app", "monthly_cost_per_instance"))
        self.assertFalse(res.model.components["app"].groundings)

    def test_override_moves_only_matched_inputs_and_keeps_money_integer(self):
        res = enrich(url_shortener.build(), _curated(), override=True)
        db = res.model.components["db"]
        lb = res.model.components["lb"]
        self.assertEqual(db.per_instance_rps, 8_133)                 # in-band central applied
        self.assertEqual(lb.per_instance_rps, 350_000)               # out-of-band central applied (opt-in)
        self.assertEqual(db.monthly_cost_per_instance, 12_210)       # money override
        self.assertIsInstance(db.monthly_cost_per_instance, int)     # harm floor: still integer cents

    def test_override_changes_engine_cost_default_does_not(self):
        m = url_shortener.build()
        base = simulate(m).monthly_cost
        default_cost = simulate(enrich(m, _curated()).model).monthly_cost
        override_cost = simulate(enrich(m, _curated(), override=True).model).monthly_cost
        self.assertEqual(default_cost, base)        # evidence-only doesn't move the bill
        self.assertNotEqual(override_cost, base)    # override does (db cost $420 → $122.10)

    def test_curated_report_renders_citation_and_band(self):
        m = enrich(url_shortener.build(), _curated()).model
        md = render(m, make_council().design(m), simulate(m))
        self.assertIn("## Grounding & reconciliation", md)
        self.assertIn("RECONCILE", md)
        self.assertIn("GROUNDED", md)
        self.assertIn("Redis official documentation", md)   # a citation source
        self.assertIn("4,800–29,000 rps", md)               # a cited band

    def test_scaled_what_if_preserves_groundings(self):
        m = enrich(url_shortener.build(), _curated()).model
        scaled = m.scaled(50_000)
        self.assertIn("base_latency_ms", scaled.components["cache"].groundings)


if __name__ == "__main__":
    unittest.main()
