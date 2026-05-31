#!/usr/bin/env bash
# run_frontend_gate.sh — Structured frontend gate with JSON artifact output.
#
# Usage: bash scripts/run_frontend_gate.sh [--json-out PATH]
#
# Runs every frontend gate check in order and writes a structured
# frontend_gate.json to artifacts/proof/current/.
# Exits 0 only when ALL gates pass.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARTIFACT_DIR="${REPO_ROOT}/artifacts/proof/current"
JSON_OUT="${ARTIFACT_DIR}/frontend_gate.json"

# ── Parse arguments ───────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --json-out=*) JSON_OUT="${arg#*=}" ;;
    --json-out)   shift; JSON_OUT="$1" ;;
  esac
done

mkdir -p "${ARTIFACT_DIR}"

GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OVERALL_PASS=true

declare -A GATE_RESULTS
GATE_NAMES=()

run_gate() {
  local name="$1"
  shift
  GATE_NAMES+=("$name")
  if "$@" >/dev/null 2>&1; then
    GATE_RESULTS["$name"]="PASS"
  else
    GATE_RESULTS["$name"]="FAIL"
    OVERALL_PASS=false
  fi
}

# ── Node version gate ─────────────────────────────────────────────
run_gate "frontend_node_gate" \
  python3 "${SCRIPT_DIR}/check_frontend_node_gate.py"

# ── npm install ───────────────────────────────────────────────────
run_gate "frontend_install" \
  bash -c "cd '${REPO_ROOT}/frontend' && npm ci --prefer-offline"

# ── Lint ──────────────────────────────────────────────────────────
run_gate "frontend_lint" \
  bash -c "cd '${REPO_ROOT}/frontend' && npm run lint"

# ── Type-check ────────────────────────────────────────────────────
run_gate "frontend_typecheck" \
  bash -c "cd '${REPO_ROOT}/frontend' && npm run typecheck"

# ── Contract tests ────────────────────────────────────────────────
run_gate "frontend_contracts" \
  bash -c "cd '${REPO_ROOT}/frontend' && npm run test:contracts 2>/dev/null || npm run test 2>/dev/null"

# ── Build ─────────────────────────────────────────────────────────
run_gate "frontend_build" \
  bash -c "cd '${REPO_ROOT}/frontend' && npm run build"

# ── Write JSON artifact ───────────────────────────────────────────
{
  echo "{"
  echo "  \"frontend_gate_pass\": ${OVERALL_PASS},"
  echo "  \"generated_at\": \"${GENERATED_AT}\","
  echo "  \"checks\": ["
  local_sep=""
  for name in "${GATE_NAMES[@]}"; do
    echo "    ${local_sep}{\"name\": \"${name}\", \"status\": \"${GATE_RESULTS[$name]}\"}"
    local_sep=","
  done
  echo "  ]"
  echo "}"
} > "${JSON_OUT}"

echo "Frontend gate artifact: ${JSON_OUT}"

# ── Summary ───────────────────────────────────────────────────────
if [ "${OVERALL_PASS}" = "true" ]; then
  echo "FRONTEND GATE: PASS"
  exit 0
else
  echo "FRONTEND GATE: BLOCKED"
  for name in "${GATE_NAMES[@]}"; do
    echo "  - ${name}: ${GATE_RESULTS[$name]}"
  done
  exit 1
fi
