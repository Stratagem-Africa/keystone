"""Tests for POST /generate — the stateless intent → deep-architecture endpoint (offline reference path)."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestGenerateEndpoint(unittest.TestCase):
    def test_twitter_intent_returns_deep_arch_map(self):
        r = client.post("/generate", json={"intent": "I want to build a platform like Twitter"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("verdict", d)
        self.assertIsNotNone(d["verdict"]["bottleneck_id"])
        self.assertGreaterEqual(len(d["nodes"]), 12, "a deep architecture, not a sketch")
        self.assertTrue(all("icon" in n and "role" in n for n in d["nodes"]))

    def test_no_auth_required(self):
        # Stateless compute — like /simulate, NOT auth-gated.
        r = client.post("/generate", json={"intent": "a url shortener"})
        self.assertEqual(r.status_code, 200)

    def test_unknown_intent_still_returns_a_valid_startingpoint_with_catalogue(self):
        r = client.post("/generate", json={"intent": "a quantum weather oracle for llamas"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["nodes"])                 # a real, editable starting point
        self.assertIsNone(d["matched"])             # honest: nothing matched offline → generic fallback
        self.assertIn("social platform", d["catalogue"])  # hint: try one of these offline

    def test_matched_reports_the_reference_used(self):
        d = client.post("/generate", json={"intent": "a platform like twitter"}).json()
        self.assertEqual(d["matched"], "social platform")

    def test_public_surface_stays_offline_even_if_llm_activated(self):
        # Harm floor: the public, unauthenticated /generate must NEVER reach a live LLM (unmetered
        # anonymous spend). Even with INGEST_PROVIDER set to a live provider, it stays on the $0
        # offline reference path — proven here by getting a clean 200 deep map with no key/network.
        with mock.patch.dict("os.environ", {"INGEST_PROVIDER": "claude", "INGEST_MODEL": "claude-haiku-4-5-20251001"}):
            r = client.post("/generate", json={"intent": "a platform like twitter"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertGreaterEqual(len(d["nodes"]), 12)   # the offline deep reference, not an LLM/network call
        self.assertEqual(d["matched"], "social platform")

    def test_empty_intent_is_422(self):
        r = client.post("/generate", json={"intent": ""})
        self.assertEqual(r.status_code, 422)        # pydantic min_length rejects before the handler

    def test_render_flag_returns_self_contained_html(self):
        r = client.post("/generate", json={"intent": "like twitter", "render": True})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertIn("html", d)
        html = d["html"]
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html"))
        self.assertIn("arch-data", html)               # the data island the renderer reads
        self.assertNotIn("</script><script>alert", html)  # island is <>&-neutralised (XSS defence)

    def test_render_omitted_by_default(self):
        r = client.post("/generate", json={"intent": "like twitter"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("html", r.json())             # lean by default (canvas/tests don't want 58KB)


if __name__ == "__main__":
    unittest.main()


class RightClickResizeTest(unittest.TestCase):
    """Right-clicking a tier on the canvas sends {instances:{id:n}}; "Fix the whole design for me"
    sends autosize. Both re-run the ENGINE on the edited design — nothing is patched in place, so
    every number that comes back is a real simulation rather than the old one with a box drawn on it.
    """

    def _gen(self, body):
        r = client.post("/generate", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_adding_instances_changes_the_engine_result(self):
        base = self._gen({"intent": "a url shortener"})["verdict"]
        more = self._gen({"intent": "a url shortener", "instances": {"app": 24}})["verdict"]
        self.assertLess(more["bottleneck_utilization"], base["bottleneck_utilization"])
        self.assertGreater(more["monthly_cost_cents"], base["monthly_cost_cents"])
        self.assertGreater(more["breakpoint_rps_safe"], base["breakpoint_rps_safe"])

    def test_autosize_repairs_a_design_the_edit_broke(self):
        """The order matters: autosize must run AFTER the manual edits, or the edit re-breaks it
        and the button appears to do nothing."""
        broken = self._gen({"intent": "a platform like Twitter", "instances": {"web": 2}})["verdict"]
        self.assertGreater(broken["bottleneck_utilization"], 1.0)
        fixed = self._gen({"intent": "a platform like Twitter",
                           "instances": {"web": 2}, "autosize": True})["verdict"]
        self.assertLessEqual(fixed["bottleneck_utilization"], 0.85)

    def test_a_bad_component_id_is_a_clean_400(self):
        r = client.post("/generate", json={"intent": "a url shortener", "instances": {"nope": 3}})
        self.assertEqual(r.status_code, 400)

    def test_zero_or_absurd_counts_are_refused(self):
        """0 instances is a component that does not exist (hard_node_failure — UNMODELLED), and an
        unbounded count would let a caller drive an arbitrarily expensive simulate()."""
        for n in (0, -1, 10_001):
            with self.subTest(n=n):
                r = client.post("/generate", json={"intent": "a url shortener", "instances": {"app": n}})
                self.assertEqual(r.status_code, 422)
