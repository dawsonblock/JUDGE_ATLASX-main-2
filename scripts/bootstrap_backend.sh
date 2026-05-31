#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
VENV_DIR="${JTA_BACKEND_VENV:-$BACKEND_DIR/.venv}"
PYTHON_BIN="${PYTHON:-python3}"

echo "==> Bootstrapping backend in $BACKEND_DIR"
cd "$BACKEND_DIR"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e ".[test]"

python -m compileall -q app
python - <<'PY'
from app.main import create_app

app = create_app()
print(f"FastAPI import/boot check OK: {app.title}")
PY

echo "Backend bootstrap complete. Activate with: source $VENV_DIR/bin/activate"
