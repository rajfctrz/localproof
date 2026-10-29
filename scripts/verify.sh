#!/usr/bin/env bash
# Local verification loop: tests, no-outbound grep, browser mode, native window, self-audit.
# Usage: scripts/verify.sh [python]   (defaults to `python` on PATH)
set -uo pipefail

PY="${1:-python}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HOME_DIR="$(mktemp -d -t localproof-verify)"
export LOCALPROOF_HOME="$HOME_DIR"
FAILED=0

step() { printf '\n== %s\n' "$1"; }
fail() { echo "FAIL: $1"; FAILED=1; }

step "pytest"
"$PY" -m pytest -q || fail "pytest"

step "no-outbound grep (templates + static, excluding vendor/)"
if grep -rn 'https\?://' app/templates app/static --include='*.html' --include='*.css' --include='*.js' | grep -v vendor/; then
  fail "outbound URL found"
else
  echo "clean"
fi

step "browser mode (flask run)"
PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')"
"$PY" -m flask --app app run --port "$PORT" >"$HOME_DIR/flask.log" 2>&1 &
FLASK_PID=$!
for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 0.25; done
if curl -sf "http://127.0.0.1:$PORT/health" && curl -sf "http://127.0.0.1:$PORT/forecast/sample?horizon=12" | grep -q "Next 12 months"; then
  echo " ok"
else
  fail "browser mode"; cat "$HOME_DIR/flask.log"
fi
kill "$FLASK_PID" 2>/dev/null; wait "$FLASK_PID" 2>/dev/null

if [ -f localproof/launcher.py ]; then
  step "native window (launcher --window-smoke)"
  "$PY" -m localproof.launcher --window-smoke || fail "native window"
fi

if [ -f localproof/selfaudit.py ]; then
  step "self-audit"
  "$PY" -m localproof.launcher --self-audit
  code=$?
  echo "exit code: $code (0 = enforced, 2 = guard only, 3 = dev override, 1 = guard inactive/error)"
  [ "$code" -eq 1 ] && fail "self-audit reported the guard inactive"
fi

rm -rf "$HOME_DIR"
[ "$FAILED" -eq 0 ] && echo "ALL CHECKS PASSED" || { echo "SOME CHECKS FAILED"; exit 1; }
