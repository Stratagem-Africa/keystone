"""Tiny stdlib .env loader for the run scripts (no python-dotenv dependency — CLAUDE.md stdlib-first).

The run scripts call `load_env()` at the start of `main()` so a local, gitignored `.env`
(COUNCIL_PROVIDER, CONSENSUS_*, API keys, KB_PROVIDER) activates the real council/grounding —
WITHOUT this, `os.getenv(...)` in the engine sees nothing and silently falls back to the stub.

Deliberately NOT auto-loaded on import and NOT used by the library or the tests: it is opt-in,
called only from a script's `main()`, so importing a run script (as the golden tests do) never
mutates the environment and the deterministic fixtures stay byte-stable.

Rules (match python-dotenv's safe defaults):
  * existing environment variables WIN (a shell `export` overrides .env) — never clobbered;
  * `KEY=value`, optional `export ` prefix, blank lines and `# comments` ignored;
  * surrounding quotes are stripped (a quoted value keeps any '#' literally);
  * an unquoted inline `# comment` is stripped; a value that is empty/whole-comment is skipped,
    so a blank `ANTHROPIC_API_KEY=` stays UNSET (clean "not configured", fails closed).
Secrets are never logged here (harm floor): only KEY NAMES are returned, never values.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Repo root = parent of prototype/ (this file lives in prototype/).
_DEFAULT_ENV = Path(__file__).resolve().parent.parent / ".env"

_INLINE_COMMENT = re.compile(r"\s+#.*$")


def _parse_value(raw: str) -> str:
    """Return the cleaned value for one `KEY=...` right-hand side ('' means skip/unset)."""
    val = raw.strip()
    if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
        return val[1:-1]                       # quoted literal — keep '#' and spaces verbatim
    if val.startswith("#"):
        return ""                              # whole value is a comment → unset
    return _INLINE_COMMENT.sub("", val).strip()  # drop a trailing ` # comment`


def load_env(path: str | os.PathLike | None = None) -> list[str]:
    """Load KEY=VALUE pairs from `.env` into os.environ (existing vars win). No-op if the file
    is absent. Returns the list of KEY NAMES applied (for an honest, secret-free run banner)."""
    p = Path(path) if path is not None else _DEFAULT_ENV
    if not p.exists():
        return []
    applied: list[str] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, raw = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = _parse_value(raw)
        if not val:
            continue                            # blank/comment-only → leave UNSET (fails closed)
        if key not in os.environ:               # existing environment wins (no override)
            os.environ[key] = val
            applied.append(key)
    return applied


def council_provider() -> str:
    """The configured council provider ('stub' | 'claude' | 'consensus'), normalised."""
    return (os.getenv("COUNCIL_PROVIDER") or "stub").strip().lower()


def report_path(committed_path: str) -> tuple[str, str]:
    """Pick where a run writes its report, returning (path, provider).

    STUB (deterministic) -> the committed golden `*.md` (unchanged, byte-stable for the gate).
    LIVE council -> a gitignored `*.local.md` sibling, so a non-deterministic LLM report NEVER
    clobbers the committed fixture (which the golden test byte-compares)."""
    provider = council_provider()
    if provider == "stub":
        return committed_path, provider
    root, ext = os.path.splitext(committed_path)
    return f"{root}.local{ext}", provider
