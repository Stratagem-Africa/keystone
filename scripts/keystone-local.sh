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

# CORS. The API defaults to allowing http://localhost:3000 only, and this launcher serves the studio
# on http://127.0.0.1:3000 — which a browser treats as a DIFFERENT ORIGIN. The page loaded, the
# button worked, and every request was blocked before it left the browser. Both spellings are listed
# so whichever one you open in works. Still loopback only: nothing outside this machine is allowed.
export ALLOWED_ORIGINS="http://$BIND:$WEB_PORT,http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT"

cleanup() { dim "shutting down…"; kill $(jobs -p) 2>/dev/null || true; }
trap cleanup EXIT INT TERM

( cd prototype && python3 -m uvicorn api.main:app --host "$BIND" --port "$API_PORT" --log-level warning ) &
# PRODUCTION BUILD, NOT `next dev`. This ran the dev server and the studio silently FAILED TO
# HYDRATE: the page rendered, you could type into the box, and the Generate button stayed disabled
# forever — because the text reached the DOM while React state never updated. The dev server's
# hot-reload WebSocket could not connect (ERR_INVALID_HTTP_RESPONSE, retrying endlessly) and took
# hydration down with it. A dev server is for editing code, not for running an app: it compiles on
# first request, needs a live socket to the toolchain, and fails in ways a built app cannot.
#
# NEXT_PUBLIC_* are inlined AT BUILD TIME, so the API address must be set for the build, not just
# the server — that is why it appears on both lines below.
( cd frontend
  # `set -o pipefail` is on, and `find ... -newer .next/BUILD_ID` ERRORS when that file does not
  # exist (first run). The failing find made the whole pipeline fail, `set -e` killed this subshell
  # before it printed anything, and the launcher happily announced a URL that served nothing.
  # Hence: test for the marker FIRST, and only then ask what is newer than it.
  # NEXT_PUBLIC_* are inlined into the JS AT BUILD TIME, so a build made with a different API
  # address — or none at all — is stale even when every source file is older than it. That exact
  # case shipped: a cached build had no API URL in the bundle, the studio loaded and the Generate
  # button worked, and the request went nowhere. Source mtimes cannot see it, so the address used
  # is recorded next to the build and compared.
  WANT_API="http://$BIND:$API_PORT"
  needs_build=1
  if [ -f .next/BUILD_ID ] && [ "$(cat .next/.keystone-api-url 2>/dev/null)" = "$WANT_API" ]; then
    if [ -z "$(find src public package.json next.config.ts -type f -newer .next/BUILD_ID 2>/dev/null | head -1)" ]; then
      needs_build=0
    fi
  fi
  if [ "$needs_build" = "1" ]; then
    printf '\033[2m  building the app (first run, or the code changed) — about a minute…\033[0m\n'
    if ! NEXT_PUBLIC_API_URL="http://$BIND:$API_PORT" npm run build >/tmp/keystone-build.log 2>&1; then
      printf '\033[31m  build failed. Last lines of /tmp/keystone-build.log:\033[0m\n'
      tail -15 /tmp/keystone-build.log
      exit 1
    fi
    printf '%s' "$WANT_API" > .next/.keystone-api-url
  fi
  NEXT_PUBLIC_API_URL="http://$BIND:$API_PORT" npx --no-install next start --port "$WEB_PORT" >/dev/null 2>&1
) &

# Wait for BOTH, not just the API. This waited only on /health, so when the frontend subshell died
# the launcher still printed the URL and everything looked fine until you clicked something.
for _ in $(seq 1 40); do
  curl -fsS -m 2 "http://$BIND:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 1
done
web_up=0
for _ in $(seq 1 180); do
  if curl -fsS -m 2 "http://$BIND:$WEB_PORT/studio" >/dev/null 2>&1; then web_up=1; break; fi
  kill -0 %2 2>/dev/null || break          # the frontend job died — stop waiting on it
  sleep 1
done
if [ "$web_up" != "1" ]; then
  echo
  bad "the app did not come up on port $WEB_PORT"
  echo "     Build log: /tmp/keystone-build.log"
  echo "     Try by hand:  cd frontend && npm run build"
  echo
  exit 1
fi

# A desktop launch should land you IN the app, not hand you a URL to copy. Only when a real TTY is
# attached, so a CI or headless run never tries to open a browser.
URL="http://$BIND:$WEB_PORT/studio"
if [ -t 1 ] && command -v open >/dev/null 2>&1; then
  ( sleep 1; open "$URL" ) >/dev/null 2>&1 &
fi

echo
bold "  $URL"
if [ "$MODE" = "cli" ]; then
  dim "  Council + ingestion: your Claude subscription. Numbers: always the engine, never the AI."
else
  dim "  No AI. The engine and the 56 reference designs — every number still computed, still cited."
fi
dim "  Ctrl-C to stop."
echo
wait
