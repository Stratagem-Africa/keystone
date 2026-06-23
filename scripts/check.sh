#!/usr/bin/env bash
# Keystone local CI gate. GitHub Actions is DORMANT (account billing), so THIS is the
# test/lint signal that gates every merge. Zero-dependency: the engine + council +
# ingestion + reconciliation tests need no pip install and no API key ($0).
#
#   scripts/check.sh        # run from anywhere in the repo
#
# Exit 0 = safe to merge (after review). Non-zero = do not merge.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/prototype" || { echo "error: cannot find prototype/"; exit 2; }

status=0

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

if command -v ruff >/dev/null 2>&1; then
  echo; echo "==> ruff check ."
  ruff check . || status=1
else
  echo; echo "==> ruff: skipped (not installed — pip install 'keystone[dev]')"
fi

echo
if [ "$status" -eq 0 ]; then
  echo "✅ CHECK PASSED — safe to merge (after review)."
else
  echo "❌ CHECK FAILED — do not merge."
fi
exit "$status"
