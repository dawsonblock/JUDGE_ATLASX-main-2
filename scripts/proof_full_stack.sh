#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ARTIFACT_ROOT="$PROJECT_ROOT/artifacts/proof"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$ARTIFACT_ROOT/full-stack-$TIMESTAMP"
BACKEND_VENV="$PROJECT_ROOT/backend/.venv-proof"

mkdir -p "$RUN_DIR"

log_step() {
  echo "==> $*" | tee -a "$RUN_DIR/proof.log"
}

run_logged() {
  local name="$1"
  shift
  log_step "$name"
  ("$@") >"$RUN_DIR/$name.log" 2>&1
  cat "$RUN_DIR/$name.log" >>"$RUN_DIR/proof.log"
}

export JTA_APP_ENV="${JTA_APP_ENV:-development}"
export JTA_AUTO_SEED="${JTA_AUTO_SEED:-false}"
export JTA_ENABLE_SCHEDULER="${JTA_ENABLE_SCHEDULER:-false}"
export JTA_ADMIN_TOKEN="${JTA_ADMIN_TOKEN:-local-proof-admin-token-change-before-deploy}"
export JTA_ADMIN_REVIEW_TOKEN="${JTA_ADMIN_REVIEW_TOKEN:-local-proof-review-token-change-before-deploy}"
export JTA_JWT_SECRET_KEY="${JTA_JWT_SECRET_KEY:-local-proof-jwt-secret-change-before-deploy-000000000000}"
export JTA_DATABASE_URL="${JTA_DATABASE_URL:-sqlite:///$RUN_DIR/proof.sqlite3}"

log_step "Proof artifacts: $RUN_DIR"

cd "$PROJECT_ROOT/backend"
run_logged backend-uv-sync uv sync --frozen
source "$PROJECT_ROOT/backend/.venv/bin/activate"
run_logged backend-compile python -m compileall -q app
run_logged alembic-heads alembic heads
run_logged alembic-upgrade alembic upgrade head
run_logged backend-tests python -m pytest -q

cd "$PROJECT_ROOT/frontend"
run_logged frontend-install npm ci
run_logged frontend-typecheck npm run typecheck
run_logged frontend-build npm run build

cd "$PROJECT_ROOT"
run_logged truth-claims python3 scripts/check_truth_claims.py --root .
run_logged source-workflows python3 scripts/validate_workflows.py

log_step "Starting Docker stack"
docker compose up -d --build >"$RUN_DIR/docker-compose-up.log" 2>&1
cat "$RUN_DIR/docker-compose-up.log" >>"$RUN_DIR/proof.log"

cleanup() {
  docker compose logs >"$RUN_DIR/docker-compose-logs.log" 2>&1 || true
  docker compose down -v >"$RUN_DIR/docker-compose-down.log" 2>&1 || true
}
trap cleanup EXIT

run_logged docker-ps docker compose ps
run_logged smoke-backend curl -fsS http://localhost:8000/health
run_logged smoke-frontend curl -fsS http://localhost:3000/

log_step "Full-stack proof completed"
echo "$RUN_DIR" > "$ARTIFACT_ROOT/latest-full-stack-proof.txt"
