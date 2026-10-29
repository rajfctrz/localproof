#!/usr/bin/env bash
# Package dist/LocalProof.app into dist/LocalProof-<version>-macos-<arch>.dmg with create-dmg.
# Set DMG_SKIP_FINDER=1 on headless CI runners (skips the Finder window layout step).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
APP="dist/LocalProof.app"
[ -d "$APP" ] || { echo "missing $APP: run pyinstaller packaging/localproof.spec first" >&2; exit 1; }

PY="${PYTHON:-python3}"
VERSION="$("$PY" -c 'import localproof; print(localproof.__version__)')"
ARCH="$(uname -m)"
OUT="dist/LocalProof-${VERSION}-macos-${ARCH}.dmg"
STAGE="$(mktemp -d -t localproof-dmg)"
trap 'rm -rf "$STAGE"' EXIT

ditto "$APP" "$STAGE/LocalProof.app"
rm -f "$OUT"

EXTRA=()
[ "${DMG_SKIP_FINDER:-0}" = "1" ] && EXTRA+=(--skip-jenkins)

create-dmg \
  --volname "LocalProof ${VERSION}" \
  --window-size 540 360 \
  --icon-size 96 \
  --icon "LocalProof.app" 140 170 \
  --app-drop-link 400 170 \
  --hdiutil-quiet \
  "${EXTRA[@]+"${EXTRA[@]}"}" \
  "$OUT" "$STAGE"

echo "built $OUT"
shasum -a 256 "$OUT"
