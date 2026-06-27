"""The grounding seam (`keystone.grounding.enrich`) — ADR-006 L0→L1 wiring.

Locks the trust-critical guarantees: (1) under the stub KB it is a strict no-op (engine + report
byte-identical); (2) in default/evidence-only mode it NEVER moves a value, so the engine output is
identical (the prime-directive proof); (3) it only ever probes the 3 INPUT metrics; (4) the curated
corpus produces the honest mixed report (in-band GROUNDED + out-of-band RECONCILE, value kept);
(5) override is opt-in and money stays integer cents.
"""
from __future__ import annotations

import inspect
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import run_url_shortener
from keystone.benchmarks.benchmark_corpus import CuratedKnowledgeBase
from keystone.grounding import enrich as _enrich_fn
from keystone.blueprints import url_shortener
from keystone.grounding import _RATE_EVIDENCE, enrich, ground_pricing
from keystone.knowledge_base import EmptyKnowledgeBase, make_knowledge_base
from keystone.model import COMPUTE_PRICING_RETAINED_BP, PricingRates
from keystone.provenance import GROUNDABLE_METRICS
from keystone.report import _RATE_LABEL, _RATE_ORDER, render
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

    def test_caveats_provenance_accurate_when_grounded(self):
        # Honesty audit fix: a grounded report must NOT claim ALL capacities are ASSUMPTION (the grounding
        # table shows some GROUNDED/RECONCILE), and the cost caveat must flag that the per-component COMPUTE
        # prices carry their own provenance — the "GROUNDED rates" label is only for per-unit rates.
        _, _, _, md = run_url_shortener.build_and_render(_curated())
        self.assertIn("MIXED provenance", md)
        self.assertIn("per-component COMPUTE prices", md)
        self.assertNotIn("Component capacities are SEED benchmarks tagged ASSUMPTION", md)

    def test_caveats_unchanged_when_no_grounding(self):
        # Stub off-state: keep the original ASSUMPTION wording — no false "mixed provenance" with nothing grounded.
        _, _, _, md = run_url_shortener.build_and_render(EmptyKnowledgeBase())
        self.assertIn("Component capacities are SEED benchmarks tagged ASSUMPTION", md)
        self.assertNotIn("MIXED provenance", md)

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
        # in-band → GROUNDED (modeler value sits inside the cited band)
        self.assertTrue(_find(res, "cache", "base_latency_ms").in_band)   # 0.5 in [0.4,1.5]
        self.assertTrue(_find(res, "db", "per_instance_rps").in_band)     # 8,000 in [4.8k,29k]
        self.assertTrue(_find(res, "cache", "per_instance_rps").in_band)  # 100k in [70k,180k] (grown corpus)
        # out-of-band → RECONCILE (value outside a kind-matched but context-mismatched benchmark)
        self.assertFalse(_find(res, "lb", "per_instance_rps").in_band)    # 30k vs bare-metal nginx 350k
        self.assertFalse(_find(res, "db", "monthly_cost_per_instance").in_band)
        self.assertFalse(_find(res, "app", "per_instance_rps").in_band)   # 1,200 below [2k,8k] (grown corpus)
        self.assertGreaterEqual(len(res.out_of_band), 2)                  # mix of GROUNDED + RECONCILE

    def test_default_mode_keeps_out_of_band_value(self):
        # The modeler's out-of-band LB capacity + DB cost must be KEPT, never silently clobbered.
        m = url_shortener.build()
        res = enrich(m, _curated())   # default: no override
        self.assertEqual(res.model.components["lb"].per_instance_rps, 30_000)
        self.assertEqual(res.model.components["db"].monthly_cost_per_instance, 42_000)
        # but the evidence IS attached (so the report can show RECONCILE)
        self.assertIn("per_instance_rps", res.model.components["lb"].groundings)

    def test_context_free_disjoint_cost_does_not_ground(self):
        # app_server COST datapoints span disjoint vendor bands → the KB refuses to guess (returns None),
        # even though app_server per_instance_rps now grounds (grown corpus). Cost needs context matching.
        res = enrich(url_shortener.build(), _curated())
        self.assertIsNone(_find(res, "app", "monthly_cost_per_instance"))
        self.assertNotIn("monthly_cost_per_instance", res.model.components["app"].groundings)

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

    def test_stub_report_byte_for_byte_matches_stub_fixture(self):
        # Locks the grounding-OFF render: with KB_PROVIDER=stub the report must equal the stub fixture,
        # so a future render tweak can't silently change the off-state output. (The DEFAULT report,
        # url_shortener_report.md, is now grounded — see test_curated_report_byte_for_byte.)
        _, _, _, md = run_url_shortener.build_and_render(EmptyKnowledgeBase())
        golden = (Path(run_url_shortener.__file__).resolve().parent
                  / "outputs" / "url_shortener_report.stub.md").read_text(encoding="utf-8")
        self.assertEqual(md, golden, "stub report drifted — regenerate outputs/url_shortener_report.stub.md")

    def test_override_defaults_off(self):
        # Safe-default lock: enrich must NEVER move an input unless a caller explicitly opts in.
        # The shipped report path (run_url_shortener.build_and_render) never passes override=True.
        self.assertIs(inspect.signature(_enrich_fn).parameters["override"].default, False)

    # ---- Cost-rate grounding (slice 2) -------------------------------------------------------- #

    def test_ground_pricing_noop_under_stub(self):
        m = url_shortener.build()
        self.assertIs(ground_pricing(m, EmptyKnowledgeBase()), m)        # strict identity
        self.assertFalse(m.pricing.groundings)

    def test_ground_pricing_attaches_all_eight_rates_under_curated(self):
        m = ground_pricing(url_shortener.build(), _curated())
        self.assertEqual(set(m.pricing.groundings), {
            "egress", "storage", "requests", "llm_input", "llm_output",
            "reserved_1yr", "reserved_3yr", "spot"})
        for g in m.pricing.groundings.values():
            self.assertTrue(g.citations)                                # ≥1 cited source (Grounding invariant)
            self.assertLessEqual(g.confidence_low, g.value)             # band brackets the value
            self.assertLessEqual(g.value, g.confidence_high)

    def test_rate_grounding_values_match_the_engine_seeds(self):
        # The attached evidence value must equal the rate the engine actually uses (no drift).
        m = ground_pricing(url_shortener.build(), _curated())
        pr = PricingRates()
        self.assertEqual(m.pricing.groundings["egress"].value, pr.egress_micro_usd_per_gb)
        self.assertEqual(m.pricing.groundings["requests"].value, pr.request_micro_usd_per_thousand)
        self.assertEqual(m.pricing.groundings["llm_output"].value, pr.llm_output_micro_usd_per_1k_tokens)
        self.assertEqual(m.pricing.groundings["spot"].value, COMPUTE_PRICING_RETAINED_BP["spot"])

    def test_rate_grounding_does_not_change_engine_cost(self):
        # Evidence-only: attaching rate citations must not move the bill (prime-directive proof for rates).
        m = url_shortener.build()
        base = simulate(m).monthly_cost
        grounded = simulate(ground_pricing(m, _curated())).monthly_cost
        self.assertEqual(base, grounded)

    def test_report_shows_rate_evidence_only_when_grounded(self):
        stub_m = url_shortener.build()
        self.assertNotIn("## Cost rate evidence", render(stub_m, make_council().design(stub_m), simulate(stub_m)))
        m = ground_pricing(url_shortener.build(), _curated())
        md = render(m, make_council().design(m), simulate(m))
        self.assertIn("## Cost rate evidence", md)
        self.assertIn("$3.00/1M req", md)         # the grounded requests rate (corrected from $1)
        self.assertIn("77% off", md)              # the grounded spot discount
        self.assertIn("AWS API Gateway", md)      # a citation source

    # ---- Activation-readiness fixes (final-review follow-ups) --------------------------------- #

    def test_grounded_report_has_no_assumption_vs_grounded_contradiction(self):
        # The engine's cost provenance strings must AGREE with the report's rate tag when grounded —
        # never label the same rates both GROUNDED and ASSUMPTION (the honesty non-negotiable).
        c = url_shortener.build().components["app"]   # reuse a real component kind
        from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
        comp = Component("a", K.APP_SERVER, "App", per_instance_rps=1000.0, monthly_cost_per_instance=5000,
                         egress_gb_per_month=1000, requests_per_month=50_000_000)
        m = SystemModel("t", {"a": comp}, [Flow("f", 1.0, [FlowStep("a")])], Workload(1000.0),
                        pricing=PricingRates(compute_pricing="spot"))
        grounded = ground_pricing(m, _curated())
        md = render(grounded, make_council().design(grounded), simulate(grounded))
        self.assertIn("GROUNDED (cited) rates", md)            # engine + report agree: GROUNDED
        self.assertNotIn("ASSUMPTION rates", md)               # no leftover ASSUMPTION on the same rates
        self.assertNotIn("usage rates ASSUMPTION", md)
        # and the stub of the same model still honestly says ASSUMPTION (no false GROUNDED)
        stub_md = render(m, make_council().design(m), simulate(m))
        self.assertIn("ASSUMPTION rates", stub_md)
        self.assertNotIn("GROUNDED (cited) rates", stub_md)

    def test_custom_billed_rate_is_not_falsely_certified_as_grounded(self):
        # A model that BILLS a custom rate (≠ grounded central) must not be swept under a blanket GROUNDED
        # prose tag — neither the evidence table (fail closed) nor the cost caveats/derivation.
        from keystone.model import Component, ComponentKind as K, Flow, FlowStep, SystemModel, Workload
        comp = Component("a", K.APP_SERVER, "App", per_instance_rps=1000.0, monthly_cost_per_instance=5000,
                         egress_gb_per_month=1000)                           # bills egress
        m = SystemModel("t", {"a": comp}, [Flow("f", 1.0, [FlowStep("a")])], Workload(1000.0),
                        pricing=PricingRates(egress_micro_usd_per_gb=300_000))   # custom $0.30/GB ≠ grounded
        grounded = ground_pricing(m, _curated())
        self.assertNotIn("egress", grounded.pricing.groundings)     # fail closed: custom egress not certified
        self.assertIn("requests", grounded.pricing.groundings)      # default rates still grounded
        md = render(grounded, make_council().design(grounded), simulate(grounded))
        self.assertNotIn("GROUNDED (cited) rates", md)              # a billed custom rate → no blanket GROUNDED
        self.assertIn("ASSUMPTION rates", md)
        # control: the SAME model with the default (grounded) egress rate → all billed rates grounded → GROUNDED
        comp2 = Component("b", K.APP_SERVER, "App", per_instance_rps=1000.0, monthly_cost_per_instance=5000,
                          egress_gb_per_month=1000)
        m2 = SystemModel("t2", {"b": comp2}, [Flow("f", 1.0, [FlowStep("b")])], Workload(1000.0))
        md2 = render(ground_pricing(m2, _curated()), make_council().design(m2), simulate(ground_pricing(m2, _curated())))
        self.assertIn("GROUNDED (cited) rates", md2)

    def test_rate_tables_match_evidence_ids(self):
        # The hand-maintained report tables must stay in lockstep with the evidence file's rate ids.
        json_ids = {r["id"] for r in json.loads(_RATE_EVIDENCE.read_text())["rates"]}
        self.assertEqual(json_ids, set(_RATE_ORDER))
        self.assertEqual(json_ids, set(_RATE_LABEL))

    def test_kb_provider_empty_or_whitespace_defaults_to_stub(self):
        # A set-but-empty KB_PROVIDER (export KB_PROVIDER= / empty CI secret) must not crash the run.
        for val in ("", "  "):
            with mock.patch.dict(os.environ, {"KB_PROVIDER": val}):
                self.assertIsInstance(make_knowledge_base(), EmptyKnowledgeBase)

    def test_curated_report_byte_for_byte_matches_committed_golden(self):
        # The DEFAULT (activated) report is grounded: locks the GROUNDED render incl. the grounding
        # sections. This is the committed outputs/url_shortener_report.md (what `main()` now writes).
        _, _, _, md = run_url_shortener.build_and_render(CuratedKnowledgeBase.from_default_corpus())
        golden = (Path(run_url_shortener.__file__).resolve().parent
                  / "outputs" / "url_shortener_report.md").read_text(encoding="utf-8")
        self.assertEqual(md, golden, "grounded report drifted — regenerate outputs/url_shortener_report.md")


if __name__ == "__main__":
    unittest.main()
