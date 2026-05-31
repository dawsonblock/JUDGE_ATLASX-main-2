#!/usr/bin/env bash
set -Eeuo pipefail

# Dedicated egress proxy proof for release gate evidence.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
BACKEND_PYTHON="${BACKEND_PYTHON:-$BACKEND_DIR/.venv/bin/python}"

if [ ! -x "$BACKEND_PYTHON" ]; then
    BACKEND_PYTHON="$(command -v python3)"
fi

if [ -z "$BACKEND_PYTHON" ] || [ ! -x "$BACKEND_PYTHON" ]; then
    echo "[proof_egress_proxy] FAIL: backend python executable not found"
    exit 1
fi

echo "[proof_egress_proxy] STAGE: environment"
echo "[proof_egress_proxy] Backend Python: $BACKEND_PYTHON"

echo "[proof_egress_proxy] STAGE: production startup egress policy tests"
(
    cd "$BACKEND_DIR"
    "$BACKEND_PYTHON" -m pytest app/tests/test_production_fetch_egress_policy.py -q
)

echo "[proof_egress_proxy] STAGE: runtime proxy wiring tests"
(
    cd "$BACKEND_DIR"
    "$BACKEND_PYTHON" -m pytest app/tests/test_source_fetcher_proxy.py -q
)

echo "[proof_egress_proxy] STAGE: ssrf context coverage tests"
(
    cd "$BACKEND_DIR"
    "$BACKEND_PYTHON" -m pytest app/tests/test_source_fetcher_ssrf.py -q
)

echo "[proof_egress_proxy] PASS: egress proxy proof checks completed"
