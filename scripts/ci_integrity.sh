#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TMP_DB="$REPO_ROOT/backend/.ci_integrity.db"

cd "$REPO_ROOT"

$PYTHON_BIN scripts/check_false_claims.py
$PYTHON_BIN scripts/check_external_boundaries.py

rm -f "$TMP_DB"
(
	cd "$REPO_ROOT/backend"
	JTA_DATABASE_URL="sqlite:///$TMP_DB" $PYTHON_BIN -m alembic upgrade head
)

JTA_DATABASE_URL="sqlite:///$TMP_DB" $PYTHON_BIN backend/tools/verify_evidence_store.py
JTA_DATABASE_URL="sqlite:///$TMP_DB" $PYTHON_BIN backend/tools/verify_audit_chain.py
JTA_DATABASE_URL="sqlite:///$TMP_DB" $PYTHON_BIN backend/tools/check_migrations.py

rm -f "$TMP_DB"
