#!/usr/bin/env bash
# proof_repo.sh — Non-aborting per-step proof with a fixed, canonical output path.
#
# Outputs to artifacts/proof/latest/  (overwritten on each run).
# Each step writes exactly one named log file.  If a required dependency is
# absent the step is SKIPPED and the log records why; the script continues.
#
# Canonical output files
# ──────────────────────
#   backend_compile.log   frontend_typecheck.log
#   backend_tests.log     frontend_build.log
#   alembic_upgrade.log   docker_compose.log
#                         healthcheck.log
#                         proof_summary.md
#
# Usage
# ─────
#   ./scripts/proof_repo.sh
#   JTA_DATABASE_URL="postgresql://..." ./scripts/proof_repo.sh
#
# NOTE: set -e is intentionally absent so per-step failures do not suppress
#       later steps.  set -u and pipefail remain for safety.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="$PROJECT_ROOT/artifacts/proof/latest"

mkdir -p "$OUT"

# ──────────────────────────────────────────────────────────────────────────────
# Python resolver: prefer the project venv over the system interpreter
# ──────────────────────────────────────────────────────────────────────────────
BACKEND_VENV="$PROJECT_ROOT/backend/.venv"
if [[ -x "$BACKEND_VENV/bin/python3" ]]; then
  PY="$BACKEND_VENV/bin/python3"
elif [[ -x "$BACKEND_VENV/bin/python" ]]; then
  PY="$BACKEND_VENV/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=""
fi

# ──────────────────────────────────────────────────────────────────────────────
# Environment defaults (safe for CI and local runs; override via env vars)
# ──────────────────────────────────────────────────────────────────────────────
export JTA_APP_ENV="${JTA_APP_ENV:-development}"
export JTA_AUTO_SEED="${JTA_AUTO_SEED:-false}"
export JTA_ENABLE_SCHEDULER="${JTA_ENABLE_SCHEDULER:-false}"
export JTA_ADMIN_TOKEN="${JTA_ADMIN_TOKEN:-local-proof-admin-token-change-before-deploy}"
export JTA_ADMIN_REVIEW_TOKEN="${JTA_ADMIN_REVIEW_TOKEN:-local-proof-review-token-change-before-deploy}"
export JTA_JWT_SECRET_KEY="${JTA_JWT_SECRET_KEY:-local-proof-jwt-secret-change-before-deploy-000000000000}"
export JTA_DATABASE_URL="${JTA_DATABASE_URL:-sqlite:///$OUT/proof.sqlite3}"

echo "==> proof_repo.sh  output: $OUT"
echo "==> python: ${PY:-NOT FOUND}"

# Step status variables — values: PASS | FAIL | SKIP
S_COMPILE=SKIP
S_TESTS=SKIP
S_ALEMBIC=SKIP
S_TYPECHECK=SKIP
S_BUILD=SKIP
S_DOCKER=SKIP
S_HEALTH=SKIP

# ──────────────────────────────────────────────────────────────────────────────
# 1. Backend compile
# ──────────────────────────────────────────────────────────────────────────────
echo "--- backend_compile"
if [[ -n "$PY" ]]; then
  "$PY" -m compileall -q "$PROJECT_ROOT/backend/app" \
    > "$OUT/backend_compile.log" 2>&1
  rc=$?
  [[ $rc -eq 0 ]] && S_COMPILE=PASS || S_COMPILE=FAIL
else
  printf 'SKIPPED: python interpreter not found\n' > "$OUT/backend_compile.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 2. Backend tests
# ──────────────────────────────────────────────────────────────────────────────
echo "--- backend_tests"
if [[ -n "$PY" ]] && "$PY" -c "import pytest" 2>/dev/null; then
  pushd "$PROJECT_ROOT/backend" > /dev/null
  "$PY" -m pytest -q > "$OUT/backend_tests.log" 2>&1
  rc=$?
  popd > /dev/null
  [[ $rc -eq 0 ]] && S_TESTS=PASS || S_TESTS=FAIL
else
  printf 'SKIPPED: pytest not installed in %s\n' "${PY:-system python}" \
    > "$OUT/backend_tests.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 3. Alembic upgrade
# ──────────────────────────────────────────────────────────────────────────────
echo "--- alembic_upgrade"
if [[ -n "$PY" ]] && "$PY" -c "import alembic" 2>/dev/null; then
  pushd "$PROJECT_ROOT/backend" > /dev/null
  "$PY" -m alembic upgrade head > "$OUT/alembic_upgrade.log" 2>&1
  rc=$?
  popd > /dev/null
  [[ $rc -eq 0 ]] && S_ALEMBIC=PASS || S_ALEMBIC=FAIL
else
  printf 'SKIPPED: alembic not installed\n' > "$OUT/alembic_upgrade.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 4. Frontend typecheck
# ──────────────────────────────────────────────────────────────────────────────
echo "--- frontend_typecheck"
if command -v npm >/dev/null 2>&1 && [[ -f "$PROJECT_ROOT/frontend/package.json" ]]; then
  pushd "$PROJECT_ROOT/frontend" > /dev/null
  npm run typecheck > "$OUT/frontend_typecheck.log" 2>&1
  rc=$?
  popd > /dev/null
  [[ $rc -eq 0 ]] && S_TYPECHECK=PASS || S_TYPECHECK=FAIL
else
  printf 'SKIPPED: npm not found or frontend/package.json absent\n' \
    > "$OUT/frontend_typecheck.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 5. Frontend build
# ──────────────────────────────────────────────────────────────────────────────
echo "--- frontend_build"
if command -v npm >/dev/null 2>&1 && [[ -f "$PROJECT_ROOT/frontend/package.json" ]]; then
  pushd "$PROJECT_ROOT/frontend" > /dev/null
  npm run build > "$OUT/frontend_build.log" 2>&1
  rc=$?
  popd > /dev/null
  [[ $rc -eq 0 ]] && S_BUILD=PASS || S_BUILD=FAIL
else
  printf 'SKIPPED: npm not found or frontend/package.json absent\n' \
    > "$OUT/frontend_build.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 6. Docker compose up (and tear down)
# ──────────────────────────────────────────────────────────────────────────────
echo "--- docker_compose"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  pushd "$PROJECT_ROOT" > /dev/null
  docker compose up -d --build > "$OUT/docker_compose.log" 2>&1
  rc=$?
  popd > /dev/null

  if [[ $rc -eq 0 ]]; then
    S_DOCKER=PASS
    (cd "$PROJECT_ROOT" && docker compose ps) >> "$OUT/docker_compose.log" 2>&1 || true

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Health check (only runs if compose came up cleanly)
    # ──────────────────────────────────────────────────────────────────────────
    echo "--- healthcheck"
    sleep 5
    if curl -fsS http://localhost:8000/health > "$OUT/healthcheck.log" 2>&1; then
      printf '\nbackend /health: PASS\n' >> "$OUT/healthcheck.log"
      S_HEALTH=PASS
    else
      printf '\nbackend /health: FAIL (could not reach http://localhost:8000/health)\n' \
        >> "$OUT/healthcheck.log"
      S_HEALTH=FAIL
    fi

    # Always tear down; failure here is non-fatal
    (cd "$PROJECT_ROOT" && docker compose down -v) >> "$OUT/docker_compose.log" 2>&1 || true
  else
    S_DOCKER=FAIL
    printf 'SKIPPED: docker compose up returned non-zero (%d)\n' "$rc" \
      > "$OUT/healthcheck.log"
  fi
else
  printf 'SKIPPED: docker or docker compose not available in PATH\n' \
    > "$OUT/docker_compose.log"
  printf 'SKIPPED: docker or docker compose not available in PATH\n' \
    > "$OUT/healthcheck.log"
fi

# ──────────────────────────────────────────────────────────────────────────────
# proof_summary.md
# ──────────────────────────────────────────────────────────────────────────────
PASS_COUNT=0; FAIL_COUNT=0; SKIP_COUNT=0
for _s in "$S_COMPILE" "$S_TESTS" "$S_ALEMBIC" "$S_TYPECHECK" "$S_BUILD" "$S_DOCKER" "$S_HEALTH"; do
  case "$_s" in
    PASS) PASS_COUNT=$((PASS_COUNT + 1)) ;;
    FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
    *)    SKIP_COUNT=$((SKIP_COUNT + 1)) ;;
  esac
done

OVERALL=PASS
[[ $FAIL_COUNT -gt 0 ]] && OVERALL=FAIL

COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
GENERATED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$OUT/proof_summary.md" <<SUMMARY
# Proof Summary

<!-- Machine-generated by scripts/proof_repo.sh — do not edit manually. -->

Generated: ${GENERATED_AT}
Commit: ${COMMIT}
Overall: **${OVERALL}**

| Step | Status |
|------|--------|
| backend_compile | ${S_COMPILE} |
| backend_tests | ${S_TESTS} |
| alembic_upgrade | ${S_ALEMBIC} |
| frontend_typecheck | ${S_TYPECHECK} |
| frontend_build | ${S_BUILD} |
| docker_compose | ${S_DOCKER} |
| healthcheck | ${S_HEALTH} |

PASS=${PASS_COUNT}  FAIL=${FAIL_COUNT}  SKIP=${SKIP_COUNT}

## Interpretation

- **PASS** — step executed and exited 0.
- **FAIL** — step executed and exited non-zero; see individual log for details.
- **SKIP** — dependency absent; step was not attempted (not a failure).
  Open the corresponding \`.log\` file for the skip reason.

Artifacts are at: \`artifacts/proof/latest/\`
SUMMARY

echo ""
echo "==> proof_summary.md"
cat "$OUT/proof_summary.md"

# Exit non-zero only when there are hard FAILures; SKIPs are acceptable.
[[ $FAIL_COUNT -eq 0 ]]
