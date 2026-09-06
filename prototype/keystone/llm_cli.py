"""`claude_cli` — drive the locally installed Claude Code CLI instead of a metered API key.

Why this exists: Keystone is an internal Stratagem tool, and every member of staff already has a
Claude subscription sitting in their terminal. Paying per token through `ANTHROPIC_API_KEY` to do
work their subscription already covers is waste, and it is the thing that has kept the council and
the ingestion layer stub-gated.

**The boundary, stated once and enforced below.** Anthropic permits a person to drive their OWN
subscription non-interactively — that is what `claude setup-token` exists for, and the Consumer
Terms carve out automated access "where we otherwise explicitly permit it". What is NOT permitted is
sharing an account: a hosted Keystone that answers other people's requests out of one person's
subscription is exactly the "make your Account available to anyone else" case, and no amount of
internal framing changes that. So this transport is for a HUMAN AT THEIR OWN KEYBOARD running
Keystone locally. `_refuse_if_served()` fails closed when it detects a server process, and the
served product keeps the API-key path (or ADR-010's free providers) unchanged.

Measured on Claude Code 2.1.157, subscription auth (`authMethod: claude.ai`, `max`):

* `claude -p --output-format json` works and returns a JSON envelope whose `result` is the text.
* **`--json-schema` did NOT enforce structured output** — asked for an object, it returned prose.
  So this transport does not use it. That costs nothing, because `claude_council._extract_json`
  already pulls JSON out of free text; the council's existing contract is the right one to keep.
* It is SLOW compared with the API: ~13 s for a trivial prompt, ~59 s for a real one, because each
  invocation boots a full Claude Code session. Budget minutes for a council run, not seconds.
* The envelope reports `total_cost_usd`. On a subscription that is NOTIONAL — what the same tokens
  would have cost via the API — so it is recorded for visibility, never as spend.
* **It runs in a neutral directory, deliberately.** `claude -p` auto-discovers `CLAUDE.md` from its
  working directory, so running the council from inside the Keystone repo silently prepends this
  project's own instructions to every persona prompt. Measured: ~7,400 extra context tokens and
  roughly double the notional cost, and — worse — the council's answer would then depend on which
  directory the developer happened to be standing in. Keystone's whole contract is reproducibility,
  so the prompt is exactly what `_model_brief` and the persona say, and nothing ambient.

Prime directive is untouched: this is a transport. It returns text for the council to reason with,
and `simulate()` remains the only source of a number.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from .cost_meter import CostMeter
from .llm import LLMError

__all__ = ["ClaudeCliLLM", "cli_available", "cli_status"]

# A council stage can legitimately take a while; a stuck child must not hang the run for ever.
_DEFAULT_TIMEOUT = int(os.getenv("CLAUDE_CLI_TIMEOUT", "300"))

# Environment set by the usual Python servers. If any is present we are almost certainly inside a
# request handler, not at someone's keyboard.
_SERVER_MARKERS = ("UVICORN_", "GUNICORN_", "SERVER_SOFTWARE", "WEBSITE_INSTANCE_ID",
                   "KUBERNETES_SERVICE_HOST", "DYNO", "FLY_ALLOC_ID", "RAILWAY_ENVIRONMENT")


def cli_available() -> bool:
    """Is the Claude Code CLI on PATH?"""
    return shutil.which("claude") is not None


def cli_status() -> dict:
    """What `claude auth status` reports — used to tell a human WHY the transport is unusable
    rather than failing with a bare error. Never raises; never returns a credential."""
    if not cli_available():
        return {"available": False, "reason": "the `claude` CLI is not on PATH"}
    try:
        p = subprocess.run(["claude", "auth", "status"],
                           capture_output=True, text=True, timeout=30)
        data = json.loads(p.stdout or "{}")
    except Exception as e:                                   # noqa: BLE001 - status must never raise
        return {"available": False, "reason": f"could not read auth status: {type(e).__name__}"}
    # Deliberately narrow: report the shape of the login, never the identity beyond the org label.
    return {
        "available": bool(data.get("loggedIn")),
        "auth_method": data.get("authMethod"),
        "subscription": data.get("subscriptionType"),
        "reason": "" if data.get("loggedIn") else "not logged in — run `claude` once to sign in",
    }


def _refuse_if_served() -> None:
    """Fail closed when this looks like a server process.

    A subscription is a person's, not a service's. This is a guard, not a security boundary — it
    stops the obvious accident (someone sets COUNCIL_PROVIDER=claude_cli in a deployed API and
    quietly serves every user out of one account), and it is deliberately loud about why.
    """
    if os.getenv("KEYSTONE_ALLOW_CLI_IN_SERVER") == "1":
        return          # explicit, documented override for a single-user local API
    hit = next((k for k in _SERVER_MARKERS if any(e.startswith(k) for e in os.environ)), None)
    if hit:
        raise LLMError(
            "the `claude_cli` transport refuses to run inside a server process "
            f"(saw {hit}*). A Claude subscription may be driven by the person it belongs to, not "
            "used to answer other people's requests — that is account sharing regardless of who "
            "the users are. Use an API key or ADR-010's free providers for anything served. If "
            "this really is a single-user local API, set KEYSTONE_ALLOW_CLI_IN_SERVER=1.")


class ClaudeCliLLM:
    """An `LLM` transport that shells out to the user's own Claude Code CLI.

    Same protocol as `AnthropicLLM` / `OpenAICompatibleLLM`, so the council, the consensus layer and
    the ingestor all work unchanged — only the transport differs.
    """

    def __init__(self, model: str | None = None, *, meter: CostMeter | None = None,
                 timeout: int = _DEFAULT_TIMEOUT) -> None:
        self.model = model or ""
        self._meter = meter
        self._timeout = timeout

    def complete(self, *, label: str, system: str, user: str, max_tokens: int,
                 agents: str | None = None) -> str:
        """`agents` is an optional Claude Code `--agents` JSON object. When given, the CLI runs those
        personas as SUBAGENTS inside this one session — the mechanism `panel_council` uses to hold a
        whole deliberation in a single call instead of one call per persona. It is an extra keyword,
        so the plain `LLM` protocol is unaffected and every other caller is untouched."""
        _refuse_if_served()
        if not cli_available():
            raise LLMError("`claude` is not on PATH — install Claude Code, or use a provider "
                           "with an API key.")

        cmd = ["claude", "-p", "--output-format", "json"]
        if agents:
            cmd += ["--agents", agents]
        if self.model:
            cmd += ["--model", self.model]
        if system.strip():
            # The council's persona/system prompt is APPENDED rather than replacing Claude Code's
            # own, because --system-prompt would also drop the tool-use scaffolding the CLI needs.
            cmd += ["--append-system-prompt", system]
        cmd.append(user)

        try:
            # Neutral cwd: see the module docstring. Without this the council inherits whatever
            # CLAUDE.md is above the caller's directory, and stops being reproducible.
            with tempfile.TemporaryDirectory(prefix="keystone-cli-") as neutral:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=self._timeout, cwd=neutral)
        except subprocess.TimeoutExpired as e:
            raise LLMError(
                f"{label}: `claude -p` timed out after {self._timeout}s. Each call boots a whole "
                f"Claude Code session (~15-60s is normal), so raise CLAUDE_CLI_TIMEOUT for a long "
                f"council stage.") from e
        except OSError as e:
            raise LLMError(f"{label}: could not run `claude`: {e}") from e

        if proc.returncode != 0:
            raise LLMError(f"{label}: `claude -p` exited {proc.returncode}: "
                           f"{(proc.stderr or proc.stdout)[:300]}")

        raw = (proc.stdout or "").strip()
        if not raw:
            # Seen for real: an invalid flag value makes the CLI exit 0 with empty stdout. Treat a
            # silent success as a failure rather than handing the council an empty string.
            raise LLMError(f"{label}: `claude -p` returned nothing (exit 0 with empty stdout) — "
                           f"usually a malformed argument.")
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMError(f"{label}: `claude -p` did not return JSON: {raw[:200]}") from e

        if envelope.get("is_error"):
            raise LLMError(f"{label}: {envelope.get('subtype') or 'error'}: "
                           f"{str(envelope.get('result'))[:300]}")

        result = envelope.get("result")
        if not isinstance(result, str) or not result.strip():
            raise LLMError(f"{label}: no text in the CLI result envelope")

        if self._meter is not None:
            usage = envelope.get("usage") or {}
            # Recorded for VISIBILITY, not as spend: a subscription call bills no API money, and
            # `total_cost_usd` here is what the same tokens would have cost through the API.
            self._meter.record("claude_cli", self.model or "subscription",
                               usage.get("input_tokens"), usage.get("output_tokens"))
        return result
