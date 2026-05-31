#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$REPO_ROOT"

bash scripts/check_no_pyc.sh
$PYTHON_BIN scripts/check_source_keys.py --root backend/app --repo-root .
$PYTHON_BIN scripts/check_statuses.py --root backend/app
$PYTHON_BIN scripts/check_external_boundaries.py
$PYTHON_BIN backend/tools/check_migrations.py
uv run --directory "$REPO_ROOT/backend" pytest -q
