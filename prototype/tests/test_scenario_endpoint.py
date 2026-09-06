"""Tests for POST /scenario — the stateless chaos counterfactual endpoint.

The regression these exist to prevent: the catalogue and the run must be computed on the SAME
model. A generated design carries flow branch probabilities (a cache-miss path); rebuilding it from
a canvas topology flattens every step to certainty. Offer a scenario from one model and run it
against the other, and the panel shows a card that then refuses — the dead-button failure the
scenario layer is built to make impossible.
"""
import unittest

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

INTENT = "a URL shortener, mostly reads"


def _catalogue(payload: dict) -> dict[str, dict]:
    return {s["key"]: s for s in payload["scenarios"]}


class TestScenarioCatalogue(unittest.TestCase):
    def test_generate_carries_the_catalogue_and_the_unmodelled_register(self):
        d = client.post("/generate", json={"intent": INTENT}).json()
        self.assertIn("scenarios", d)
        self.assertIn("unmodelled", d)
        self.assertGreater(len(d["scenarios"]), 0)
        self.assertGreaterEqual(len(d["unmodelled"]), 4, "the refuse-to-fake register must ship")
        for s in d["scenarios"]:
            self.assertTrue(s["question"] and s["caveat"], f"{s['key']} must declare both")

    def test_simulate_carries_a_catalogue_for_the_drawn_topology(self):
        r = client.post("/simulate", json={
            "name": "drawn", "system_rps": 10_000,
            "nodes": [{"id": "lb", "kind": "load_balancer"}, {"id": "app", "kind": "app_server"},
                      {"id": "db", "kind": "sql_db"}],
            "edges": [["lb", "app"], ["app", "db"]]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("scenarios", r.json())


class TestCatalogueMatchesTheRun(unittest.TestCase):
    """Every card the API offers must actually run against the model it was offered for."""

    def test_every_generated_scenario_runs_in_intent_mode(self):
        d = client.post("/generate", json={"intent": INTENT}).json()
        self.assertGreater(len(d["scenarios"]), 0)
        for s in d["scenarios"]:
            with self.subTest(s["key"]):
                r = client.post("/scenario", json={
                    "intent": INTENT, "scenario_id": s["id"], "target_id": s["target_id"]})
                self.assertEqual(r.status_code, 200, r.text)

    def test_every_drawn_scenario_runs_in_topology_mode(self):
        topology = {
            "name": "drawn", "system_rps": 10_000,
            "nodes": [{"id": "lb", "kind": "load_balancer"}, {"id": "app", "kind": "app_server",
                      "instances": 4}, {"id": "ch", "kind": "cache"}, {"id": "db", "kind": "sql_db"}],
            "edges": [["lb", "app"], ["app", "ch"], ["ch", "db"]]}
        d = client.post("/simulate", json=topology).json()
        for s in d["scenarios"]:
            with self.subTest(s["key"]):
                r = client.post("/scenario", json={
                    **topology, "scenario_id": s["id"], "target_id": s["target_id"]})
                self.assertEqual(r.status_code, 200, r.text)

    def test_a_generated_design_rebuilt_as_topology_loses_its_miss_path(self):
        """The exact bug this endpoint's `intent` mode exists to avoid — pinned so it cannot return.

        `cache_cold` is offered for the generated design (it has a 10% miss path). Rebuilt from a
        flat topology the same scenario is correctly REFUSED, which is why the studio must send the
        intent rather than the reconstructed topology.
        """
        gen = client.post("/generate", json={"intent": INTENT}).json()
        cold = [s for s in gen["scenarios"] if s["id"] == "cache_cold"]
        self.assertTrue(cold, "the generated url-shortener design should offer cache_cold")
        target = cold[0]["target_id"]

        ok = client.post("/scenario", json={
            "intent": INTENT, "scenario_id": "cache_cold", "target_id": target})
        self.assertEqual(ok.status_code, 200, "intent mode preserves the miss path")
        self.assertTrue(ok.json()["delta"]["bottleneck_moved"])

        nodes = [{"id": n["id"], "kind": n["kind"]} for n in gen["nodes"]]
        edges = []
        for f in gen["flows"]:
            ids = [st["component_id"] for st in f["steps"]]
            edges += [[a, b] for a, b in zip(ids, ids[1:])]
        flat = client.post("/scenario", json={
            "name": "rebuilt", "system_rps": 10_000, "nodes": nodes, "edges": edges,
            "scenario_id": "cache_cold", "target_id": target})
        self.assertEqual(flat.status_code, 400, "a flattened topology must refuse, not silently no-op")
        self.assertIn("miss path", flat.json()["detail"])


class TestScenarioResponse(unittest.TestCase):
    def test_delta_reduces_to_the_two_engine_runs(self):
        r = client.post("/scenario", json={"intent": INTENT, "scenario_id": "traffic_surge"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        for key in ("baseline", "perturbed", "delta", "scenario"):
            self.assertIn(key, d)
        delta = d["delta"]
        self.assertAlmostEqual(
            delta["latency_multiple"],
            delta["perturbed_latency_ms"] / delta["baseline_latency_ms"], places=6)
        self.assertTrue(delta["derivation"], "the delta must show its working")
        self.assertTrue(delta["perturbed_confidence"], "each side keeps its own confidence")
        self.assertEqual(d["baseline"]["verdict"]["bottleneck_name"], delta["baseline_bottleneck"])

    def test_both_sides_are_full_arch_maps(self):
        r = client.post("/scenario", json={"intent": INTENT, "scenario_id": "traffic_surge"})
        d = r.json()
        for side in ("baseline", "perturbed"):
            with self.subTest(side):
                arch = d[side]
                self.assertTrue(arch["nodes"] and arch["flows"] and arch["caveats"])
                self.assertTrue(arch["derivation"], "each run keeps the engine's own derivation")

    def test_no_auth_required(self):
        r = client.post("/scenario", json={"intent": INTENT, "scenario_id": "traffic_surge"})
        self.assertEqual(r.status_code, 200)


class TestScenarioFailsClosed(unittest.TestCase):
    def test_unknown_scenario_is_400(self):
        r = client.post("/scenario", json={"intent": INTENT, "scenario_id": "does_not_exist"})
        self.assertEqual(r.status_code, 400)

    def test_missing_target_is_400(self):
        r = client.post("/scenario", json={"intent": INTENT, "scenario_id": "cache_cold"})
        self.assertEqual(r.status_code, 400)

    def test_wrong_kind_target_is_400(self):
        gen = client.post("/generate", json={"intent": INTENT}).json()
        db = next(n["id"] for n in gen["nodes"] if n["kind"] == "sql_db")
        r = client.post("/scenario", json={
            "intent": INTENT, "scenario_id": "cache_cold", "target_id": db})
        self.assertEqual(r.status_code, 400)

    def test_scenario_id_is_required(self):
        r = client.post("/scenario", json={"intent": INTENT})
        self.assertEqual(r.status_code, 422, "pydantic rejects a missing scenario_id at the edge")


class TestMagnitudeAndCompound(unittest.TestCase):
    def test_catalogue_publishes_selectable_magnitudes(self):
        d = client.post("/generate", json={"intent": INTENT}).json()
        parameterised = [s for s in d["scenarios"] if s["magnitudes"]]
        self.assertTrue(parameterised, "some scenarios must be dial-able")
        for s in parameterised:
            self.assertTrue(s["magnitude_unit"])
            self.assertEqual(s["default_magnitude"], s["magnitudes"][0])

    def test_a_magnitude_the_catalogue_did_not_offer_is_refused(self):
        r = client.post("/scenario", json={
            "intent": INTENT, "scenario_id": "traffic_surge", "magnitude": 7})
        self.assertEqual(r.status_code, 400)

    def test_compound_runs_and_reports_every_part(self):
        r = client.post("/scenario", json={"intent": INTENT, "specs": [
            {"scenario_id": "cache_cold", "target_id": "cache"},
            {"scenario_id": "slow_dependency", "target_id": "db", "magnitude": 100},
        ]})
        self.assertEqual(r.status_code, 200, r.text)
        applied = r.json()["scenario"]["applied"]
        self.assertEqual(len(applied), 2)
        self.assertEqual(applied[1]["magnitude"], 100)

    def test_exactly_one_form_is_accepted(self):
        both = client.post("/scenario", json={
            "intent": INTENT, "scenario_id": "cache_cold",
            "specs": [{"scenario_id": "cache_cold"}]})
        self.assertEqual(both.status_code, 422)
        neither = client.post("/scenario", json={"intent": INTENT})
        self.assertEqual(neither.status_code, 422)

    def test_duplicate_targets_in_a_compound_are_refused(self):
        r = client.post("/scenario", json={"intent": INTENT, "specs": [
            {"scenario_id": "cache_cold", "target_id": "cache"},
            {"scenario_id": "cache_cold", "target_id": "cache"},
        ]})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
