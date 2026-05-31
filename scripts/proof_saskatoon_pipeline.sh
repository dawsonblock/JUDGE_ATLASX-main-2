#!/usr/bin/env bash
# Proof script: Saskatoon CSV → SourceSnapshot → CrimeIncident → ReviewItem pipeline
#
# Verifies that the Phase-1 provenance wiring is correct:
#   1. Python files compile without errors.
#   2. All four pipeline-wiring tests pass.
#   3. Migration 20260504_0010 is the single alembic head.
#   4. Alembic upgrade applies cleanly (SQLite smoke-test).
#
# Usage: bash scripts/proof_saskatoon_pipeline.sh
# Exit code: 0 = all checks passed, 1 = one or more failed.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
PROOF_DIR="$REPO_ROOT/artifacts/proof"
mkdir -p "$PROOF_DIR"
LOG="$PROOF_DIR/proof_saskatoon_pipeline.log"

echo "=== Saskatoon Pipeline Proof ===" | tee "$LOG"
echo "repo: $REPO_ROOT" | tee -a "$LOG"
echo "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

PASS=0
FAIL=0
FAILURES=()

run_step() {
    local name="$1"
    local cmd="$2"
    echo "--- $name ---" | tee -a "$LOG"
    if (cd "$REPO_ROOT" && eval "$cmd") >>"$LOG" 2>&1; then
        echo "PASS: $name" | tee -a "$LOG"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name" | tee -a "$LOG"
        FAIL=$((FAIL + 1))
        FAILURES+=("$name")
    fi
    echo "" | tee -a "$LOG"
}

# 1. Compile all backend Python files
run_step "python_compile" \
    "cd backend && python -m compileall -q app"

# 2. Pipeline-wiring unit/integration tests only
run_step "test_pipeline_wiring" \
    "cd backend && python -m pytest app/tests/test_saskatoon_pipeline_wiring.py -v"

# 3. Alembic heads = exactly 1 and is 20260504_0010
run_step "alembic_single_head_0010" \
    "cd backend && heads=\$(alembic heads 2>&1); \
     count=\$(echo \"\$heads\" | grep -c '(head)' || true); \
     echo \"heads output: \$heads\"; \
     [ \"\$count\" -eq 1 ] || { echo \"Expected 1 head, got \$count\"; exit 1; }; \
     echo \"\$heads\" | grep -q '20260504_0010' || { echo \"Head is not 20260504_0010\"; exit 1; }"

# 4. Alembic upgrade smoke-test on SQLite (DB-agnostic compilation check)
run_step "alembic_upgrade_sqlite" \
    "cd backend && { \
       JTA_DATABASE_URL=sqlite:///./proof_saskatoon.db alembic upgrade head; \
       rc=\$?; rm -f proof_saskatoon.db; exit \$rc; \
     }"

# 5. Alembic test: test_latest_migration_is_0010
run_step "test_alembic_heads" \
    "cd backend && python -m pytest app/tests/test_alembic_heads.py::test_latest_migration_is_0010 -v"

echo "" | tee -a "$LOG"
echo "=== RESULT: PASS=$PASS FAIL=$FAIL ===" | tee -a "$LOG"

if [ ${#FAILURES[@]} -gt 0 ]; then
    echo "Failed steps:" | tee -a "$LOG"
    for f in "${FAILURES[@]}"; do
        echo "  - $f" | tee -a "$LOG"
    done
fi

echo "Log saved to: $LOG"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
