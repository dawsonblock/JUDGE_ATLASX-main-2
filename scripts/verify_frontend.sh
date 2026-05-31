#!/bin/bash
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")/../frontend" && pwd)"
ARTIFACTS_DIR="$(cd "$(dirname "$0")/.." && pwd)/artifacts/proof/frontend"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${ARTIFACTS_DIR}/${TIMESTAMP}.log"

mkdir -p "${ARTIFACTS_DIR}"

# Route all output to stdout AND the log file
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=== Frontend Verification — ${TIMESTAMP} ==="

cd "${FRONTEND_DIR}"

if [[ -s "${HOME}/.nvm/nvm.sh" ]]; then
    # Honor the frontend Node contract before running the fail-closed check.
    # If nvm is not installed, the normal PATH-based check below still applies.
    # shellcheck source=/dev/null
    source "${HOME}/.nvm/nvm.sh"
    nvm use >/dev/null
fi

# ---------------------------------------------------------------------------
# 1. Require Node 22.x
# ---------------------------------------------------------------------------
echo ""
echo "1. Checking Node version ..."
NODE_VERSION="$(node --version 2>/dev/null || echo "not-found")"
if [[ "${NODE_VERSION}" == "not-found" ]]; then
    echo "ERROR: Node.js not found. Please install Node 22.x."
    exit 1
fi
# Extract major version (handles v22.x.x)
NODE_MAJOR="${NODE_VERSION%%.*}"
NODE_MAJOR="${NODE_MAJOR#v}"
if [[ "${NODE_MAJOR}" -ne 22 ]]; then
    echo "ERROR: Node 22.x is required. Found: ${NODE_VERSION}"
    echo "Install Node 22 (e.g. via nvm: nvm install 22 && nvm use 22) and re-run."
    exit 1
fi
echo "   Node: ${NODE_VERSION} — OK (Node 22.x supported)"
echo "   npm:  $(npm --version)"

# ---------------------------------------------------------------------------
# 2–5. Install, lint, typecheck, build
# ---------------------------------------------------------------------------
echo ""
echo "2. Clean install (npm ci) ..."
npm ci

echo ""
echo "3. Lint ..."
npm run lint

echo ""
echo "4. Typecheck ..."
npm run typecheck

echo ""
echo "5. Build ..."
npm run build

echo ""
echo "=== Frontend verification PASSED ==="
echo "Log: ${LOG_FILE}"
