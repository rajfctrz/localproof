#!/bin/sh
# Flatpak entry point: run LocalProof from source with the runtime's Python.
export PYTHONPATH="/app/share/localproof${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m localproof.launcher "$@"
