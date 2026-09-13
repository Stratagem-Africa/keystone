"""The double-decker: Keystone's personas as subagents inside one Claude Code call.

The point of these tests is that a SECOND deck of reasoning does not buy a weaker guard. The panel
runs through the same prime-directive scrub, the same ADR schema and the same provenance stamp as any
other council path — and it is explicit that agreement among subagents in one session is weaker
evidence than cross-vendor consensus.

Transport is mocked throughout: the gate stays $0, offline and deterministic.
"""
from __future__ import annotations

import json
import unittest
from unittest import mock

from keystone.blueprints import url_shortener
from keystone.claude_council import PERSONAS
from keystone.panel_council import PANEL_CAVEAT, PanelCouncil, build_agents_payload


def _panel_json(decision="Use cache-aside", rationale="Reads dominate.", dissent=None):
    return json.dumps([{
        "area": "Read path", "decision": decision, "rationale": rationale,
        "dissent": dissent or ["FinOps: a cache is another thing to run"],
        "confidence": "high", "kill_criteria": ["hit rate collapses"],
    }])


class _FakeLLM:
    """Captures what the panel would send, and returns a canned panel reply."""
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete(self, **kw):
        self.calls.append(kw)
        return self.reply


class AgentsPayloadTest(unittest.TestCase):
    def test_it_uses_keystones_own_personas(self):
        payload = json.loads(build_agents_payload())
        self.assertEqual(set(payload), {p.key for p in PERSONAS})
        self.assertEqual(len(payload), 7)

    def test_every_agent_carries_the_no_numbers_rule_itself(self):
        """The rule has to travel with the persona that might break it — putting it only in the
        outer prompt leaves a subagent free to invent a figure the outer turn then repeats."""
        for key, spec in json.loads(build_agents_payload()).items():
            with self.subTest(key):
                self.assertIn("number", spec["prompt"].lower())

    def test_each_agent_keeps_its_own_remit(self):
        payload = json.loads(build_agents_payload())
        for p in PERSONAS:
            self.assertIn(p.brief[:24], payload[p.key]["prompt"])


class GovernanceTest(unittest.TestCase):
    """A panel does not earn a weaker guard than a single model."""

    def test_a_number_invented_inside_the_panel_is_redacted(self):
        fake = _FakeLLM(_panel_json(decision="Use a cache; it serves 90k rps easily"))
        adrs = PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertNotIn("90k rps", adrs[0].decision)
        self.assertIn("engine-owned metric removed", adrs[0].decision)

    def test_the_redaction_is_disclosed_not_silent(self):
        fake = _FakeLLM(_panel_json(rationale="It costs about $4,000/month"))
        adrs = PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertIn("Prime-directive guard", adrs[0].rationale)

    def test_design_language_survives_untouched(self):
        fake = _FakeLLM(_panel_json(decision="Adopt cache-aside on the redirect path"))
        adrs = PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertEqual(adrs[0].decision, "Adopt cache-aside on the redirect path")

    def test_provenance_is_stamped(self):
        fake = _FakeLLM(_panel_json())
        adrs = PanelCouncil(transport=fake, model="opus").design(url_shortener.build())
        self.assertTrue(adrs[0].source.startswith("claude_panel:"))

    def test_dissent_is_preserved(self):
        fake = _FakeLLM(_panel_json(dissent=["SRE: this hides a failure mode"]))
        adrs = PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertEqual(list(adrs[0].dissent), ["SRE: this hides a failure mode"])


class HonestyAboutTheDeckTest(unittest.TestCase):
    def test_every_adr_says_what_panel_agreement_is_worth(self):
        fake = _FakeLLM(_panel_json())
        adrs = PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertEqual(adrs[0].consensus, PANEL_CAVEAT)

    def test_the_caveat_names_the_actual_limitation(self):
        low = PANEL_CAVEAT.lower()
        self.assertIn("one provider", low)
        self.assertIn("weaker evidence", low)
        self.assertIn("cross-vendor", low)


class MechanicsTest(unittest.TestCase):
    def test_it_is_one_call_not_one_per_persona(self):
        """The whole efficiency argument: 7 personas, 1 session."""
        fake = _FakeLLM(_panel_json())
        PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertEqual(len(fake.calls), 1)

    def test_the_agents_payload_is_actually_sent(self):
        fake = _FakeLLM(_panel_json())
        PanelCouncil(transport=fake).design(url_shortener.build())
        sent = json.loads(fake.calls[0]["agents"])
        self.assertEqual(set(sent), {p.key for p in PERSONAS})

    def test_the_brief_describes_the_system(self):
        fake = _FakeLLM(_panel_json())
        PanelCouncil(transport=fake).design(url_shortener.build())
        self.assertIn("URL Shortener", fake.calls[0]["user"])

    def test_a_non_array_reply_fails_closed(self):
        for bad in ('{"area": "x"}', "not json at all", "[]"):
            with self.subTest(bad):
                with self.assertRaises(Exception):
                    PanelCouncil(transport=_FakeLLM(bad)).design(url_shortener.build())

    def test_registered_as_a_council_provider(self):
        with mock.patch.dict("os.environ", {"COUNCIL_PROVIDER": "claude_panel"}, clear=False):
            from keystone.council import make_council
            self.assertIsInstance(make_council(), PanelCouncil)


if __name__ == "__main__":
    unittest.main()
