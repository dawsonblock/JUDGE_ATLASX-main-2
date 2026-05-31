#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/bootstrap_backend.sh"
"$SCRIPT_DIR/bootstrap_frontend.sh"

echo "All bootstrap steps completed."
