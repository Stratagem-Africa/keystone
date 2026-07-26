"""Tests for the audit map (keystone.audit_map) — the architecture map overlaid with model-vs-observed
divergence. Trust surface: reproduce the reconciliation faithfully (worst-verdict per node), keep the
base engine numbers intact (prime directive), stay honest (L0, non-guarantee, never a false pass),
deterministic, and injection-safe. (arch_map itself stays actuals-free — guarded in test_actuals.py.)
"""
import copy
import json
import re
import unittest

from keystone.actuals import Observation, reconcile_observed
from keystone.audit_map import build_audit_map, render_audit_map_html
from keystone.blueprints import url_shortener
from keystone.simulation import simulate


def _us():
    m = url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)
    return m, simulate(m)


def _obs(metric, value, *, component_id=None, unit="ratio", source="Datadog"):
    return Observation(metric=metric, value=value, unit=unit, source=source,
                       window="2026-07", component_id=component_id)


def _blob(html):
    m = re.search(r'<script id="arch-data" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class TestDivergenceOverlay(unittest.TestCase):
    def setUp(self):
        self.model, self.sim = _us()
        self.outcome = reconcile_observed(self.sim, [
            _obs("utilization", self.sim.components["app"].utilization, component_id="app"),          # MATCH
            _obs("utilization", self.sim.components["cache"].utilization * 3, component_id="cache"),   # hard DIVERGE
            _obs("p99_ms", self.sim.metrics["p99_ms"].value * 1.3, unit="ms"),                         # system-level
            _obs("error_rate", 0.02, component_id="db"),                                               # NO_PREDICTION
        ])
        self.arch = build_audit_map(self.model, self.sim, self.outcome)
        self.nodes = {n["id"]: n for n in self.arch["nodes"]}

    def test_node_status_by_component(self):
        self.assertEqual(self.nodes["app"]["divergence"]["status"], "matched")
        self.assertEqual(self.nodes["cache"]["divergence"]["status"], "hard")
        self.assertEqual(self.nodes["db"]["divergence"]["status"], "not_compared")   # only NO_PREDICTION
        self.assertEqual(self.nodes["lb"]["divergence"]["status"], "not_observed")   # nothing observed

    def test_hard_divergence_carries_gap(self):
        self.assertAlmostEqual(self.nodes["cache"]["divergence"]["gap"], 2.0)   # observed = 3×predicted → +200%

    def test_soft_divergence_status(self):
        outcome = reconcile_observed(self.sim, [
            _obs("utilization", self.sim.components["app"].utilization * 1.3, component_id="app")])   # ~+30% → soft
        arch = build_audit_map(self.model, self.sim, outcome)
        app = next(n for n in arch["nodes"] if n["id"] == "app")
        self.assertEqual(app["divergence"]["status"], "soft")

    def test_system_level_observation_is_unmatched_not_dropped(self):
        u = self.arch["audit_unmatched"]
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["metric"], "p99_ms")
        self.assertIsNone(u[0]["component_id"])

    def test_audit_tally_and_honest_overall(self):
        a = self.arch["meta"]["audit"]
        self.assertEqual(a["matched"], 1)
        self.assertEqual(a["hard"], 1)
        self.assertEqual(a["observed_count"], 4)
        self.assertIn("NEEDS ATTENTION", a["overall"])       # a hard divergence is present

    def test_base_engine_numbers_intact(self):
        # Prime directive: the overlay must not disturb the engine values the base map carries.
        for n in self.arch["nodes"]:
            self.assertEqual(n["utilization"], self.sim.components[n["id"]].utilization)
            self.assertEqual(n["arrival_rps"], self.sim.components[n["id"]].arrival_rps)

    def test_no_observed_is_model_only_not_a_pass(self):
        arch = build_audit_map(self.model, self.sim, reconcile_observed(self.sim, []))
        self.assertIn("MODEL-ONLY", arch["meta"]["audit"]["overall"])
        self.assertTrue(all(n["divergence"]["status"] == "not_observed" for n in arch["nodes"]))

    def test_reads_as_pass_gates_the_not_a_guarantee_caveat(self):
        # Only an all-matched, no-divergence audit reads as a pass — and only then must the map carry
        # the "a match is NOT a guarantee of correctness" caveat (honesty charter on the glanceable surface).
        all_matched = reconcile_observed(self.sim, [
            _obs("utilization", self.sim.components["app"].utilization, component_id="app")])
        self.assertTrue(build_audit_map(self.model, self.sim, all_matched)["meta"]["audit"]["reads_as_pass"])
        self.assertIn("NOT a validation pass or a guarantee of correctness",
                      render_audit_map_html(self.model, self.sim, all_matched))
        # A hard divergence and a model-only audit must NOT read as a pass.
        self.assertFalse(self.arch["meta"]["audit"]["reads_as_pass"])                     # the setUp outcome has a hard row
        self.assertFalse(build_audit_map(self.model, self.sim,
                                         reconcile_observed(self.sim, []))["meta"]["audit"]["reads_as_pass"])


class TestRenderAndSafety(unittest.TestCase):
    def _hard(self):
        m, s = _us()
        outcome = reconcile_observed(s, [_obs("utilization", s.components["cache"].utilization * 3, component_id="cache")])
        return m, s, outcome

    def test_render_carries_audit_and_honesty_furniture(self):
        m, s, outcome = self._hard()
        html = render_audit_map_html(m, s, outcome)
        self.assertIn("model vs OBSERVED reality", html)     # audit subtitle
        self.assertIn("L0 (Directional)", html)              # honesty label
        self.assertIn("Where this is wrong", html)           # mandatory section
        self.assertIn("never auto-resolved", html)           # ADR-004 non-auto-resolve note
        self.assertTrue(_blob(html)["meta"]["audit"])        # audit overlay present in the data

    def test_deterministic(self):
        m, s, outcome = self._hard()
        self.assertEqual(render_audit_map_html(m, s, outcome), render_audit_map_html(m, s, outcome))

    def test_does_not_mutate_inputs(self):
        m, s, outcome = self._hard()
        mb, sb, ob = copy.deepcopy(m), copy.deepcopy(s), copy.deepcopy(outcome)
        render_audit_map_html(m, s, outcome)
        self.assertEqual(m, mb)
        self.assertEqual(s, sb)
        self.assertEqual(outcome, ob)

    def test_hostile_observed_source_cannot_break_out(self):
        # Build an Observation directly (bypassing the parser's sanitiser) with a </script> payload in
        # the untrusted source — the map's blob escaping must neutralise it at render time regardless.
        m, s = _us()
        evil = Observation(metric="utilization", value=s.components["cache"].utilization * 3, unit="ratio",
                           source="Datadog</script><script>alert(1)</script>", window="w", component_id="cache")
        html = render_audit_map_html(m, s, reconcile_observed(s, [evil]))
        self.assertEqual(html.count("</script>"), 2)         # only the two real closers
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("\\u003c", html)                       # payload neutralised inside the data island


if __name__ == "__main__":
    unittest.main()
