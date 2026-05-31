#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_VENV_PYTHON="$REPO_ROOT/backend/.venv/bin/python"

if [[ -x "$BACKEND_VENV_PYTHON" ]]; then
  PYTHON_BIN="$BACKEND_VENV_PYTHON"
else
  PYTHON_BIN="python3"
fi

echo "[proof_all_current] delegating to canonical release gate"
exec "$PYTHON_BIN" "$REPO_ROOT/scripts/release_gate.py"
