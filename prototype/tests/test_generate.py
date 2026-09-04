"""intent -> deep architecture generation (keystone.generate).

Covers the offline reference-library path (works today, $0) and the LLM design path (a fake client,
no key, no network). The engine still owns numbers — these only assert the generated INPUT *design*.
"""
import unittest

from keystone.generate import (
    generate_architecture, match_reference, reference_catalogue,
)
from keystone.ingestion import validate_model
from keystone.simulation import simulate


class TestReferenceMatch(unittest.TestCase):
    def test_twitter_intents_map_to_social_platform(self):
        for intent in ("I want to build a platform like Twitter",
                       "a social network for photos", "a microblog", "an app like Instagram"):
            ref = match_reference(intent)
            self.assertIsNotNone(ref, intent)
            self.assertEqual(ref[1], "social platform", intent)

    def test_payments_intents_map(self):
        for intent in ("an online store checkout", "a billing system", "a stripe-style payments API"):
            self.assertEqual(match_reference(intent)[1], "payments / checkout", intent)

    def test_ticket_and_shortener_intents_map(self):
        self.assertEqual(match_reference("a flash-sale ticket booking site")[1], "ticket booking")
        self.assertEqual(match_reference("a bitly-style url shortener")[1], "URL shortener")

    def test_unknown_intent_has_no_reference(self):
        self.assertIsNone(match_reference("a quantum weather oracle for llamas"))

    def test_catalogue_lists_all_references(self):
        cat = reference_catalogue()
        self.assertIn("social platform", cat)
        self.assertEqual(len(cat), 4)


class TestGenerateOffline(unittest.TestCase):
    def test_twitter_intent_generates_deep_valid_model(self):
        m = generate_architecture("build me something like Twitter")  # no provider -> offline
        validate_model(m)  # fail-closed: raises if invalid
        self.assertGreaterEqual(len(m.components), 12, "a 'deep' architecture, not a 4-box sketch")
        # it must actually simulate to an engine verdict (numbers come from the engine, not here)
        result = simulate(m)
        self.assertIsNotNone(result.bottleneck_id)

    def test_unknown_intent_falls_back_to_valid_starting_point(self):
        m = generate_architecture("a quantum weather oracle for llamas")
        validate_model(m)  # still a real, valid model the user can edit on the canvas
        self.assertTrue(m.components)


class _FakeIngestClient:
    """Stands in for a live LLM client (the `LLM` seam): returns a canned architecture JSON for any
    prompt. Matches the real transport contract — a `.complete(label, system, user, max_tokens)` str."""
    _JSON = (
        '{"name":"Generated","workload":{"system_rps":1000,"description":"x"},'
        '"components":['
        '{"id":"lb","kind":"load_balancer","name":"LB","per_instance_rps":20000,"instances":2},'
        '{"id":"app","kind":"app_server","name":"App","per_instance_rps":800,"instances":4},'
        '{"id":"db","kind":"sql_db","name":"DB","per_instance_rps":3000,"instances":1}],'
        '"flows":[{"name":"main","share":1.0,"path":['
        '{"component_id":"lb"},{"component_id":"app"},{"component_id":"db"}]}],'
        '"assumptions":[],"domain_flags":[]}'
    )

    def complete(self, *_a, **_k):
        return self._JSON


class TestGenerateLLM(unittest.TestCase):
    def test_client_triggers_llm_design_path(self):
        # Passing a client forces the LLM path even with INGEST_PROVIDER=stub — the LLM DESIGNS it.
        m = generate_architecture("anything at all", client=_FakeIngestClient())
        validate_model(m)
        self.assertEqual(m.name, "Generated")
        self.assertIn("app", m.components)


if __name__ == "__main__":
    unittest.main()
