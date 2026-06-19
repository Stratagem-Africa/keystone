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
