"""Tests for the architecture audit report (keystone.audit_report).

The audit report is the client deliverable, so the honesty surface is what matters most:
it must carry the L0 maturity + non-guarantee disclaimer, fire the high-stakes expert-review
banner, rank findings by severity, surface (not hide) unresolved rows, reuse the engine's
numbers without producing new ones, and stay deterministic.
"""
import copy
import dataclasses
import unittest

from keystone import __version__ as ENGINE_VERSION
from keystone.actuals import Observation, reconcile_observed
from keystone.audit_report import render_audit_report
from keystone.blueprints import payments, url_shortener
from keystone.simulation import ComponentResult, simulate


def _model():
    return url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)


def _obs(metric, value, *, component_id=None, unit="ratio", source="Datadog"):
    return Observation(metric=metric, value=value, unit=unit, source=source,
                       window="2026-07", component_id=component_id)


class TestAuditReport(unittest.TestCase):
    def setUp(self):
        self.model = _model()
        self.sim = simulate(self.model)
        self.outcome = reconcile_observed(self.sim, [
            _obs("utilization", self.sim.components["app"].utilization, component_id="app"),       # match
            _obs("utilization", self.sim.components["cache"].utilization * 3, component_id="cache"),  # hard
            _obs("p99_ms", self.sim.metrics["p99_ms"].value * 1.3, unit="ms"),                     # soft
            _obs("error_rate", 0.02, component_id="app"),                                          # no prediction
        ])
        self.md = render_audit_report(self.model, self.sim, self.outcome)

    def test_maturity_and_nonguarantee(self):
        self.assertIn("L0 (Directional)", self.md)
        self.assertIn("certification", self.md)
        self.assertIn("guarantee", self.md)
        self.assertIn("No guarantee", self.md)          # the explicit limitations bullet

    def test_structure_and_findings(self):
        for section in ("Keystone Architecture Audit", "Executive summary", "Findings",
                        "Model vs observed reality", "Limitations & where this is wrong",
                        "Reproducibility"):
            self.assertIn(section, self.md)
        self.assertIn("HARD", self.md)                  # the hard cache divergence, ranked
        self.assertIn("Modeled vs measured", self.md)   # the modeled-vs-measured honesty distinction

    def test_reproducibility_and_provenance(self):
        self.assertIn(ENGINE_VERSION, self.md)
        self.assertIn("Datadog", self.md)               # observation source surfaced

    def test_unresolved_rows_surfaced_not_hidden(self):
        # the NO_PREDICTION error_rate row must appear, not be silently dropped
        self.assertIn("Could not be compared", self.md)
        self.assertIn("error_rate", self.md)

    def test_hard_divergence_ranked_first(self):
        findings = self.md.split("## Findings")[1].split("##")[0]
        hard_pos = findings.find("HARD")
        soft_pos = findings.find("soft")
        self.assertGreater(hard_pos, -1)
        self.assertTrue(soft_pos == -1 or hard_pos < soft_pos)   # hard listed before soft

    def test_high_stakes_banner(self):
        pm = payments.build()
        pmd = render_audit_report(pm, simulate(pm), reconcile_observed(simulate(pm), []))
        self.assertIn("HIGH-STAKES DOMAIN", pmd)
        self.assertIn("mandatory expert", pmd.lower())
        self.assertNotIn("HIGH-STAKES DOMAIN", self.md)   # url_shortener isn't high-stakes

    def test_no_observed_is_model_only_not_a_pass(self):
        md0 = render_audit_report(self.model, self.sim, reconcile_observed(self.sim, []))
        self.assertIn("MODEL-ONLY", md0)
        self.assertNotIn("within tolerance", md0)          # must not read as a validation pass
        self.assertIn("nothing was reconciled", md0.lower())

    def test_all_incomparable_is_not_a_pass(self):
        # Observations supplied but none comparable (unit-mismatch + not-predicted): the headline
        # must NOT claim consistency/within-tolerance — the overclaim the review caught.
        outcome = reconcile_observed(self.sim, [
            _obs("utilization", 72, component_id="app", unit="percent"),   # UNIT_MISMATCH
            _obs("error_rate", 0.02, component_id="app"),                  # NO_PREDICTION
        ])
        md = render_audit_report(self.model, self.sim, outcome)
        self.assertIn("NOT RECONCILED", md)
        self.assertNotIn("BROADLY CONSISTENT", md)
        self.assertNotIn("within tolerance", md)
        self.assertIn("Nothing was reconciled", md)

    def test_zero_predicted_finding_does_not_crash(self):
        zero = ComponentResult(id="z", name="z", arrival_rps=0.0, capacity_rps=100.0,
                               utilization=0.0, mean_latency_ms=0.0, saturated=False)
        sim0 = dataclasses.replace(self.sim, components={"z": zero})
        outcome = reconcile_observed(sim0, [_obs("utilization", 0.5, component_id="z")])  # DIVERGE, gap None
        md = render_audit_report(self.model, sim0, outcome)
        self.assertIn("gap n/a", md)                     # None gap rendered safely

    def test_does_not_mutate_inputs(self):
        # Prime-directive boundary: the report READS its inputs; it must not mutate the engine
        # result, the model, or the reconciliation. Deep-compare the whole objects.
        sim_before = copy.deepcopy(self.sim)
        model_before = copy.deepcopy(self.model)
        outcome_before = copy.deepcopy(self.outcome)
        render_audit_report(self.model, self.sim, self.outcome)
        self.assertEqual(self.sim, sim_before)
        self.assertEqual(self.model, model_before)
        self.assertEqual(self.outcome, outcome_before)

    def test_deterministic(self):
        self.assertEqual(render_audit_report(self.model, self.sim, self.outcome),
                         render_audit_report(self.model, self.sim, self.outcome))

    def test_render_self_defends_against_injection(self):
        # Built directly (bypassing the parser's sanitisation) with newline/heading payloads
        # in the untrusted source + metric — the report must not break out into a heading.
        evil = [
            _obs("utilization", self.sim.components["cache"].utilization * 3,   # → Findings + Reproducibility
                 component_id="cache", source="ok\n## PWNED\n| forged | row |"),
            _obs("bad_metric\n## H2", 1.0, component_id="app"),                  # → NO_PREDICTION (unresolved)
        ]
        md = render_audit_report(self.model, self.sim, reconcile_observed(self.sim, evil))
        self.assertNotIn("\n## PWNED", md)
        self.assertNotIn("\n## H2", md)
        self.assertFalse(any(ln.startswith("## PWNED") or ln.startswith("## H2")
                             for ln in md.splitlines()))


if __name__ == "__main__":
    unittest.main()
