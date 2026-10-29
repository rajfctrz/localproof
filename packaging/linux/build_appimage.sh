#!/usr/bin/env bash
# Wrap the PyInstaller onedir build (dist/LocalProof) into an AppImage.
# Build on Ubuntu 22.04 for older-glibc compatibility. Needs appimagetool on PATH
# or APPIMAGETOOL pointing at it.
#
# The AppImage is the convenience channel: no sandbox, so it is "guard only".
# The window uses the host's GTK 3 + WebKit2GTK 4.1 stack as bundled by PyInstaller.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
[ -d dist/LocalProof ] || { echo "missing dist/LocalProof: run pyinstaller packaging/localproof.spec first" >&2; exit 1; }

PY="${PYTHON:-python3}"
VERSION="$("$PY" -c 'import localproof; print(localproof.__version__)')"
ARCH="${ARCH:-$(uname -m)}"
TOOL="${APPIMAGETOOL:-appimagetool}"
APPDIR="build/AppDir"
OUT="dist/LocalProof-${VERSION}-${ARCH}.AppImage"

rm -rf "$APPDIR" && mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a dist/LocalProof "$APPDIR/usr/lib/LocalProof"
install -m 0755 packaging/linux/AppRun "$APPDIR/AppRun"
install -m 0644 packaging/linux/LocalProof.desktop "$APPDIR/LocalProof.desktop"
install -m 0644 packaging/linux/LocalProof.desktop "$APPDIR/usr/share/applications/LocalProof.desktop"
install -m 0644 packaging/linux/localproof.svg "$APPDIR/localproof.svg"
install -m 0644 packaging/linux/localproof.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/localproof.svg"
ln -sf localproof.svg "$APPDIR/.DirIcon"

# --appimage-extract-and-run lets appimagetool (itself an AppImage) run without FUSE.
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "built $OUT"
sha256sum "$OUT"
