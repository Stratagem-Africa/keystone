#!/usr/bin/env bash
# Keystone — one command to set up everything. Run this once after cloning.
#
#     ./setup.sh
#
# It checks what you have, tells you plainly what is missing and how to get it, builds the desktop
# app (macOS), puts a shortcut on your Desktop, and installs a git hook so every future `git pull`
# rebuilds the app for you. After this, you never run it again.
set -uo pipefail
cd "$(dirname "$0")"
REPO="$PWD"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo; bold "Keystone setup"; echo

# ---------------------------------------------------------------- 1. what's here
missing=0
if command -v python3 >/dev/null; then ok "python3 $(python3 -V 2>&1 | cut -d' ' -f2)"
else bad "python3 — install Xcode command line tools: xcode-select --install"; missing=1; fi

if command -v node >/dev/null; then ok "node $(node -v)"
else bad "node — install Node 20+ from https://nodejs.org (or: brew install node)"; missing=1; fi

if command -v npm >/dev/null; then ok "npm $(npm -v)"
else bad "npm — comes with node"; missing=1; fi

if [ $missing -eq 1 ]; then
  echo; bad "Install the missing tools above, then run ./setup.sh again."; echo; exit 1
fi

# ---------------------------------------------------------------- 2. the Claude CLI
# Checked LAST and never fatal: Keystone runs completely without it. The engine and all 56 reference
# designs are pure maths and need no AI at all — the CLI only adds the council's reasoning.
if command -v claude >/dev/null; then
  auth=$(cd prototype 2>/dev/null && python3 -c '
import json
try:
    from keystone.llm_cli import cli_status
    print(json.dumps(cli_status()))
except Exception:
    print("{\"available\": false}")' 2>/dev/null || echo '{"available": false}')
  if printf '%s' "$auth" | grep -q '"available": true'; then
    ok "Claude Code CLI signed in — the council will run on YOUR subscription"
  else
    warn "Claude Code CLI installed but not signed in. Run: claude   (once, to sign in)"
    dim "     Until then Keystone runs with no AI — which still gives you every number."
  fi
else
  warn "Claude Code CLI not installed (optional)"
  dim "     npm install -g @anthropic-ai/claude-code   then:   claude"
  dim "     Without it Keystone runs offline: the engine and all 56 designs still work."
fi

# ---------------------------------------------------------------- 3. frontend deps
if [ -d frontend/node_modules ]; then
  ok "frontend dependencies present"
else
  dim "  installing frontend dependencies (a minute or two)…"
  ( cd frontend && npm install --silent ) && ok "frontend dependencies installed" \
    || { bad "npm install failed — run 'cd frontend && npm install' to see why"; exit 1; }
fi

# ---------------------------------------------------------------- 4. the desktop app
if [ "$(uname)" = "Darwin" ]; then
  mkdir -p "$HOME/Applications"
  if ./scripts/make-mac-app.sh "$HOME/Applications" >/dev/null 2>&1; then
    ok "built Keystone.app in ~/Applications"
    # A Finder ALIAS on the Desktop, not the bundle itself: Desktops are often iCloud-synced, and
    # iCloud can evict an app bundle to the cloud or strip its executable bit. An alias is a tiny
    # file that syncs harmlessly and always points at the real app.
    if osascript >/dev/null 2>&1 <<AS
tell application "Finder"
  set appFile to POSIX file "$HOME/Applications/Keystone.app" as alias
  set d to path to desktop folder
  try
    delete (every item of d whose name is "Keystone")
  end try
  make new alias file at d to appFile
  set name of result to "Keystone"
end tell
AS
    then ok "shortcut named 'Keystone' on your Desktop"
    else warn "could not create the Desktop shortcut — open ~/Applications/Keystone.app instead"
    fi
  else
    warn "could not build the .app — use ./scripts/keystone-local.sh instead"
  fi
else
  dim "  not macOS — start it with ./scripts/keystone-local.sh"
fi

# ---------------------------------------------------------------- 5. keep it fresh
# `core.hooksPath` points git at a VERSIONED hooks directory. .git/hooks is not tracked, so without
# this every person would have to install hooks by hand and would silently not have them.
git config core.hooksPath scripts/git-hooks 2>/dev/null \
  && ok "git hook installed — future 'git pull' rebuilds the app automatically" \
  || warn "could not set core.hooksPath (not a git checkout?)"

echo
bold "  Done."
if [ "$(uname)" = "Darwin" ]; then
  echo "  Double-click \"Keystone\" on your Desktop."
else
  echo "  Start it with: ./scripts/keystone-local.sh"
fi
dim "  It opens http://127.0.0.1:3000/studio. Describe a system; read the verdict."
dim "  Nothing is shared, nothing is hosted, nothing is billed — it all runs on your machine."
echo
