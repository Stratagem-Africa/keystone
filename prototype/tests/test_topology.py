"""Tests for topology.py — the deterministic canvas-topology -> validated SystemModel seam."""
import unittest

from keystone.ingestion import IngestError
from keystone.model import ComponentKind
from keystone.simulation import simulate
from keystone.topology import build_model_from_topology

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


class TestTopology(unittest.TestCase):
    def test_builds_valid_simulatable_model(self):
        m = build_model_from_topology(_TOPO)
        self.assertEqual(set(m.components), {"lb", "app", "cache", "db"})  # client excluded
        self.assertTrue(m.flows)
        self.assertAlmostEqual(sum(f.share for f in m.flows), 1.0, places=5)
        sim = simulate(m)                       # the engine runs on it
        self.assertIsNotNone(sim.bottleneck_id)

    def test_client_is_traffic_source_not_a_component(self):
        m = build_model_from_topology(_TOPO)
        self.assertNotIn("client", m.components)
        # ...and never appears on a flow path
        self.assertNotIn("client", {s.component_id for f in m.flows for s in f.path})

    def test_flows_derived_from_the_graph(self):
        m = build_model_from_topology(_TOPO)
        paths = {tuple(s.component_id for s in f.path) for f in m.flows}
        # the app->cache / app->db branch yields two entry->terminal paths
        self.assertIn(("lb", "app", "cache"), paths)
        self.assertIn(("lb", "app", "db"), paths)

    def test_per_node_overrides_are_honoured(self):
        topo = {"nodes": [{"id": "a", "kind": "app_server", "name": "A",
                           "per_instance_rps": 999, "instances": 4, "base_latency_ms": 3,
                           "monthly_cost_cents": 7777}]}
        m = build_model_from_topology(topo)
        c = m.components["a"]
        self.assertEqual((c.per_instance_rps, c.instances, c.base_latency_ms), (999.0, 4, 3.0))
        self.assertEqual(c.monthly_cost_per_instance, 7777)

    def test_unspecified_capacity_gets_a_positive_default(self):
        m = build_model_from_topology({"nodes": [{"id": "d", "kind": "sql_db", "name": "D"}]})
        self.assertGreater(m.components["d"].per_instance_rps, 0)   # seed-or-grounded, never 0/invalid

    def test_provenance_is_assumption(self):
        m = build_model_from_topology(_TOPO)
        self.assertTrue(all(c.provenance == "ASSUMPTION" for c in m.components.values()))

    def test_fail_closed_on_empty_topology(self):
        with self.assertRaises(IngestError):
            build_model_from_topology({"nodes": []})

    def test_fail_closed_on_client_only(self):
        with self.assertRaises(IngestError):
            build_model_from_topology({"nodes": [{"id": "c", "kind": "client", "name": "U"}]})

    def test_single_node_no_edges_still_simulates(self):
        m = build_model_from_topology({"nodes": [{"id": "app", "kind": "app_server", "name": "A"}]})
        self.assertEqual(len(m.flows), 1)                          # one flow over the lone component
        self.assertIsNotNone(simulate(m).bottleneck_id)

    def test_deterministic(self):
        a, b = build_model_from_topology(_TOPO), build_model_from_topology(_TOPO)
        self.assertEqual(list(a.components), list(b.components))
        self.assertEqual([(f.name, f.share) for f in a.flows], [(f.name, f.share) for f in b.flows])

    def test_prime_directive_no_metric_inputs(self):
        # topology carries only INPUT structure; a derived metric key must never become a component field.
        m = build_model_from_topology(_TOPO)
        for c in m.components.values():
            self.assertIsInstance(c.kind, ComponentKind)
            self.assertGreater(c.per_instance_rps, 0)


if __name__ == "__main__":
    unittest.main()
