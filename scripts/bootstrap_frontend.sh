#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "==> Bootstrapping frontend in $FRONTEND_DIR"
cd "$FRONTEND_DIR"

if [ -f .nvmrc ] && command -v node >/dev/null 2>&1; then
  echo "Node version: $(node --version); expected major from .nvmrc: $(cat .nvmrc)"
fi

npm ci
npm run typecheck

echo "Frontend bootstrap complete."
