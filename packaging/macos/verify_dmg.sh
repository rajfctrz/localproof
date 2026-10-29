#!/usr/bin/env bash
# Mount a DMG read-only and run the bundled app's checks from the mounted image.
# Usage: packaging/macos/verify_dmg.sh dist/LocalProof-<version>-macos-<arch>.dmg [--window]
set -uo pipefail

DMG="$1"
MOUNT="$(mktemp -d -t localproof-mnt)"
hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT" "$DMG" >/dev/null || exit 1
trap 'hdiutil detach "$MOUNT" -quiet || hdiutil detach "$MOUNT" -force -quiet' EXIT

BIN="$MOUNT/LocalProof.app/Contents/MacOS/LocalProof"
export LOCALPROOF_HOME="$(mktemp -d -t localproof-dmg-home)"
"$BIN" --version || exit 1
"$BIN" --serve-smoke || exit 1
"$BIN" --self-audit >"$LOCALPROOF_HOME/audit.txt"
code=$?
grep -E "SHA-256|Enforcement tier|Result" "$LOCALPROOF_HOME/audit.txt"
# macOS has no OS-level enforcement: the honest answer is guard only (2).
[ "$code" -eq 2 ] || { echo "expected self-audit exit 2 (guard only), got $code" >&2; exit 1; }
if [ "${2:-}" = "--window" ]; then
  "$BIN" --window-smoke || exit 1
fi
echo "dmg ok"
