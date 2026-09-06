#!/usr/bin/env bash
# Frontend half of the merge gate.
#
# Why this exists: scripts/check.sh was Python-only, so nothing in the gate ever ran eslint, tsc or
# `next build`. Two real consequences, both observed:
#   * a lint error reached main in #140, because the reviewer had no reason to run eslint by hand;
#   * `.canvas-glass` shipped in `next build` but was silently DROPPED from the dev CSS chunk by
#     Turbopack, so `--cv-paper` resolved to empty and the studio overlay rendered transparent over
#     the page — undetected from #196 until it happened to surface during an unrelated refactor.
#
# The second one is the interesting failure: a bare custom class in globals.css is not a reliable
# place for anything load-bearing, and neither typecheck nor build catches it. So this script adds a
# TOKEN GUARD: every `--cv-*` custom property the components read must be declared on `:root`, where
# it survives, rather than only inside a class that can vanish.
#
# Skips cleanly (like ruff/mypy in check.sh) when node_modules is absent, so the Python gate still
# runs on a fresh clone with no npm install.
set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fe="$root/frontend"
status=0

if [ ! -d "$fe/node_modules" ]; then
  echo "==> frontend: skipped (no node_modules — run 'cd frontend && npm install')"
  exit 0
fi

cd "$fe" || { echo "error: cannot find frontend/"; exit 2; }

# Build into a directory nothing else touches, and typecheck with tsconfig.gate.json, which reads
# the SOURCE plus this build's generated types — never .next/.
#
# Why: .next/types/ is shared with a running `next dev`, AND on this machine a second process is
# copying files as they are written — the duplicates land as "routes.d 3.ts" with 0600 permissions
# while the real file is 0644, one per minute, matching each gate run. tsc then reports duplicate
# identifiers and the gate fails on code that is fine: intermittently at first (1 run in 3), then
# every run as they accumulated. A gate that is red for reasons unrelated to the change is worse
# than no gate, because it teaches you to ignore red.
export NEXT_DIST_DIR=".next-gate"

# Sweep any duplicates a sync/AV agent left behind, so a stale copy cannot fail a later run.
find .next .next-gate -name "* [0-9].*" -delete 2>/dev/null || true

echo "==> frontend: design-token guard  (every --cv-* the components read is declared on :root)"
node --input-type=module -e '
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const css = readFileSync("src/app/globals.css", "utf8");
// Tokens declared on a bare :root block (not inside a class, media query or [data-theme]).
const declared = new Set();
for (const block of css.matchAll(/:root\s*\{([^}]*)\}/g)) {
  for (const m of block[1].matchAll(/(--cv-[a-z0-9-]+)\s*:/g)) declared.add(m[1]);
}

const walk = (dir, out = []) => {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|css)$/.test(e)) out.push(p);
  }
  return out;
};

const used = new Map();
for (const file of walk("src")) {
  if (file.endsWith("globals.css")) continue;
  const src = readFileSync(file, "utf8");
  for (const m of src.matchAll(/var\((--cv-[a-z0-9-]+)/g)) {
    if (!used.has(m[1])) used.set(m[1], file);
  }
}

const missing = [...used].filter(([t]) => !declared.has(t));
if (missing.length) {
  console.error("   ❌ tokens read by components but NOT declared on :root in globals.css:");
  for (const [t, f] of missing) console.error(`      ${t}   (first used in ${f})`);
  console.error("   A token defined only inside a bare custom class can be dropped by Turbopack in");
  console.error("   dev while surviving `next build` — declare it on :root instead.");
  process.exit(1);
}
console.log(`   ok: ${used.size} token(s) used, all declared on :root`);
' || status=1

# --max-warnings=0: the tree is clean today, so warnings are cheap to keep at zero and expensive to
# let accumulate — an unused import or a stale dep array is exactly the rot that hides a real defect.
echo; echo "==> frontend: eslint (warnings are errors)"
npx --no-install eslint src --max-warnings=0 2>&1 | tail -n 5
[ "${PIPESTATUS[0]}" -eq 0 ] || status=1

echo; echo "==> frontend: next build"
npm run build 2>&1 | grep -E "✓|✗|error|Error|Failed" | tail -n 6
[ "${PIPESTATUS[0]}" -eq 0 ] || status=1

echo; echo "==> frontend: tsc --noEmit (gate tsconfig)"
npx --no-install tsc -p tsconfig.gate.json --noEmit 2>&1 | tail -n 5
[ "${PIPESTATUS[0]}" -eq 0 ] || status=1

exit "$status"
