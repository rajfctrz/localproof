#!/usr/bin/env bash
# Usage: scripts/ci/expect.sh <expected-exit-code> [--contains TEXT] -- command args...
# Runs the command, prints its output, and fails unless the exit code (and text) match.
set -uo pipefail
expect="$1"; shift
contains=""
if [ "${1:-}" = "--contains" ]; then contains="$2"; shift 2; fi
[ "${1:-}" = "--" ] && shift
out="$("$@" 2>&1)"; code=$?
printf '%s\n' "$out"
echo "exit code: $code (expected: $expect)"
[ "$code" = "$expect" ] || { echo "unexpected exit code" >&2; exit 1; }
if [ -n "$contains" ] && ! grep -qF -- "$contains" <<<"$out"; then
  echo "output does not contain: $contains" >&2; exit 1
fi
