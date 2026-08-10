#!/usr/bin/env bash
# Thin wrapper for the tiered check runner — picks the project venv automatically.
#   scripts/check.sh [guard|changed|full|all] [base-ref]
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -x ./.venv/bin/python ]; then
  PY=./.venv/bin/python
else
  PY="$(command -v python3 || command -v python)"
fi
exec "$PY" scripts/check.py "$@"
