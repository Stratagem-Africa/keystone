#!/usr/bin/env bash
# Manual merge-gate helper. GitHub Actions is DORMANT (billing), so contributor PRs are
# gated locally by the reviewer (Bifola / his Claude): fetch the PR, see its diff, run
# the local check gate. Then do an adversarial review and `gh pr merge --squash` on green
# (never merge on a failing gate; never merge your own PR; prod stays Bifola-gated).
#
#   scripts/review-pr.sh <PR-number>
#
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 2
pr="${1:-}"
[ -n "$pr" ] || { echo "usage: scripts/review-pr.sh <PR-number>"; exit 2; }

echo "==> gh pr checkout $pr"
gh pr checkout "$pr" || { echo "error: could not check out PR #$pr"; exit 2; }

echo; echo "==> Changed files vs origin/main:"
git --no-pager diff --stat origin/main...HEAD

echo; echo "==> Running local gate…"
exec "$root/scripts/check.sh"
