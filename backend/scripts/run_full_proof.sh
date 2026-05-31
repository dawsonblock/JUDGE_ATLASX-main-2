#!/usr/bin/env bash
# Run the full backend proof suite.
#
# Usage:
#   cd backend && bash scripts/run_full_proof.sh
#
# Exit 0 if all checks pass; non-zero on the first failure.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

# Default to development mode so no missing-secret validation fires.
export JTA_APP_ENV="${JTA_APP_ENV:-development}"
export PYTHONDONTWRITEBYTECODE=1

echo "=== run_full_proof: backend dir: $BACKEND_DIR ===" >&2

run_check() {
  local label="$1"
  shift
  echo "--- $label ---" >&2
  python3 "$@"
  echo "--- $label: OK ---" >&2
}

run_check "proof_backend_import"        scripts/proof_backend_import.py
run_check "proof_ingest_review_map"     scripts/proof_ingest_review_map.py
run_check "check_no_direct_ingestion_network_clients" \
          scripts/check_no_direct_ingestion_network_clients.py
run_check "check_repo_boundaries"       scripts/check_repo_boundaries.py

echo "=== run_full_proof: all checks passed ===" >&2
