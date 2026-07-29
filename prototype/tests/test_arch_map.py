"""Tests for the architecture map (keystone.arch_map).

The map is a VIEW of a validated design, so its trust surface is what matters: it must reproduce the
engine's numbers exactly (never fabricate one), stay deterministic, carry the honesty furniture
(L0 label, provenance, "where this is wrong", high-stakes banner), never mutate its inputs, and be
injection-safe (untrusted component names / citations cannot break out of the data island).
"""
import copy
import json
import os
import re
import unittest

from keystone import __version__ as ENGINE_VERSION
from keystone.arch_map import _json_safe, _round_floats, _status, build_arch_map, render_html
from keystone.blueprints import payments, url_shortener
from keystone.model import (Assumption, Component, ComponentKind, Flow, FlowStep,
                            SystemModel, Workload)
from keystone.provenance import Citation, Grounding
from keystone.simulation import simulate


def _us():
    m = url_shortener.build(system_rps=10_000, cache_hit_rate=0.90)
    return m, simulate(m)


def _extract_blob(html: str) -> dict:
    """Recover the embedded JSON data island exactly as a browser's JSON.parse would (it accepts the
    \\u003c escaping). Proves the blob is STRICT, parseable JSON — not just a Python dict."""
    m = re.search(r'<script id="arch-data" type="application/json">(.*?)</script>', html, re.S)
    assert m, "arch-data island not found"
    return json.loads(m.group(1))   # json.loads natively decodes < / & etc.


class TestArchMapNumbers(unittest.TestCase):
    """Prime directive: every number on the map is an engine value, read — never produced here."""

    def setUp(self):
        self.model, self.sim = _us()
        self.arch = build_arch_map(self.model, self.sim)

    def test_every_node_number_equals_the_engine(self):
        for n in self.arch["nodes"]:
            cr = self.sim.components[n["id"]]
            self.assertEqual(n["utilization"], cr.utilization)
            self.assertEqual(n["arrival_rps"], cr.arrival_rps)
            self.assertEqual(n["mean_latency_ms"], cr.mean_latency_ms)
            self.assertEqual(n["saturated"], cr.saturated)

    def test_verdict_equals_the_engine(self):
        v = self.arch["verdict"]
        self.assertEqual(v["bottleneck_id"], self.sim.bottleneck_id)
        self.assertEqual(v["bottleneck_utilization"], self.sim.bottleneck_utilization)
        self.assertEqual(v["breakpoint_rps_safe"], self.sim.breakpoint_rps_safe)
        self.assertEqual(v["monthly_cost_cents"], self.sim.monthly_cost)
        self.assertEqual(v["latency"]["p99_ms"], self.sim.p99_ms)

    def test_metrics_mirror_the_engine_envelope_in_order(self):
        self.assertEqual([m["key"] for m in self.arch["metrics"]], list(self.sim.metrics.keys()))
        for m in self.arch["metrics"]:
            src = self.sim.metrics[m["key"]]
            self.assertEqual(m["value"], src.value)
            self.assertEqual(m["model"], src.model)
            self.assertEqual((m["low"], m["high"]), (src.low, src.high))

    def test_bottleneck_and_spof_flags_track_the_engine(self):
        bn = [n for n in self.arch["nodes"] if n["is_bottleneck"]]
        self.assertEqual([n["id"] for n in bn], [self.sim.bottleneck_id])
        spof_names = {n["name"] for n in self.arch["nodes"] if n["is_spof"]}
        self.assertEqual(spof_names, set(self.sim.spofs))

    def test_source_file_has_no_metric_constructor(self):
        # Locality mirror of the ADR-007 envelope guard: this module must never author a number.
        import keystone.arch_map as am
        with open(am.__file__, encoding="utf-8") as f:
            self.assertNotIn("Metric(", f.read())


class TestDeterminismAndValidity(unittest.TestCase):
    def test_build_and_render_are_deterministic(self):
        m, s = _us()
        self.assertEqual(build_arch_map(m, s), build_arch_map(m, s))
        self.assertEqual(render_html(build_arch_map(m, s)), render_html(build_arch_map(m, s)))

    def test_embedded_blob_is_strict_json_and_matches(self):
        m, s = _us()
        arch = build_arch_map(m, s)
        recovered = _extract_blob(render_html(arch))
        # The blob is the map with floats rounded to a cross-version-stable precision (render-time only),
        # so it round-trips through strict JSON to exactly the rounded map.
        self.assertEqual(recovered, _round_floats(arch))

    def test_does_not_mutate_inputs(self):
        m, s = _us()
        mb, sb = copy.deepcopy(m), copy.deepcopy(s)
        render_html(build_arch_map(m, s))
        self.assertEqual(m, mb)
        self.assertEqual(s, sb)

    def test_json_safe_replaces_nonfinite_and_render_survives_unbounded(self):
        # An unbounded breakpoint (ρ→0) is inf; it must become null and NOT raise under allow_nan=False.
        import dataclasses
        m, s = _us()
        s2 = dataclasses.replace(s, breakpoint_rps_theoretical=float("inf"))
        arch = build_arch_map(m, s2)
        self.assertIsNone(arch["verdict"]["breakpoint_rps_theoretical"])
        html = render_html(arch)          # must not raise (strict JSON, allow_nan=False)
        self.assertIn("arch-data", html)
        self.assertEqual(_json_safe(float("nan")), None)
        self.assertEqual(_json_safe(1.5), 1.5)


class TestHonestyFurniture(unittest.TestCase):
    def test_l0_and_where_this_is_wrong_present(self):
        m, s = _us()
        html = render_html(build_arch_map(m, s))
        self.assertIn("L0 (Directional)", html)
        self.assertIn("Where this is wrong", html)
        # the engine's caveats are carried verbatim into the data island
        arch = _extract_blob(html)
        self.assertEqual(arch["caveats"], list(s.caveats))
        self.assertTrue(arch["caveats"])   # url_shortener has caveats

    def test_high_stakes_banner_fires_only_when_flagged(self):
        pm = payments.build()
        pm_html = render_html(build_arch_map(pm, simulate(pm)))
        self.assertIn("HIGH-STAKES DOMAIN", pm_html)
        self.assertTrue(_extract_blob(pm_html)["meta"]["high_stakes"])
        m, s = _us()
        us_html = render_html(build_arch_map(m, s))
        self.assertFalse(_extract_blob(us_html)["meta"]["high_stakes"])
        # the banner copy is only *populated* from meta.high_stakes by JS, so the flag is the real gate
        self.assertNotIn('"high_stakes":true', us_html.replace(" ", ""))

    def test_engine_version_and_accuracy_level_carried(self):
        m, s = _us()
        arch = build_arch_map(m, s)
        self.assertEqual(arch["meta"]["engine_version"], ENGINE_VERSION)
        self.assertEqual(arch["meta"]["accuracy_level"], "L0 (Directional)")

    def test_status_buckets_match_report_thresholds(self):
        self.assertEqual(_status(0.5, False), "ok")
        self.assertEqual(_status(0.85, False), "hot")
        self.assertEqual(_status(0.99, True), "saturated")   # saturated wins even if util < 1 rounding

    def test_confidence_qualifier_is_not_stripped(self):
        # The engine's confidence string carries its honesty qualifier in parentheses (e.g.
        # "medium (directional; …)"). The renderer must NEVER truncate at the first "(" on the header /
        # verdict / metrics surfaces — that would show a bare, more-certain-sounding label than the engine's.
        m, s = _us()
        html = render_html(build_arch_map(m, s))
        self.assertNotIn("split('(", html)                   # no confidence-stripping anywhere in the JS
        self.assertIn(s.confidence, _extract_blob(html)["meta"]["confidence"])
        self.assertIn("(", s.confidence)                     # sanity: the string really has a qualifier


class TestProvenanceAndEvidence(unittest.TestCase):
    def _model_with(self, grounding, name="App"):
        comp = Component("app", ComponentKind.APP_SERVER, name, per_instance_rps=1000.0, instances=3,
                         groundings={"per_instance_rps": grounding} if grounding else {})
        db = Component("db", ComponentKind.SQL_DB, "DB", per_instance_rps=500.0)
        return SystemModel(name="Prov Co", components={"app": comp, "db": db},
                           flows=[Flow("f", 1.0, [FlowStep("app"), FlowStep("db")])],
                           workload=Workload(system_rps=100.0))

    def test_grounded_in_band_is_GROUNDED_with_citation(self):
        g = Grounding(1000.0, "rps", 900.0, 1100.0, citations=(Citation("Redis bench", "http://ex/ref"),))
        m = self._model_with(g)
        arch = build_arch_map(m, simulate(m))
        app = next(n for n in arch["nodes"] if n["id"] == "app")
        self.assertEqual(app["provenance"], "GROUNDED")
        self.assertEqual(app["evidence"][0]["status"], "GROUNDED")
        self.assertEqual(app["evidence"][0]["sources"][0]["source"], "Redis bench")

    def test_value_outside_band_is_RECONCILE_not_overwritten(self):
        # per_instance_rps=1000 sits OUTSIDE the cited band 400–600 → RECONCILE, and the modeler value is kept.
        g = Grounding(500.0, "rps", 400.0, 600.0, citations=(Citation("bench", "http://ex/r"),))
        m2 = self._model_with(g)
        arch = build_arch_map(m2, simulate(m2))
        app = next(n for n in arch["nodes"] if n["id"] == "app")
        self.assertEqual(app["provenance"], "RECONCILE")
        self.assertEqual(app["evidence"][0]["status"], "RECONCILE")
        self.assertEqual(app["evidence"][0]["your_value"], 1000.0)  # the modeler value, kept

    def test_ungrounded_component_is_assumption(self):
        m = self._model_with(None)
        arch = build_arch_map(m, simulate(m))
        app = next(n for n in arch["nodes"] if n["id"] == "app")
        self.assertEqual(app["provenance"], "ASSUMPTION")
        self.assertEqual(app["evidence"], [])

    def test_out_of_vocab_provenance_clamps_to_assumption(self):
        # A free-form / LLM-supplied provenance outside the known vocabulary must clamp to ASSUMPTION,
        # so it keeps the amber (honesty) styling instead of silently degrading to neutral — a node must
        # never read LESS uncertain than it is.
        comp = Component("app", ComponentKind.APP_SERVER, "A", per_instance_rps=100.0, provenance="inferred")
        m = SystemModel(name="X", components={"app": comp},
                        flows=[Flow("f", 1.0, [FlowStep("app")])], workload=Workload(system_rps=10.0))
        arch = build_arch_map(m, simulate(m))
        self.assertEqual(arch["nodes"][0]["provenance"], "ASSUMPTION")   # not "INFERRED"


class TestInjectionSafety(unittest.TestCase):
    def test_hostile_strings_cannot_break_out_of_the_data_island(self):
        evil = 'App </script><script>alert(1)</script> & <b>x</b>'
        comp = Component("app", ComponentKind.APP_SERVER, evil, per_instance_rps=1000.0, instances=2,
                         groundings={"per_instance_rps": Grounding(
                             1000.0, "rps", 900.0, 1100.0,
                             citations=(Citation("s</script>x", "r&<i>y"),))})
        db = Component("db", ComponentKind.SQL_DB, "DB", per_instance_rps=500.0)
        m = SystemModel(name="Evil </script> Co", components={"app": comp, "db": db},
                        flows=[Flow("f", 1.0, [FlowStep("app"), FlowStep("db")])],
                        workload=Workload(system_rps=100.0),
                        assumptions=[Assumption("s", "stmt </script> x", "med")],
                        domain_flags=["high_stakes:payments"])
        html = render_html(build_arch_map(m, simulate(m)))
        # exactly the two real closers (arch-data island + render script); none injected
        self.assertEqual(html.count("</script>"), 2)
        self.assertEqual(html.lower().count("<script"), 2)
        self.assertNotIn("<script>alert(1)", html)
        self.assertIn("\\u003c", html)                     # the payload was neutralised in the blob
        # and it still parses as strict JSON with the hostile text preserved as DATA
        arch = _extract_blob(html)
        app = next(n for n in arch["nodes"] if n["id"] == "app")
        self.assertEqual(app["name"], evil)                # preserved verbatim as text, not markup

    def test_title_is_html_escaped_in_head(self):
        comp = Component("a", ComponentKind.APP_SERVER, "A", per_instance_rps=100.0)
        m = SystemModel(name="T </title><script>x</script>", components={"a": comp},
                        flows=[Flow("f", 1.0, [FlowStep("a")])], workload=Workload(system_rps=10.0))
        html = render_html(build_arch_map(m, simulate(m)))
        self.assertNotIn("</title><script>x", html)        # escaped, no breakout
        self.assertIn("&lt;/title&gt;", html)


class TestCommittedGolden(unittest.TestCase):
    """The demo maps are committed goldens (like the md reports). Lock byte-identity against the tree so
    a change to arch_map.py that forgets to regenerate fails loudly — and render the SAME grounded path
    main() writes (imported from run_arch_map, no drift). Mirrors test_grounding_seam.py's md golden lock."""

    def test_demo_maps_match_committed_goldens(self):
        import run_arch_map
        for name, builder in run_arch_map.DEMOS:
            _model, _sim, html = run_arch_map.render_map(builder)
            golden = os.path.join(run_arch_map.OUT, f"{name}_map.html")
            self.assertTrue(os.path.exists(golden), f"missing golden {name}_map.html — run `python3 run_arch_map.py`")
            with open(golden, encoding="utf-8") as f:
                self.assertEqual(html, f.read(),
                                 f"outputs/{name}_map.html is stale — regenerate with `python3 run_arch_map.py`")

    def test_serialized_floats_are_cross_version_stable(self):
        # The embedded blob must carry NO >6dp float — full-precision engine floats differ in the last
        # ULP across CPython versions (libm) and would break the committed byte-golden on a different
        # Python (was green on 3.9, red on 3.12+). _round_floats at render time pins this; guard it so a
        # future change can't silently reintroduce drift-prone precision.
        import run_arch_map
        for name, builder in run_arch_map.DEMOS:
            _model, _sim, html = run_arch_map.render_map(builder)
            leaked: list[str] = []

            def walk(o, path=""):
                if isinstance(o, float):
                    if round(o, 6) != o:
                        leaked.append(f"{path}={o!r}")
                elif isinstance(o, dict):
                    for k, v in o.items():
                        walk(v, f"{path}.{k}")
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        walk(v, f"{path}[{i}]")

            walk(_extract_blob(html))
            self.assertEqual(leaked, [], f"drift-prone >6dp floats leaked into {name} blob: {leaked[:5]}")


if __name__ == "__main__":
    unittest.main()
