"""Tests for the run-scripts' stdlib .env loader (_env.py).

Locks the parsing rules that make `.env`-based activation safe: existing env wins (no clobber),
inline comments / quotes handled, blank+comment-only values stay UNSET (fail closed), and live
runs route to a gitignored *.local.md so the deterministic goldens are never overwritten.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _env


def _write(tmp: Path, text: str) -> str:
    p = tmp / ".env"
    p.write_text(text)
    return str(p)


class TestLoadEnv(unittest.TestCase):
    def test_basic_key_value(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "COUNCIL_PROVIDER=consensus\n")
            applied = _env.load_env(path)
            self.assertEqual(os.environ["COUNCIL_PROVIDER"], "consensus")
            self.assertEqual(applied, ["COUNCIL_PROVIDER"])

    def test_inline_comment_stripped_from_unquoted_value(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "OPENROUTER_API_KEY=sk-or-v1-abc123    # <-- paste your key\n")
            _env.load_env(path)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "sk-or-v1-abc123")

    def test_comment_only_value_stays_unset(self):
        # A blank `KEY=   # hint` must NOT set KEY to the hint text — it must remain unset (fails closed).
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "ANTHROPIC_API_KEY=        # <-- paste your Anthropic key\n")
            applied = _env.load_env(path)
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
            self.assertEqual(applied, [])

    def test_truly_empty_value_stays_unset(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "OPENAI_API_KEY=\n")
            _env.load_env(path)
            self.assertNotIn("OPENAI_API_KEY", os.environ)

    def test_hash_without_leading_space_is_kept(self):
        # dotenv semantics: a '#' NOT preceded by whitespace is part of the value, not a comment.
        # So a mistyped 'KEY=sk-...#typo' is kept whole (fails loudly at auth), never silently cut.
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "OPENROUTER_API_KEY=sk-or-v1-abc#oops\n")
            _env.load_env(path)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "sk-or-v1-abc#oops")

    def test_quoted_value_keeps_hash(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), 'TOKEN="a#b c"\n')
            _env.load_env(path)
            self.assertEqual(os.environ["TOKEN"], "a#b c")

    def test_existing_env_wins_no_override(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"COUNCIL_PROVIDER": "stub"}, clear=True):
            path = _write(Path(d), "COUNCIL_PROVIDER=consensus\n")
            applied = _env.load_env(path)
            self.assertEqual(os.environ["COUNCIL_PROVIDER"], "stub")  # shell export not clobbered
            self.assertNotIn("COUNCIL_PROVIDER", applied)

    def test_export_prefix_and_blank_and_comment_lines(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "\n# a comment\nexport KB_PROVIDER=curated\n\n")
            _env.load_env(path)
            self.assertEqual(os.environ["KB_PROVIDER"], "curated")

    def test_missing_file_is_noop(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_env.load_env(str(Path(tempfile.gettempdir()) / "definitely-not-here.env")), [])

    def test_value_with_colons_and_commas_preserved(self):
        # The CONSENSUS_VOTERS spec contains ':' and ',' — must survive intact for the voter parser.
        spec = "openrouter:meta-llama/llama-3.3-70b-instruct:free, openrouter:deepseek/deepseek-r1:free"
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), f"CONSENSUS_VOTERS={spec}\n")
            _env.load_env(path)
            self.assertEqual(os.environ["CONSENSUS_VOTERS"], spec)

    def test_applied_returns_names_not_secret_values(self):
        # Harm floor: the run banner must never echo a secret — load_env returns KEY NAMES only.
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            path = _write(Path(d), "OPENROUTER_API_KEY=sk-or-v1-supersecret\n")
            applied = _env.load_env(path)
            self.assertEqual(applied, ["OPENROUTER_API_KEY"])
            self.assertNotIn("sk-or-v1-supersecret", " ".join(applied))


class TestReportPath(unittest.TestCase):
    def test_stub_writes_committed_golden(self):
        with mock.patch.dict(os.environ, {"COUNCIL_PROVIDER": "stub"}, clear=True):
            path, provider = _env.report_path("/x/outputs/url_shortener_report.md")
            self.assertEqual(path, "/x/outputs/url_shortener_report.md")
            self.assertEqual(provider, "stub")

    def test_default_provider_is_stub(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            path, provider = _env.report_path("/x/outputs/r.md")
            self.assertEqual(provider, "stub")
            self.assertEqual(path, "/x/outputs/r.md")

    def test_live_writes_local_sibling(self):
        with mock.patch.dict(os.environ, {"COUNCIL_PROVIDER": "consensus"}, clear=True):
            path, provider = _env.report_path("/x/outputs/url_shortener_report.md")
            self.assertEqual(path, "/x/outputs/url_shortener_report.local.md")  # gitignored, never clobbers golden
            self.assertEqual(provider, "consensus")

    def test_claude_provider_also_local(self):
        with mock.patch.dict(os.environ, {"COUNCIL_PROVIDER": "claude"}, clear=True):
            path, _ = _env.report_path("/x/outputs/r.md")
            self.assertTrue(path.endswith(".local.md"))

    def test_whitespace_provider_falls_back_to_stub(self):
        # A whitespace-only COUNCIL_PROVIDER must NOT route to .local.md (it would mis-route a
        # crashing run) — it falls back to 'stub' / the committed golden path (fail closed).
        with mock.patch.dict(os.environ, {"COUNCIL_PROVIDER": "   "}, clear=True):
            self.assertEqual(_env.council_provider(), "stub")
            path, provider = _env.report_path("/x/outputs/r.md")
            self.assertEqual(provider, "stub")
            self.assertEqual(path, "/x/outputs/r.md")


if __name__ == "__main__":
    unittest.main()
