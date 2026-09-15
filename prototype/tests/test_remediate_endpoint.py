"""Tests for POST /remediate — the stateless capacity-sizing endpoint."""
import unittest

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
INTENT = "a URL shortener, mostly reads"


class TestRemediateEndpoint(unittest.TestCase):
    def test_sizes_a_saturated_design_and_proves_it_holds(self):
        r = client.post("/remediate", json={"intent": INTENT, "target_rps": 20_000})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["holds"])
        self.assertTrue(d["remedies"])
        self.assertLessEqual(d["after"]["bottleneck_utilization"], d["ceiling"])
        self.assertGreater(d["before"]["bottleneck_utilization"], d["ceiling"])

    def test_cost_delta_is_the_difference_of_the_two_runs(self):
        d = client.post("/remediate", json={"intent": INTENT, "target_rps": 20_000}).json()
        self.assertEqual(
            d["monthly_cost_delta_cents"],
            d["after"]["monthly_cost_cents"] - d["before"]["monthly_cost_cents"])
        self.assertIsInstance(d["monthly_cost_delta_cents"], int)

    def test_returns_a_renderable_map_of_the_fixed_design(self):
        d = client.post("/remediate", json={"intent": INTENT, "target_rps": 20_000}).json()
        after = d["after_map"]
        for key in ("nodes", "flows", "verdict", "meta", "caveats"):
            self.assertIn(key, after)
        scaled = {r["component_id"]: r["to_instances"] for r in d["remedies"]}
        for node in after["nodes"]:
            if node["id"] in scaled:
                self.assertEqual(node["instances"], scaled[node["id"]],
                                 "the returned map must BE the fixed design")

    def test_publishes_its_limits_and_its_working(self):
        d = client.post("/remediate", json={"intent": INTENT, "target_rps": 20_000}).json()
        self.assertGreaterEqual(len(d["limits"]), 4)
        self.assertIn("linear", " ".join(d["limits"]).lower())
        self.assertTrue(d["derivation"])

    def test_a_wall_is_reported_as_a_blocker_with_guidance(self):
        """Past the point where scaling helps, the primary must be named, not sized."""
        d = client.post("/remediate", json={"intent": INTENT, "target_rps": 400_000}).json()
        self.assertFalse(d["holds"])
        self.assertTrue(d["blockers"])
        blocked_kinds = {b["kind"] for b in d["blockers"]}
        self.assertIn("sql_db", blocked_kinds)
        for b in d["blockers"]:
            self.assertGreater(len(b["guidance"]), 80)
        self.assertNotIn("sql_db", {r["kind"] for r in d["remedies"]})

    def test_no_change_needed_at_the_design_load(self):
        d = client.post("/remediate", json={"intent": INTENT}).json()
        self.assertEqual(d["remedies"], [])
        self.assertEqual(d["monthly_cost_delta_cents"], 0)
        self.assertTrue(d["holds"])

    def test_topology_mode(self):
        r = client.post("/remediate", json={
            "name": "drawn", "system_rps": 40_000,
            "nodes": [{"id": "lb", "kind": "load_balancer"},
                      {"id": "app", "kind": "app_server", "instances": 2},
                      {"id": "db", "kind": "sql_db"}],
            "edges": [["lb", "app"], ["app", "db"]],
            "target_rps": 40_000})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["verdict"])

    def test_no_auth_required(self):
        r = client.post("/remediate", json={"intent": INTENT, "target_rps": 12_000})
        self.assertEqual(r.status_code, 200)

    def test_bad_target_is_rejected_at_the_edge(self):
        r = client.post("/remediate", json={"intent": INTENT, "target_rps": -5})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
