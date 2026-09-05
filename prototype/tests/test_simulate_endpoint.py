"""Tests for POST /simulate — the stateless canvas-topology → engine-verdict endpoint."""
import unittest

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_TOPO = {
    "name": "Canvas test", "system_rps": 10_000,
    "nodes": [
        {"id": "client", "kind": "client", "name": "Users"},
        {"id": "lb", "kind": "load_balancer", "name": "LB"},
        {"id": "app", "kind": "app_server", "name": "App", "instances": 12},
        {"id": "cache", "kind": "cache", "name": "Cache"},
        {"id": "db", "kind": "sql_db", "name": "DB"},
    ],
    "edges": [["client", "lb"], ["lb", "app"], ["app", "cache"], ["app", "db"]],
}


class TestSimulateEndpoint(unittest.TestCase):
    def test_valid_topology_returns_engine_verdict(self):
        r = client.post("/simulate", json=_TOPO)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        # arch-map shape — engine-computed verdict + nodes with icons/roles
        self.assertIn("verdict", d)
        self.assertIsNotNone(d["verdict"]["bottleneck_id"])
        self.assertTrue(d["nodes"])
        self.assertTrue(all("icon" in n and "role" in n for n in d["nodes"]))

    def test_no_auth_required(self):
        # Stateless compute: no Authorization header, still 200 (NOT 401) — unlike /design.
        r = client.post("/simulate", json=_TOPO)
        self.assertEqual(r.status_code, 200)

    def test_bad_kind_is_400_not_500(self):
        bad = {"nodes": [{"id": "x", "kind": "not_a_real_kind", "name": "X"}]}
        r = client.post("/simulate", json=bad)
        self.assertEqual(r.status_code, 400)   # fail-closed, clean client error

    def test_empty_topology_is_400(self):
        r = client.post("/simulate", json={"nodes": []})
        self.assertEqual(r.status_code, 400)

    def test_client_only_topology_is_400(self):
        r = client.post("/simulate", json={"nodes": [{"id": "c", "kind": "client", "name": "U"}]})
        self.assertEqual(r.status_code, 400)

    def test_nonpositive_rps_rejected_at_edge(self):
        bad = dict(_TOPO); bad["system_rps"] = 0
        r = client.post("/simulate", json=bad)
        self.assertEqual(r.status_code, 422)   # pydantic gt=0 rejects before the handler

    def test_render_flag_returns_self_contained_html(self):
        # render:true → the studio can re-render the animated map for an edited topology.
        r = client.post("/simulate", json={**_TOPO, "render": True})
        self.assertEqual(r.status_code, 200)
        html = r.json().get("html", "")
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html"))
        self.assertIn("arch-data", html)

    def test_render_omitted_by_default(self):
        self.assertNotIn("html", client.post("/simulate", json=_TOPO).json())


if __name__ == "__main__":
    unittest.main()
