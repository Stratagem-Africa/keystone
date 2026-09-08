#!/usr/bin/env bash
# Keystone, running on your own machine, on your own Claude subscription.
#
# WHY THIS SCRIPT EXISTS — and why Keystone is not simply a website you visit.
#
# The council and the ingestion layer can run on Claude Code's CLI (`claude -p`), which means they
# run on YOUR subscription: no API key, no metered spend, nothing to bill. That only works because
# the CLI is a program on your laptop.
#
# A hosted website cannot do this. A browser has no way to reach a CLI on the visitor's machine, so
# a server calling `claude -p` would be running on ONE account and answering EVERYBODY'S requests —
# account sharing, whoever the users are. `llm_cli._refuse_if_served()` fails closed the moment it
# smells a server process, and it is right to.
#
# The documented escape hatch, KEYSTONE_ALLOW_CLI_IN_SERVER=1, exists for exactly this case: a
# single-user API on your own machine. This script is the only place it is set, and it sets it ONLY
# after proving the bind address is loopback. If you point it at 0.0.0.0, it refuses — because at
# that moment the sentence "this is a single-user local API" stops being true.
#
#   ./scripts/keystone-local.sh            # your Claude subscription drives the council
#   ./scripts/keystone-local.sh --offline  # no AI at all: engine + the 56-blueprint library, $0
#
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

BIND="127.0.0.1"
API_PORT="${KEYSTONE_API_PORT:-8000}"
WEB_PORT="${KEYSTONE_WEB_PORT:-3000}"
MODE="cli"
[ "${1:-}" = "--offline" ] && MODE="offline"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo; bold "Keystone — local, single user"; echo

# ---------------------------------------------------------------- preflight
fail=0
command -v python3 >/dev/null || { bad "python3 not found"; fail=1; }
command -v node    >/dev/null || { bad "node not found — install Node 20+"; fail=1; }
command -v npm     >/dev/null || { bad "npm not found"; fail=1; }
[ $fail -eq 0 ] && ok "python3 $(python3 -V 2>&1 | cut -d' ' -f2) · node $(node -v)"

if [ "$MODE" = "cli" ]; then
  # Ask Keystone's own probe rather than guessing from `which claude`: it reports whether the CLI is
  # actually AUTHENTICATED, which is the thing that matters and the thing a PATH check misses.
  status=$(cd prototype && python3 -c '
import json
from keystone.llm_cli import cli_status
print(json.dumps(cli_status()))' 2>/dev/null || echo '{"available": false, "reason": "probe failed"}')
  avail=$(printf '%s' "$status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["available"])')
  if [ "$avail" != "True" ]; then
    reason=$(printf '%s' "$status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason") or "not installed")')
    bad "Claude Code CLI unavailable: $reason"
    echo
    echo "     Install it, sign in with your own account, then re-run:"
    echo "       npm install -g @anthropic-ai/claude-code   &&   claude   (sign in once)"
    echo
    echo "     Or run with no AI at all — the engine and all 56 reference designs still work:"
    echo "       ./scripts/keystone-local.sh --offline"
    exit 1
  fi
  sub=$(printf '%s' "$status" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("subscription") or d.get("auth_method") or "signed in")')
  ok "Claude Code CLI signed in ($sub) — the council runs on YOUR account"
else
  ok "offline mode — no AI, no network, \$0"
fi

# The override below is only honest while this is genuinely a single-user local API.
if [ "$BIND" != "127.0.0.1" ] && [ "$BIND" != "localhost" ]; then
  bad "refusing to bind $BIND with the CLI transport enabled — that would serve other people from your account"
  exit 1
fi
ok "binding loopback only ($BIND) — nobody else can reach this"

for p in "$API_PORT" "$WEB_PORT"; do
  if lsof -ti:"$p" >/dev/null 2>&1; then
    dim "  · port $p busy — stopping what's there"
    lsof -ti:"$p" | xargs kill -9 2>/dev/null || true
  fi
done

# ---------------------------------------------------------------- run
if [ "$MODE" = "cli" ]; then
  export COUNCIL_PROVIDER=claude_panel   # 7 personas as subagents in ONE call, not 7 sessions
  export INGEST_PROVIDER=claude_cli
  export KEYSTONE_ALLOW_CLI_IN_SERVER=1  # justified above: loopback-only, one user, your account
else
  export COUNCIL_PROVIDER=stub
  export INGEST_PROVIDER=stub
fi
export KB_PROVIDER=curated               # cited evidence in the report; uses no LLM

cleanup() { dim "shutting down…"; kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT INT TERM

( cd prototype && python3 -m uvicorn api.main:app --host "$BIND" --port "$API_PORT" --log-level warning ) &
( cd frontend && NEXT_PUBLIC_API_URL="http://$BIND:$API_PORT" npm run dev -- --port "$WEB_PORT" >/dev/null 2>&1 ) &

# Wait for the API rather than sleeping a guessed number of seconds.
for _ in $(seq 1 40); do
  curl -fsS -m 2 "http://$BIND:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done

echo
bold "  http://$BIND:$WEB_PORT/studio"
if [ "$MODE" = "cli" ]; then
  dim "  Council + ingestion: your Claude subscription. Numbers: always the engine, never the AI."
else
  dim "  No AI. The engine and the 56 reference designs — every number still computed, still cited."
fi
dim "  Ctrl-C to stop."
echo
wait
