#!/bin/zsh -l
# Opened by Keystone.app. `-l` = login shell, so PATH is the same one you get in a terminal.
cd "$(dirname "$0")/.."
LOG="$HOME/Library/Logs/Keystone.log"
mkdir -p "$(dirname "$LOG")"
{
  echo "=== $(date) ==="
  echo "PATH=$PATH"
  for t in python3 node npm claude; do
    printf '%s: %s\n' "$t" "$(command -v $t || echo MISSING)"
  done
} >> "$LOG"

if ! ./scripts/keystone-local.sh; then
  echo
  echo "  Keystone stopped. The checks above say why."
  echo "  Full log: $LOG"
  echo
  echo "  Most common fix — a tool Finder could not see:"
  echo "    npm install -g @anthropic-ai/claude-code && claude"
  echo
  echo "  Or run with no AI at all:  ./scripts/keystone-local.sh --offline"
  echo
  echo "  Press return to close."
  read -r _
fi
