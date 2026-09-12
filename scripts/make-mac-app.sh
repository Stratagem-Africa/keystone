#!/usr/bin/env bash
# Build Keystone.app — a real macOS application you double-click from the Dock.
#
# WHAT THIS IS, AND WHAT IT IS NOT.
#
# It is a thin native wrapper around the SAME Next.js frontend the web app serves. Identical code,
# identical pixels — the only difference is where it runs. It is not a rewrite, not a port, and not
# a second UI to keep in sync, because there is no second UI.
#
# It exists for one reason: the council runs on `claude -p`, which is a program on YOUR laptop.
# A hosted site cannot reach it (a server calling it would be one account answering everybody's
# requests), so Keystone has to run locally to use your own subscription. A Dock icon is simply a
# nicer way to start a local process than remembering a shell command.
#
#   ./scripts/make-mac-app.sh          # builds ./Keystone.app
#   ./scripts/make-mac-app.sh ~/Apps   # or wherever you want it
#
# The bundle is a LAUNCHER, not a copy: it points at this checkout, so `git pull` updates the app.
# Nothing is vendored, nothing goes stale, and the .app is gitignored — each person builds their own.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"
DEST="${1:-$REPO}"
APP="$DEST/Keystone.app"

if [ "$(uname)" != "Darwin" ]; then
  echo "This builds a macOS .app bundle. On Linux/Windows just run ./scripts/keystone-local.sh" >&2
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Keystone</string>
  <key>CFBundleDisplayName</key><string>Keystone</string>
  <key>CFBundleIdentifier</key><string>africa.stratagem.keystone</string>
  <key>CFBundleVersion</key><string>0.1</string>
  <key>CFBundleShortVersionString</key><string>0.1</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Keystone</string>
  <key>CFBundleIconFile</key><string>Keystone</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <!-- No Dock icon bouncing for a background server; the browser is the window. -->
  <key>LSUIElement</key><false/>
</dict>
</plist>
PLIST

# The executable. Terminal.app is used deliberately rather than a silent background launch: if the
# Claude CLI is not signed in, or a port is busy, the person needs to SEE why. A desktop app that
# fails invisibly is worse than a shell command that explains itself.
cat > "$APP/Contents/MacOS/Keystone" <<LAUNCHER
#!/bin/bash
REPO="$REPO"
if [ ! -x "\$REPO/scripts/keystone-local.sh" ]; then
  osascript -e 'display alert "Keystone" message "The checkout moved. Re-run scripts/make-mac-app.sh from the repo."'
  exit 1
fi
open -a Terminal "\$REPO/scripts/keystone-local.sh"
LAUNCHER
chmod +x "$APP/Contents/MacOS/Keystone"

# Icon: generated from text so nothing binary is committed. Skipped silently if the tools are absent.
if command -v sips >/dev/null && command -v iconutil >/dev/null; then
  TMP="$(mktemp -d)"; ICONSET="$TMP/Keystone.iconset"; mkdir -p "$ICONSET"
  python3 - "$TMP/icon.png" <<'PY' 2>/dev/null || true
import struct, zlib, sys
# A 1024x1024 PNG drawn by hand — deep slate ground, a keystone wedge in amber. No dependencies,
# no committed binary, and it regenerates identically on every machine.
W = 1024
def px(x, y):
    cx = x - W/2; ty = y / W
    half = 190 + 300*ty                      # a wedge: narrow at the top, wide at the base
    if 250 <= y <= 800 and abs(cx) <= half:
        return (214, 158, 74)
    return (16, 22, 32)
rows = b"".join(b"\x00" + b"".join(struct.pack("3B", *px(x, y)) for x in range(W)) for y in range(W))
def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", W, W, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))
open(sys.argv[1], "wb").write(png)
PY
  if [ -f "$TMP/icon.png" ]; then
    for s in 16 32 64 128 256 512; do
      sips -z $s $s "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1 || true
      sips -z $((s*2)) $((s*2)) "$TMP/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/Keystone.icns" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP"
fi

touch "$APP"                      # nudge Finder to pick up the new bundle
echo
echo "  Built $APP"
echo
echo "  Double-click it, or drag it to your Dock / Applications."
echo "  It starts Keystone on this checkout and opens http://127.0.0.1:3000/studio."
echo "  Because it points at the repo rather than copying it, 'git pull' updates the app."
echo
echo "  First launch: macOS may say it is from an unidentified developer — right-click > Open once."
echo "  (It is a shell script you just built from source, not a downloaded binary.)"
echo
