"""Tests for the loopback-only local AI routes (#204) and the guard that is their whole safety case.

The guard replaces the Supabase login on these routes, so it is tested from the refusing side first:
every way a caller who is NOT the person at this machine could arrive must get a 403.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import jobs
from api.main import app
from keystone.blueprints.url_shortener import build as build_url_shortener
from keystone.llm import LLMError

ON = {"KEYSTONE_ALLOW_CLI_IN_SERVER": "1"}

# A request from this machine, addressed to this machine — the only shape the guard lets through.
local = TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1:8000")


class TestLocalGuard(unittest.TestCase):
    def test_refuses_without_the_launcher_override(self):
        with mock.patch.dict("os.environ", {"KEYSTONE_ALLOW_CLI_IN_SERVER": ""}):
            r = local.post("/local/generate", json={"intent": "a url shortener"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("keystone-local.sh", r.json()["detail"])   # loud about WHY, and the way out

    def test_refuses_a_caller_from_another_machine(self):
        remote = TestClient(app, client=("203.0.113.7", 50000), base_url="http://127.0.0.1:8000")
        with mock.patch.dict("os.environ", ON):
            r = remote.post("/local/generate", json={"intent": "a url shortener"})
        self.assertEqual(r.status_code, 403)

    def test_refuses_a_foreign_host_header(self):
        # DNS rebinding: a page on evil.example resolves its own name to 127.0.0.1. The TCP peer is
        # loopback, but the Host header gives it away.
        with mock.patch.dict("os.environ", ON):
            r = local.post("/local/generate", json={"intent": "a url shortener"},
                           headers={"host": "evil.example:8000"})
        self.assertEqual(r.status_code, 403)

    def test_accepts_localhost_and_ipv6_loopback_host_names(self):
        with mock.patch.dict("os.environ", ON):
            for host in ("localhost:8000", "[::1]:8000", "127.0.0.1"):
                d = local.get("/local/status", headers={"host": host}).json()
                self.assertTrue(d["available"], host)

    def test_status_reports_instead_of_refusing(self):
        with mock.patch.dict("os.environ", {"KEYSTONE_ALLOW_CLI_IN_SERVER": ""}):
            r = local.get("/local/status")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["available"])
        self.assertTrue(r.json()["reason"])


class TestLocalGenerate(unittest.TestCase):
    def test_uses_the_configured_provider_not_the_stub_pin(self):
        # Prove the LLM path is taken: generate_architecture must be called WITHOUT provider="stub".
        with mock.patch.dict("os.environ", {**ON, "INGEST_PROVIDER": "claude_cli"}), \
             mock.patch("api.main.generate_architecture",
                        return_value=build_url_shortener()) as gen:
            r = local.post("/local/generate", json={"intent": "a url shortener"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("provider", gen.call_args.kwargs)
        self.assertIsNotNone(gen.call_args.kwargs["meter"])           # spend-capped
        d = r.json()
        self.assertEqual(d["provider"], "claude_cli")
        self.assertIn("verdict", d)
        self.assertIn("components", d["spec"])                        # the exact design, for edits

    def test_llm_failure_is_a_clean_503(self):
        with mock.patch.dict("os.environ", ON), \
             mock.patch("api.main.generate_architecture", side_effect=LLMError("claude not on PATH")):
            r = local.post("/local/generate", json={"intent": "a url shortener"})
        self.assertEqual(r.status_code, 503)

    def test_spec_round_trips_through_public_generate_without_the_llm(self):
        # The studio's follow-up edits send the spec to /generate: same design, re-simulated, no LLM.
        with mock.patch.dict("os.environ", ON):
            first = local.post("/local/generate", json={"intent": "a url shortener"}).json()
        again = local.post("/generate", json={"spec": first["spec"]}).json()
        self.assertEqual(sorted(n["id"] for n in again["nodes"]),
                         sorted(n["id"] for n in first["nodes"]))
        self.assertEqual(again["verdict"], first["verdict"])          # deterministic: same model, same numbers


class TestSpecSubject(unittest.TestCase):
    def setUp(self):
        with mock.patch.dict("os.environ", ON):
            d = local.post("/local/generate", json={"intent": "a url shortener"}).json()
        self.spec = d["spec"]
        self.scenario = d["scenarios"][0]                             # one THIS design can truthfully run

    def test_spec_works_on_every_design_route(self):
        self.assertEqual(local.post("/export", json={"spec": self.spec}).status_code, 200)
        self.assertEqual(local.post("/loadtest", json={"spec": self.spec}).status_code, 200)
        self.assertEqual(local.post("/remediate", json={"spec": self.spec}).status_code, 200)
        r = local.post("/scenario", json={"spec": self.spec, "scenario_id": self.scenario["id"],
                                          "target_id": self.scenario["target_id"]})
        self.assertEqual(r.status_code, 200, r.text)

    def test_intent_and_spec_together_is_rejected(self):
        r = local.post("/export", json={"spec": self.spec, "intent": "a url shortener"})
        self.assertEqual(r.status_code, 422)
        r = local.post("/generate", json={"spec": self.spec, "intent": "a url shortener"})
        self.assertEqual(r.status_code, 422)

    def test_generate_needs_one_of_intent_or_spec(self):
        self.assertEqual(local.post("/generate", json={}).status_code, 422)

    def test_bad_spec_is_a_clean_400(self):
        self.assertEqual(local.post("/generate", json={"spec": {"version": 999}}).status_code, 400)


STUB = {**ON, "INGEST_PROVIDER": "stub", "COUNCIL_PROVIDER": "stub"}   # offline, $0 — no real LLM in tests


class TestLocalIntentPipeline(unittest.TestCase):
    def setUp(self):
        jobs._store.clear()

    def test_refuses_without_the_launcher_override(self):
        with mock.patch.dict("os.environ", {"KEYSTONE_ALLOW_CLI_IN_SERVER": ""}):
            self.assertEqual(local.post("/local/intent", data={"text": "a url shortener at 5k rps"}).status_code, 403)
            self.assertEqual(local.get("/local/jobs/anything").status_code, 403)

    def test_full_pipeline_runs_with_no_login(self):
        # TestClient runs background tasks before returning, so the job has finished by the next line.
        with mock.patch.dict("os.environ", STUB):
            r = local.post("/local/intent", data={"text": "a url shortener at 5k requests a second"})
            self.assertEqual(r.status_code, 200, r.text)
            job_id = r.json()["job_id"]
            self.assertEqual(local.get(f"/local/jobs/{job_id}").json()["status"], "done")
            report = local.get(f"/local/jobs/{job_id}/report?fmt=markdown")
            self.assertEqual(report.status_code, 200)
            self.assertIn("#", report.text)                                # a markdown report
            html = local.get(f"/local/jobs/{job_id}/archmap?fmt=html")
            self.assertTrue(html.text.lstrip().lower().startswith("<!doctype html"))

    def test_same_intake_rules_as_intent(self):
        with mock.patch.dict("os.environ", STUB):
            self.assertEqual(local.post("/local/intent", data={"text": "short"}).status_code, 422)
            r = local.post("/local/intent", data={"text": "a store"},
                           files={"file": ("brief.pdf", b"%PDF", "application/pdf")})
            self.assertEqual(r.status_code, 400)

    def test_local_jobs_stay_in_memory_and_out_of_reach_of_signed_in_users(self):
        with mock.patch.dict("os.environ", STUB):
            job_id = local.post("/local/intent", data={"text": "a url shortener at 5k rps"}).json()["job_id"]
        # A real Supabase user (any other id) cannot see it — same "not found" as a missing job.
        self.assertIsNone(jobs.get_job(job_id, user_id="user-123", access_token=""))
        self.assertEqual(jobs._store[job_id].user_id, "local")


if __name__ == "__main__":
    unittest.main()
