"""Twitter-scale platform — the DEPTH reference: a full, layered, multi-service topology, not a sketch.

This blueprint defines the TARGET depth that "build a platform like Twitter" should generate
(keystone.generate maps that intent here offline). The engine still owns every number.
"""
from __future__ import annotations

import math
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

    def test_the_reference_design_holds_at_its_own_stated_load(self):
        """This asserted `bottleneck_id == "tweetsdb"` with rho > 0.5, and that was PINNING A BUG.

        The blueprint shipped 15% of traffic as tweet-writes, which put 9,000 writes/s onto a
        9,000 rps primary — rho EXACTLY 1.000, a reference architecture that cannot absorb one more
        request. It read as survivable only because the engine clamped latency at rho=0.999 and
        printed a comfortable 51ms. A social timeline is one of the most read-skewed workloads
        there is (historically ~6k tweets/s against ~300k timeline reads/s), so 15% was also simply
        wrong about the domain. With the mix corrected the design holds, and the binding constraint
        is the third-party push provider — which `remediation.py` correctly refuses to scale out
        because you do not own it. That is a better lesson than a primary pinned at 100%.
        """
        from keystone.simulation import SAFE_UTILIZATION
        r = simulate(twitter.build())
        self.assertLessEqual(r.bottleneck_utilization, SAFE_UTILIZATION,
                             f"a reference design must hold at its own load; '{r.bottleneck_name}' "
                             f"is at {r.bottleneck_utilization:.1%}")
        self.assertTrue(math.isfinite(r.mean_latency_ms))
        self.assertEqual(r.bottleneck_id, "pushapi")

    def test_the_write_path_is_no_longer_the_constraint_but_is_still_a_spof(self):
        """Fixing the load mix must not quietly hide that a single primary is still a risk."""
        r = simulate(twitter.build())
        self.assertLess(r.components["tweetsdb"].utilization, 0.85)
        self.assertIn("Tweets DB (primary)", r.spofs)

    def test_single_primary_datastores_are_spofs(self):
        r = simulate(twitter.build())
        self.assertIn("Tweets DB (primary)", r.spofs)
        self.assertIn("Users/Graph DB (primary)", r.spofs)

    def test_cost_is_integer_minor_units(self):
        self.assertIsInstance(simulate(twitter.build()).monthly_cost, int)  # harm floor


if __name__ == "__main__":
    unittest.main()
