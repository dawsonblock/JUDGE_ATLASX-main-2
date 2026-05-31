#!/bin/bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"
ARTIFACTS_DIR="$(cd "$(dirname "$0")/.." && pwd)/artifacts/proof/backend"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${ARTIFACTS_DIR}/${TIMESTAMP}.log"
VERIFY_DB="${BACKEND_DIR}/verify_migration_test.db"
VENV_DIR="${BACKEND_DIR}/.venv"

mkdir -p "${ARTIFACTS_DIR}"

# Route all output to stdout AND the log file
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=== Backend Verification — ${TIMESTAMP} ==="

# ---------------------------------------------------------------------------
# 1. Locate a Python 3 interpreter
# ---------------------------------------------------------------------------
if [ -x "${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]; then
    BASE_PY="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    BASE_PY="python3"
else
    echo "ERROR: python3 not found on PATH"; exit 1
fi
echo "Base Python: ${BASE_PY} ($("${BASE_PY}" --version))"

# ---------------------------------------------------------------------------
# 2. Create or reuse backend/.venv and install dependencies
# ---------------------------------------------------------------------------
echo ""
echo "1. Creating / reusing virtual environment at ${VENV_DIR} ..."
if [ ! -x "${VENV_DIR}/bin/python" ]; then
    "${BASE_PY}" -m venv "${VENV_DIR}"
    echo "   Created new venv."
else
    echo "   Reusing existing venv."
fi

PY="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

cd "${BACKEND_DIR}"

echo ""
echo "2. Installing backend dependencies ..."
"${PY}" -m pip install --upgrade pip --quiet
"${PY}" -m pip install -e ".[test]" --quiet

echo ""
echo "Python version: $("${PY}" --version)"
echo "Installed packages:"
"${PY}" -m pip freeze

# ---------------------------------------------------------------------------
# 3. Syntax check
# ---------------------------------------------------------------------------
echo ""
echo "3. Syntax check ..."
"${PY}" -m compileall -q app

# ---------------------------------------------------------------------------
# 4. Alembic migration against fresh SQLite DB (no skip — fail hard)
# ---------------------------------------------------------------------------
echo ""
echo "4. Alembic migration against fresh SQLite DB ..."
rm -f "${VERIFY_DB}"
JTA_DATABASE_URL="sqlite:///${VERIFY_DB}" "${PY}" -m alembic upgrade head
echo "   alembic upgrade head: OK"
rm -f "${VERIFY_DB}"

# ---------------------------------------------------------------------------
# 5. Test suite
# ---------------------------------------------------------------------------
echo ""
echo "5. Running pytest ..."
"${PY}" -m pytest -q

echo ""
echo "=== Backend verification PASSED ==="
echo "Log: ${LOG_FILE}"
