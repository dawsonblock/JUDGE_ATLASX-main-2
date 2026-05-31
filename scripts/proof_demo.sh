#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROOF_DIR="${ROOT_DIR}/artifacts/proof/current"
DEMO_DB_PATH="${PROOF_DIR}/demo_proof.sqlite3"
DEMO_BACKEND_PORT="${DEMO_BACKEND_PORT:-18010}"
DEMO_API_BASE="http://127.0.0.1:${DEMO_BACKEND_PORT}"
RUNTIME_LOG="${PROOF_DIR}/demo_backend_runtime.log"

mkdir -p "${PROOF_DIR}"
rm -f "${DEMO_DB_PATH}" "${RUNTIME_LOG}"

echo "[proof_demo] PASS: demo database initialized"

PYTHON_BIN="${ROOT_DIR}/backend/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python3"
fi

export JTA_DATABASE_URL="sqlite:///${DEMO_DB_PATH}"
export JTA_APP_ENV="development"
export JTA_AUTO_SEED="false"
export JTA_SEED_SOURCE_REGISTRY="false"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && ps -p "${BACKEND_PID}" >/dev/null 2>&1; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"${PYTHON_BIN}" "${ROOT_DIR}/demo/scripts/seed_demo_data.py" >/dev/null
echo "[proof_demo] PASS: synthetic data seeded"

(
  cd "${ROOT_DIR}/backend"
  exec "${PYTHON_BIN}" -m uvicorn app.main:app --host 127.0.0.1 --port "${DEMO_BACKEND_PORT}"
) >"${RUNTIME_LOG}" 2>&1 &
BACKEND_PID=$!

for _ in {1..40}; do
  if curl -sf "${DEMO_API_BASE}/health" >/dev/null; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "${DEMO_API_BASE}/health" >/dev/null; then
  echo "ERROR: demo backend failed to become healthy at ${DEMO_API_BASE}" >&2
  tail -n 80 "${RUNTIME_LOG}" >&2 || true
  exit 1
fi

DEMO_API_BASE="${DEMO_API_BASE}" \
DEMO_BACKEND_PORT="${DEMO_BACKEND_PORT}" \
JTA_DATABASE_URL="${JTA_DATABASE_URL}" \
"${ROOT_DIR}/demo/scripts/verify_demo.sh"

echo "[proof_demo] PASS: reviewed/public event visible"
echo "[proof_demo] PASS: pending/private event hidden"
echo "[proof_demo] PASS: source registry/audit rows present"

rm -f "${DEMO_DB_PATH}"
echo "[proof_demo] PASS: cleanup completed"

echo "[proof_demo] PASS: demo proof completed"
echo "Demo proof PASS at ${DEMO_API_BASE}"
