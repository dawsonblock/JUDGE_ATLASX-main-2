#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "==> JudgeTracker Atlas alpha bootstrap (macOS + VS Code)"

if [[ ! -f .env ]]; then
  echo "WARN: .env not found. Creating from .env.example for development."
  cp .env.example .env
  echo "PASS: Created .env from .env.example"
else
  echo "PASS: .env already exists"
fi

echo "==> Checking local environment prerequisites"
python3 scripts/check_local_dev_environment.py || true

echo "==> Bootstrapping backend dependencies"
bash scripts/bootstrap_backend.sh

echo "==> Bootstrapping frontend dependencies"
bash scripts/bootstrap_frontend.sh

echo "==> Re-running environment report"
python3 scripts/check_local_dev_environment.py

echo "Bootstrap completed."
