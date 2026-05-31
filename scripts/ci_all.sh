#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT"

bash scripts/ci_backend.sh
bash scripts/ci_integrity.sh
bash scripts/ci_frontend.sh
