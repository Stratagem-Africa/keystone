"""Twitter-scale platform — the DEPTH reference: a full, layered, multi-service topology, not a sketch.

This blueprint defines the TARGET depth that "build a platform like Twitter" should generate
(keystone.generate maps that intent here offline). The engine still owns every number.
"""
from __future__ import annotations

import unittest

from keystone.blueprints import twitter
from keystone.ingestion import validate_model
from keystone.model import ComponentKind
from keystone.simulation import simulate


class TestTwitter(unittest.TestCase):
    def test_is_a_deep_layered_architecture(self):
        m = twitter.build()
        validate_model(m)  # fail-closed: valid, connected, simulate-able
        self.assertGreaterEqual(len(m.components), 12, "a deep architecture, not a 4-box sketch")
        self.assertGreaterEqual(len(m.flows), 4, "multiple real request journeys")
        kinds = {c.kind for c in m.components.values()}
        # spans the layers a senior architect whiteboards: edge, gateway, compute, cache, data, async
        for layer in (ComponentKind.CDN, ComponentKind.LOAD_BALANCER, ComponentKind.API_GATEWAY,
                      ComponentKind.APP_SERVER, ComponentKind.CACHE, ComponentKind.SQL_DB,
                      ComponentKind.REPLICA, ComponentKind.QUEUE, ComponentKind.OBJECT_STORE,
                      ComponentKind.EXTERNAL_API):
            self.assertIn(layer, kinds, f"missing layer: {layer.value}")

    def test_flow_shares_sum_to_one(self):
        m = twitter.build()
        self.assertAlmostEqual(sum(f.share for f in m.flows), 1.0, places=6)

    def test_engine_finds_the_write_datastore_as_the_constraint(self):
        # Read-heavy social feed: the write-path primary DB binds, not the cached read path.
        r = simulate(twitter.build())
        self.assertEqual(r.bottleneck_id, "tweetsdb")
        self.assertGreater(r.bottleneck_utilization, 0.5)

    def test_single_primary_datastores_are_spofs(self):
        r = simulate(twitter.build())
        self.assertIn("Tweets DB (primary)", r.spofs)
        self.assertIn("Users/Graph DB (primary)", r.spofs)

    def test_cost_is_integer_minor_units(self):
        self.assertIsInstance(simulate(twitter.build()).monthly_cost, int)  # harm floor


if __name__ == "__main__":
    unittest.main()
