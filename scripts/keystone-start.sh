#!/usr/bin/env bash
# Opened by the Keystone Desktop shortcut on Windows (via WSL). The WSL analog of
# scripts/keystone-start.command, which macOS's Keystone.app opens the same way.
cd "$(dirname "$0")/.."

# A Windows double-click reaches this script as `wsl.exe -e bash -lic "..."`. That is a LOGIN shell
# (-l), which should read ~/.profile -> ~/.bashrc same as any terminal — except Ubuntu's stock
# ~/.bashrc starts with an INTERACTIVE-only guard:
#   case $- in *i*) ;; *) return;; esac
# `-lc` (no `i`) hits that guard and returns before ever reaching an nvm.sh source line further
# down the file, so node/npm/claude (installed via nvm, the common case) go invisible — the exact
# same "PATH the launcher can't see" failure the macOS script works around, just tripped by a
# different mechanism. Adding `-i` alongside `-l` when the shortcut is built (see
# make-windows-shortcut.sh) makes the guard pass on its own; sourcing nvm here too is belt-and-
# suspenders, unconditional, and costs nothing if nvm isn't installed at all.
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

LOG="$HOME/.local/state/keystone/launcher.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date) ==="
  echo "PATH=$PATH"
  for t in python3 node npm claude; do
    printf '%s: %s\n' "$t" "$(command -v $t || echo MISSING)"
  done
} >> "$LOG"

# The icon is "a double-clickable thing that opens in the browser" — keystone-local.sh's own
# `command -v open` check is a macOS-only no-op here, so the browser-open step lives at this layer
# instead. Polls in the background so it never blocks the server itself from starting; reaches back
# out to Windows via WSL interop (`cmd.exe`), which is reachable from any stock WSL install.
#
# GATED ON THE POLL ACTUALLY SUCCEEDING, not on the loop merely finishing — an earlier version
# called `cmd.exe /c start` unconditionally after the loop, so a launch that failed fast (missing
# node, a busy port) still popped a "can't be reached" browser tab up to two minutes later, well
# after the person had already read the failure message below and likely closed the window.
# Respects KEYSTONE_WEB_PORT the same way keystone-local.sh itself does, so an overridden port
# doesn't leave this polling (and eventually opening) the wrong address.
WEB_PORT="${KEYSTONE_WEB_PORT:-3000}"
(
  up=0
  for _ in $(seq 1 120); do
    curl -fsS -m 2 "http://127.0.0.1:$WEB_PORT/studio" >/dev/null 2>&1 && { up=1; break; }
    sleep 1
  done
  [ "$up" = 1 ] && cmd.exe /c start "http://localhost:$WEB_PORT/studio" >/dev/null 2>&1
  true   # never fail the background job over the open step
) &

if ! ./scripts/keystone-local.sh "$@"; then
  echo
  echo "  Keystone stopped. The checks above say why."
  echo "  Full log: $LOG"
  echo
  echo "  Most common fix — a tool the shortcut could not see:"
  echo "    npm install -g @anthropic-ai/claude-code && claude"
  echo
  echo "  Or run with no AI at all:  ./scripts/keystone-local.sh --offline"
  echo
  echo "  Press return to close."
  read -r _
fi
