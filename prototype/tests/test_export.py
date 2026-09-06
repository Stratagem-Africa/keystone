"""The spec file (docs/05 §4): a SystemModel that survives a round trip to text and back.

The load-bearing guard is LOSSLESSNESS OF THE EVIDENCE LAYER. Round-tripping the numbers while
dropping `groundings` / `match_context` would turn a GROUNDED design into an uncited one — an
honesty regression wearing a data-loss costume — so equality is asserted on the whole model, never
on a hand-picked subset of fields.
"""
from __future__ import annotations

import json
import unittest

from keystone.benchmarks.reference_models import REFERENCE_MODELS
from keystone.blueprints import payments, ticket_booking, twitter, url_shortener
from keystone.export import SPEC_VERSION, ExportError, dumps, from_dict, loads, orphans, to_dict
from keystone.grounding import Citation, Grounding
from keystone.model import Component, ComponentKind, Flow, FlowStep, SystemModel, Workload
from keystone.simulation import simulate

ALL_BUILDERS = [b for _n, b, _r in REFERENCE_MODELS] + [
    url_shortener.build, payments.build, ticket_booking.build, twitter.build]


def _grounded_model() -> SystemModel:
    """A model carrying the full evidence layer, so the round trip is tested where it can lie."""
    g = Grounding(value=1200.0, unit="rps", confidence_low=900.0, confidence_high=1500.0,
                  citations=(Citation(source="vendor docs", reference="https://example.test/bench",
                                      note="c6g.large, 4 vCPU"),),
                  provenance="GROUNDED", measured_context="c6g.large, nginx, keepalive on")
    app = Component("app", ComponentKind.APP_SERVER, "App", per_instance_rps=1200.0, instances=2,
                    provenance="GROUNDED", groundings={"per_instance_rps": g},
                    match_context={"instance": "c6g.large", "engine": "nginx"})
    db = Component("db", ComponentKind.SQL_DB, "DB", per_instance_rps=8000.0)
    return SystemModel(
        name="Grounded fixture",
        components={"app": app, "db": db},
        flows=[Flow("read", 1.0, [FlowStep("app"), FlowStep("db", visit_prob=0.3)])],
        workload=Workload(system_rps=1000.0, description="fixture"),
    )


class RoundTripTest(unittest.TestCase):
    def test_every_shipped_model_round_trips_exactly(self):
        for build in ALL_BUILDERS:
            model = build()
            with self.subTest(model.name):
                self.assertEqual(loads(dumps(model)), model)

    def test_the_engine_agrees_after_a_round_trip(self):
        """Equality is necessary but not sufficient — the point is that the RUN reproduces."""
        for build in ALL_BUILDERS:
            model = build()
            with self.subTest(model.name):
                a, b = simulate(model), simulate(loads(dumps(model)))
                self.assertEqual(a.monthly_cost, b.monthly_cost)
                self.assertEqual(a.bottleneck_id, b.bottleneck_id)
                self.assertEqual(a.mean_latency_ms, b.mean_latency_ms)

    def test_the_evidence_layer_survives(self):
        model = _grounded_model()
        back = loads(dumps(model))
        self.assertEqual(back, model)
        g = back.components["app"].groundings["per_instance_rps"]
        self.assertEqual(g.provenance, "GROUNDED")
        self.assertEqual(g.measured_context, "c6g.large, nginx, keepalive on")
        self.assertEqual(g.citations[0].reference, "https://example.test/bench")
        self.assertEqual(back.components["app"].match_context["instance"], "c6g.large")

    def test_output_is_deterministic(self):
        for build in (url_shortener.build, twitter.build):
            with self.subTest(build.__module__):
                self.assertEqual(dumps(build()), dumps(build()))

    def test_output_is_valid_json_and_carries_its_version(self):
        payload = json.loads(dumps(url_shortener.build()))
        self.assertEqual(payload["spec_version"], SPEC_VERSION)


class PrimeDirectiveTest(unittest.TestCase):
    def test_the_spec_carries_inputs_only_never_results(self):
        """A saved design must not embed a stale verdict; the engine recomputes from inputs."""
        blob = json.dumps(to_dict(twitter.build()))
        # Engine-output keys only. `confidence` is deliberately NOT in this list: it is an INPUT on
        # Assumption (low/med/high), not the engine's stability qualifier — checking for the bare
        # word would fail on a legitimate field, which is a false positive, not a finding.
        for leaked in ("bottleneck", "utilization", "utilisation", "breakpoint_rps",
                       "mean_latency_ms", "p50_ms", "p95_ms", "p99_ms", "derivation", "saturated"):
            self.assertNotIn(leaked, blob, f"spec must not carry engine output ({leaked})")


class FailClosedTest(unittest.TestCase):
    def setUp(self):
        self.good = to_dict(url_shortener.build())

    def test_unknown_spec_version_is_refused(self):
        bad = {**self.good, "spec_version": SPEC_VERSION + 1}
        with self.assertRaises(ExportError):
            from_dict(bad)

    def test_missing_spec_version_is_refused(self):
        bad = {k: v for k, v in self.good.items() if k != "spec_version"}
        with self.assertRaises(ExportError):
            from_dict(bad)

    def test_unknown_component_kind_is_refused(self):
        bad = json.loads(json.dumps(self.good))
        bad["components"][0]["kind"] = "quantum_computer"
        with self.assertRaises(ExportError) as ctx:
            from_dict(bad)
        self.assertIn("unknown component kind", str(ctx.exception))

    def test_a_flow_referencing_an_unknown_component_is_refused(self):
        bad = json.loads(json.dumps(self.good))
        bad["flows"][0]["path"][0]["component_id"] = "ghost"
        with self.assertRaises(ExportError) as ctx:
            from_dict(bad)
        self.assertIn("unknown component", str(ctx.exception))

    def test_duplicate_component_ids_are_refused(self):
        bad = json.loads(json.dumps(self.good))
        bad["components"].append(dict(bad["components"][0]))
        with self.assertRaises(ExportError):
            from_dict(bad)

    def test_malformed_json_is_an_export_error_not_a_json_error(self):
        with self.assertRaises(ExportError):
            loads("{not json")

    def test_a_non_object_payload_is_refused(self):
        for payload in ("[]", '"a string"', "42"):
            with self.subTest(payload):
                with self.assertRaises(ExportError):
                    loads(payload)

    def test_an_invalid_model_is_refused_by_validate(self):
        """A spec cannot smuggle in a model the engine would reject."""
        bad = json.loads(json.dumps(self.good))
        bad["components"][0]["per_instance_rps"] = 0
        with self.assertRaises(ExportError):
            from_dict(bad)


class OrphanTest(unittest.TestCase):
    """An unwired component is a design smell, surfaced rather than hard-failed (docs/13)."""

    def test_orphans_are_reported_not_rejected(self):
        build = next(b for n, b, _ in REFERENCE_MODELS if n == "distributed_cache")
        model = build()
        self.assertEqual(orphans(model), ["coord"])
        self.assertEqual(loads(dumps(model)), model, "an orphan must still round-trip")

    def test_a_fully_wired_model_reports_none(self):
        self.assertEqual(orphans(url_shortener.build()), [])

    def test_an_orphan_costs_money_while_reporting_zero_utilisation(self):
        """Why it is worth surfacing: it reads as 'plenty of headroom' and still bills."""
        build = next(b for n, b, _ in REFERENCE_MODELS if n == "distributed_cache")
        model = build()
        result = simulate(model)
        self.assertEqual(result.components["coord"].arrival_rps, 0.0)
        self.assertEqual(result.components["coord"].utilization, 0.0)
        self.assertGreater(model.components["coord"].monthly_cost, 0)


if __name__ == "__main__":
    unittest.main()
