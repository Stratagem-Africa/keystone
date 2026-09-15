"""The `claude_cli` transport: drive the user's own Claude Code CLI instead of a metered API key.

Every test here MOCKS subprocess. The gate's contract is "$0, no API key, deterministic, offline",
and a test that actually shelled out to `claude` would break all four — it would also be slow
(~15-60s per call, measured) and would spend a real subscription quota on CI.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from unittest import mock

from keystone.llm import LLMError, known_providers, make_llm
from keystone.llm_cli import ClaudeCliLLM, cli_status


def _envelope(result="ok", *, is_error=False, usage=None):
    return json.dumps({
        "type": "result", "subtype": "error" if is_error else "success",
        "is_error": is_error, "result": result,
        "usage": usage or {"input_tokens": 10, "output_tokens": 20},
        "total_cost_usd": 0.01,
    })


def _proc(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


class RegistrationTest(unittest.TestCase):
    def test_provider_is_registered(self):
        self.assertIn("claude_cli", known_providers())

    def test_factory_builds_it_without_an_api_key(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            llm = make_llm("claude_cli", "")
        self.assertIsInstance(llm, ClaudeCliLLM)

    def test_unknown_provider_message_mentions_it(self):
        with self.assertRaises(LLMError) as ctx:
            make_llm("nope", "x")
        self.assertIn("claude_cli", str(ctx.exception))


class ServerGuardTest(unittest.TestCase):
    """A subscription belongs to a person. Serving other people out of it is account sharing."""

    def setUp(self):
        self.llm = ClaudeCliLLM()

    def test_refuses_inside_a_server_process(self):
        for marker in ("UVICORN_HOST", "GUNICORN_CMD_ARGS", "KUBERNETES_SERVICE_HOST", "DYNO"):
            with self.subTest(marker):
                with mock.patch.dict("os.environ", {marker: "1"}, clear=False):
                    with mock.patch("keystone.llm_cli.cli_available", return_value=True):
                        with self.assertRaises(LLMError) as ctx:
                            self.llm.complete(label="t", system="", user="hi", max_tokens=10)
                self.assertIn("account sharing", str(ctx.exception).lower())

    def test_the_override_is_explicit_and_works(self):
        env = {"UVICORN_HOST": "1", "KEYSTONE_ALLOW_CLI_IN_SERVER": "1"}
        with mock.patch.dict("os.environ", env, clear=False):
            with mock.patch("keystone.llm_cli.cli_available", return_value=True):
                with mock.patch("subprocess.run", return_value=_proc(_envelope("fine"))):
                    self.assertEqual(
                        self.llm.complete(label="t", system="", user="hi", max_tokens=10), "fine")

    def test_no_server_markers_means_no_refusal(self):
        clean = {k: v for k, v in __import__("os").environ.items()
                 if not any(k.startswith(m) for m in
                            ("UVICORN_", "GUNICORN_", "SERVER_SOFTWARE", "KUBERNETES_SERVICE_HOST",
                             "DYNO", "FLY_ALLOC_ID", "RAILWAY_ENVIRONMENT", "WEBSITE_INSTANCE_ID"))}
        with mock.patch.dict("os.environ", clean, clear=True):
            with mock.patch("keystone.llm_cli.cli_available", return_value=True):
                with mock.patch("subprocess.run", return_value=_proc(_envelope("ok"))):
                    self.assertEqual(
                        self.llm.complete(label="t", system="", user="hi", max_tokens=10), "ok")


class CompleteTest(unittest.TestCase):
    def setUp(self):
        self.llm = ClaudeCliLLM()
        self.env = mock.patch.dict("os.environ", {"KEYSTONE_ALLOW_CLI_IN_SERVER": "1"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.avail = mock.patch("keystone.llm_cli.cli_available", return_value=True)
        self.avail.start()
        self.addCleanup(self.avail.stop)

    def test_returns_the_result_text(self):
        with mock.patch("subprocess.run", return_value=_proc(_envelope("hello"))):
            self.assertEqual(self.llm.complete(label="t", system="s", user="u", max_tokens=9),
                             "hello")

    def test_system_prompt_is_appended_not_replaced(self):
        """--system-prompt would also drop the CLI's own scaffolding."""
        with mock.patch("subprocess.run", return_value=_proc(_envelope())) as run:
            self.llm.complete(label="t", system="be terse", user="u", max_tokens=9)
        cmd = run.call_args[0][0]
        self.assertIn("--append-system-prompt", cmd)
        self.assertIn("be terse", cmd)
        self.assertNotIn("--system-prompt", cmd)

    def test_json_output_format_is_requested(self):
        with mock.patch("subprocess.run", return_value=_proc(_envelope())) as run:
            self.llm.complete(label="t", system="", user="u", max_tokens=9)
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)

    def test_runs_in_a_neutral_directory(self):
        """`claude -p` auto-discovers CLAUDE.md from its cwd. Running the council inside the repo
        prepends this project's own instructions to every persona prompt — measured at ~7,400 extra
        tokens and ~2x the notional cost — and makes the answer depend on where the dev was
        standing. The prompt must be exactly the persona + the model brief."""
        with mock.patch("subprocess.run", return_value=_proc(_envelope())) as run:
            self.llm.complete(label="t", system="", user="u", max_tokens=9)
        cwd = run.call_args.kwargs.get("cwd")
        self.assertIsNotNone(cwd, "the CLI must run in a pinned, neutral cwd")
        self.assertNotIn("Keystone", str(cwd), "must not inherit the repo's CLAUDE.md")

    def test_json_schema_is_not_used(self):
        """Measured on CLI 2.1.157: --json-schema returned PROSE, not a conforming object. The
        council's own _extract_json is the reliable path, so we must not depend on the flag."""
        with mock.patch("subprocess.run", return_value=_proc(_envelope())) as run:
            self.llm.complete(label="t", system="", user="u", max_tokens=9)
        self.assertNotIn("--json-schema", run.call_args[0][0])

    def test_empty_stdout_with_exit_zero_is_an_error(self):
        """Seen for real: a malformed argument makes the CLI exit 0 and print nothing. A silent
        success must not reach the council as an empty completion."""
        with mock.patch("subprocess.run", return_value=_proc("")):
            with self.assertRaises(LLMError) as ctx:
                self.llm.complete(label="t", system="", user="u", max_tokens=9)
        self.assertIn("returned nothing", str(ctx.exception))

    def test_non_zero_exit_is_an_error(self):
        with mock.patch("subprocess.run", return_value=_proc("", 1, "boom")):
            with self.assertRaises(LLMError):
                self.llm.complete(label="t", system="", user="u", max_tokens=9)

    def test_error_envelope_is_an_error(self):
        with mock.patch("subprocess.run", return_value=_proc(_envelope("nope", is_error=True))):
            with self.assertRaises(LLMError):
                self.llm.complete(label="t", system="", user="u", max_tokens=9)

    def test_non_json_stdout_is_an_error(self):
        with mock.patch("subprocess.run", return_value=_proc("not json at all")):
            with self.assertRaises(LLMError):
                self.llm.complete(label="t", system="", user="u", max_tokens=9)

    def test_timeout_explains_that_calls_are_slow(self):
        with mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)):
            with self.assertRaises(LLMError) as ctx:
                self.llm.complete(label="t", system="", user="u", max_tokens=9)
        self.assertIn("CLAUDE_CLI_TIMEOUT", str(ctx.exception))

    def test_missing_cli_is_a_clear_error(self):
        with mock.patch("keystone.llm_cli.cli_available", return_value=False):
            with self.assertRaises(LLMError) as ctx:
                self.llm.complete(label="t", system="", user="u", max_tokens=9)
        self.assertIn("not on PATH", str(ctx.exception))

    def test_usage_is_metered_as_visibility_not_spend(self):
        class Meter:
            def __init__(self): self.calls = []
            def record(self, provider, model, i, o): self.calls.append((provider, model, i, o))
        meter = Meter()
        llm = ClaudeCliLLM(meter=meter)
        with mock.patch("subprocess.run",
                        return_value=_proc(_envelope(usage={"input_tokens": 5, "output_tokens": 7}))):
            llm.complete(label="t", system="", user="u", max_tokens=9)
        self.assertEqual(meter.calls, [("claude_cli", "subscription", 5, 7)])


class StatusTest(unittest.TestCase):
    def test_status_never_raises_and_never_leaks_a_credential(self):
        with mock.patch("keystone.llm_cli.cli_available", return_value=True):
            with mock.patch("subprocess.run", side_effect=OSError("nope")):
                status = cli_status()
        self.assertFalse(status["available"])
        self.assertIn("reason", status)

    def test_status_reports_the_login_shape(self):
        payload = json.dumps({"loggedIn": True, "authMethod": "claude.ai",
                              "subscriptionType": "max", "email": "someone@example.test"})
        with mock.patch("keystone.llm_cli.cli_available", return_value=True):
            with mock.patch("subprocess.run", return_value=_proc(payload)):
                status = cli_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["auth_method"], "claude.ai")
        self.assertEqual(status["subscription"], "max")
        self.assertNotIn("email", status, "status must not carry the account identity")


if __name__ == "__main__":
    unittest.main()
