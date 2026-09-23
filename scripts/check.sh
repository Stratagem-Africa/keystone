#!/usr/bin/env bash
# Keystone local CI gate. GitHub Actions is DORMANT (account billing), so THIS is the
# test/lint signal that gates every merge. Zero-dependency: the engine + council +
# ingestion + reconciliation tests need no pip install and no API key ($0).
#
# Covers BOTH halves of the repo. It used to be Python-only, which meant no eslint, no tsc and no
# `next build` ever ran here — a lint error reached main in #140, and a CSS regression that only
# manifested in `next dev` went unnoticed for weeks. See scripts/check-frontend.sh.
#
#   scripts/check.sh        # run from anywhere in the repo
#
# Exit 0 = safe to merge (after review). Non-zero = do not merge.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/prototype" || { echo "error: cannot find prototype/"; exit 2; }

# Hermetic gate: the suite asserts the STUB/offline defaults, so a desktop shell that
# exports live-provider config (e.g. COUNCIL_PROVIDER=consensus after LLM activation)
# must not leak into the run — it once turned this gate red with 16 env-driven failures.
# The gate's contract is "$0, no API key, deterministic"; sanitize to keep it true.
unset COUNCIL_PROVIDER COUNCIL_MODEL CONSENSUS_PRIMARY CONSENSUS_VOTERS \
      INGEST_PROVIDER KB_PROVIDER STORE_PROVIDER OLLAMA_BASE_URL \
      ANTHROPIC_API_KEY OPENROUTER_API_KEY OPENAI_API_KEY \
      SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY

status=0

# SAY WHICH INTERPRETER THIS IS, AND WHETHER IT MATCHES WHAT WE DECLARE.
#
# pyproject.toml says `requires-python = ">=3.10"`. The review machine runs macOS's stock python3,
# which is 3.9.6. That gap produced two false signals in one week and cost real time both times:
#   * a contributor's PR was green on her 3.10 box and RED here, on `assertNoLogs` (3.10+), and the
#     red was first misattributed to an unrelated environment variable (#200);
#   * `setup.sh` accepted any python3 at all, so nothing ever surfaced the mismatch.
# A gate whose interpreter differs from the declared minimum is testing something other than what
# the project claims to support, and neither side can tell.
#
# WARN, do not fail. The suite genuinely passes on 3.9.6, so failing would redden the only machine
# that reviews anything — and a gate that is red for reasons unrelated to the change teaches you to
# ignore red. Name the gap loudly instead, every run, until someone closes it.
py_ver="$(python3 -V 2>&1 | cut -d' ' -f2)"
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "==> python3 $py_ver  (meets pyproject's >=3.10)"
else
  printf '\033[33m==> python3 %s — BELOW pyproject.toml\047s declared >=3.10\033[0m\n' "$py_ver"
  echo "    The suite passes here, but this gate is not testing the version we claim to support:"
  echo "    3.10-only syntax and stdlib (e.g. unittest's assertNoLogs) pass review on a"
  echo "    contributor's machine and fail on this one. Install python 3.10+, or lower the"
  echo "    declaration — but they should not disagree."
fi

echo "==> Test suite  (python3 -m unittest discover -s tests)"
python3 -m unittest discover -s tests 2>&1 | tail -n 4
[ "${PIPESTATUS[0]}" -eq 0 ] || status=1

# Cross-process determinism gate (prior art: madsim/RisingWave DST, docs/13). The engine must be a
# pure function of its inputs: identical output across two processes with DIFFERENT hash seeds.
# Catches hash-order/iteration nondeterminism an in-process "run twice" test cannot. The engine
# produces the digest; this only compares it (prime directive intact).
echo; echo "==> Determinism gate  (engine output stable across PYTHONHASHSEED)"
d0=$(PYTHONHASHSEED=0 python3 -m keystone.benchmarks.determinism 2>/dev/null)
d1=$(PYTHONHASHSEED=1 python3 -m keystone.benchmarks.determinism 2>/dev/null)
if printf '%s' "$d0" | grep -Eq '^[0-9a-f]{64}$' && [ "$d0" = "$d1" ]; then
  echo "   ok: corpus digest ${d0:0:16}… identical across hash seeds"
else
  echo "   ❌ engine output not hash-seed stable (or the digest run errored):"
  echo "      seed0=${d0:-<empty/error>}"; echo "      seed1=${d1:-<empty/error>}"; status=1
fi

# Grounding-corpus gate (docs/12 §5). The curated benchmark datapoints must pass the curation QA
# (tier band-floors, corroboration counts, mandatory context note, no same-context contradictions)
# before they can ship. Independent human citation review is still required (not automatable).
echo; echo "==> Corpus gate  (curated grounding datapoints pass the curation QA)"
python3 -m keystone.benchmarks.validate_corpus 2>&1 | tail -n 1
[ "${PIPESTATUS[0]}" -eq 0 ] || status=1

# ruff / mypy — run whether installed on PATH OR only importable as a module (`python -m ruff`).
# A module-only install used to report "skipped" and the gate went GREEN without ever linting —
# that's how 7 ruff errors + a mypy error sat unnoticed. Only a genuine "not installed at all" now
# skips, which keeps the $0 zero-dep clean-checkout gate green by design.
if command -v ruff >/dev/null 2>&1; then ruff_cmd="ruff"
elif python3 -c "import ruff" >/dev/null 2>&1; then ruff_cmd="python3 -m ruff"
else ruff_cmd=""; fi
if [ -n "$ruff_cmd" ]; then
  echo; echo "==> ruff check .  ($ruff_cmd)"
  $ruff_cmd check . || status=1
else
  echo; echo "==> ruff: skipped (not installed — pip install 'keystone[dev,api,db]')"
fi

if command -v mypy >/dev/null 2>&1; then mypy_cmd="mypy"
elif python3 -c "import mypy" >/dev/null 2>&1; then mypy_cmd="python3 -m mypy"
else mypy_cmd=""; fi
if [ -n "$mypy_cmd" ]; then
  echo; echo "==> mypy (prototype/api)  ($mypy_cmd)"
  (cd "$root" && $mypy_cmd) || status=1
else
  echo; echo "==> mypy: skipped (not installed — pip install 'keystone[dev,api,db]')"
fi

# Frontend half of the gate. Kept in its own script so it can be run alone during UI work, and so a
# missing node_modules skips cleanly instead of failing a Python-only clone.
echo
"$root/scripts/check-frontend.sh" || status=1

echo
if [ "$status" -eq 0 ]; then
  echo "✅ CHECK PASSED — safe to merge (after review)."
else
  echo "❌ CHECK FAILED — do not merge."
fi
exit "$status"
