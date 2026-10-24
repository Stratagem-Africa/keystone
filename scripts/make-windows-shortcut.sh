#!/usr/bin/env bash
# Build a Keystone Desktop shortcut on Windows, from inside WSL.
#
# WHAT THIS IS, AND WHAT IT IS NOT.
#
# It is a thin launcher, the same idea as macOS's Keystone.app (scripts/make-mac-app.sh): a
# double-clickable icon that starts the SAME Next.js frontend the web build serves and opens it in
# your default browser. It is not a rewrite, not a native app window, and not a second UI to keep
# in sync — there is no second UI. Windows support is WSL-only: this refuses to run outside WSL, the
# same platform split scripts/keystone-local.sh has always had (native PowerShell/cmd is not a
# supported path).
#
# It exists for the same reason the macOS app does: the council can run on `claude -p`, a program on
# YOUR machine, so Keystone has to run locally to use your own subscription. A Desktop icon is just a
# nicer way to start it than remembering a shell command.
#
#   ./scripts/make-windows-shortcut.sh          # run from inside WSL — builds the shortcut
#
# The shortcut is a LAUNCHER, not a copy: it points at this checkout (via `wsl.exe`), so `git pull`
# updates it. The generated icon is gitignored; each person builds their own.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$PWD"

if [ -z "${WSL_DISTRO_NAME:-}" ]; then
  echo "This builds a Windows Desktop shortcut and must be run from inside WSL." >&2
  echo "Not on Windows/WSL? Just run ./scripts/keystone-local.sh directly." >&2
  exit 1
fi

if ! command -v powershell.exe >/dev/null; then
  echo "powershell.exe is not reachable from this WSL session (interop may be disabled)." >&2
  echo "Fix WSL interop, or just run ./scripts/keystone-local.sh directly instead." >&2
  exit 1
fi

chmod +x "$REPO/scripts/keystone-start.sh"

# Icon: generated from text, the same trick scripts/make-mac-app.sh uses, so nothing binary is
# committed and it regenerates identically on every machine. Windows has supported a PNG frame
# inside a .ico for any size since Vista, so the same procedural wedge-drawer just runs once per
# size instead of needing separate resize tooling (there's no `sips` equivalent on stock Windows).
# Skipped silently on any failure — a missing/wrong icon is cosmetic, never a reason to fail the
# shortcut build.
ICONDIR="$REPO/scripts/.windows-icon"
mkdir -p "$ICONDIR"
python3 - "$ICONDIR/Keystone.ico" <<'PY' 2>/dev/null || true
import struct, zlib, sys


def wedge_png(w):
    # Same proportional design as make-mac-app.sh's icon (deep slate ground, amber keystone
    # wedge), scaled to any size w instead of fixed at 512 — the fractions below are that
    # script's own pixel thresholds (125, 400, 95, 150) divided by its canvas size (512).
    BG = bytes((16, 22, 32))
    FG = bytes((214, 158, 74))
    y0, y1 = int(0.244 * w), int(0.781 * w)
    rows = bytearray()
    for y in range(w):
        rows.append(0)  # PNG per-scanline filter byte: none
        if y0 <= y <= y1:
            half = int(w * (0.1855 + 0.293 * (y / w)))
            left = max(0, w // 2 - half)
            right = min(w, w // 2 + half)
            rows += BG * left + FG * (right - left) + BG * (w - right)
        else:
            rows += BG * w

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, w, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
            + chunk(b"IEND", b""))


# .ico container: a 6-byte ICONDIR header, one 16-byte ICONDIRENTRY per frame, then the raw
# frame bytes in order — each frame here is a complete, valid PNG file, which is a format
# Windows has accepted inside a .ico since Vista (avoids needing any BMP/DIB encoding at all).
sizes = (16, 32, 48, 256)
pngs = [wedge_png(s) for s in sizes]
header = struct.pack("<HHH", 0, 1, len(sizes))
offset = 6 + 16 * len(sizes)
entries, data = b"", b""
for s, png in zip(sizes, pngs):
    wh = s if s < 256 else 0  # 0 means "256" in the ICO format
    entries += struct.pack("<BBBBHHII", wh, wh, 0, 0, 1, 32, len(png), offset)
    data += png
    offset += len(png)
open(sys.argv[1], "wb").write(header + entries + data)
PY

# UNC form: any WSL-internal path (not under /mnt) is reachable from Windows at
# \\wsl.localhost\<distro>\<posix path with \ instead of />. wslpath only translates the OTHER
# direction (a /mnt/c/... path to C:\...), so there's no built-in tool for this; building it by
# hand is the standard approach.
WIN_REPO="${REPO//\//\\}"
ICON_UNC="\\\\wsl.localhost\\${WSL_DISTRO_NAME}${WIN_REPO}\\scripts\\.windows-icon\\Keystone.ico"
[ -f "$ICONDIR/Keystone.ico" ] || ICON_UNC=""   # icon step failed — leave the shortcut's default icon alone

# Create the shortcut via the stock WScript.Shell COM object — ships with every Windows install,
# so this needs no new tooling. The PowerShell text below is single-quoted in bash (no bash
# interpolation at all) specifically so its own `$` variables and backtick-escapes reach
# powershell.exe untouched; the three real values are passed in as positional script args instead.
# `-Command "text" arg1 arg2` does NOT bind arg1/arg2 to a bare param() block — PowerShell just
# concatenates them onto the command text as more code, which is why the script is wrapped in an
# explicitly invoked `& { ... }` block: that's the form whose trailing CLI arguments actually get
# bound to the block's own parameters (verified directly against this machine's powershell.exe).
if powershell.exe -NoProfile -NonInteractive -Command '& {
  param($Distro, $RepoPath, $IconUnc)
  $ws = New-Object -ComObject WScript.Shell
  $shortcut = Join-Path $ws.SpecialFolders("Desktop") "Keystone.lnk"
  $s = $ws.CreateShortcut($shortcut)
  $s.TargetPath = "$env:WINDIR\System32\wsl.exe"
  $s.Arguments  = "-d $Distro -e bash -lic `"$RepoPath/scripts/keystone-start.sh`""
  $s.WorkingDirectory = $env:USERPROFILE
  $s.Description = "Keystone — intent to validated design"
  if ($IconUnc) { $s.IconLocation = "$IconUnc,0" }
  $s.Save()
  Write-Output $shortcut
}' -Distro "$WSL_DISTRO_NAME" -RepoPath "$REPO" -IconUnc "$ICON_UNC" >/dev/null; then
  echo
  echo "  Built a Keystone shortcut on your Windows Desktop."
  echo
  echo "  Double-click it. It starts Keystone on this checkout and opens"
  echo "  http://localhost:3000/studio in your browser."
  echo "  Because it points at the repo rather than copying it, 'git pull' updates it."
  echo
  echo "  Windows support is WSL-only — this shortcut always runs inside $WSL_DISTRO_NAME."
  echo
else
  echo "Could not create the Desktop shortcut — use ./scripts/keystone-local.sh instead." >&2
  exit 1
fi
