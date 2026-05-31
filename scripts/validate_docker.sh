#!/usr/bin/env bash
set -euo pipefail

PROFILE="${TOOLATHLON_PROFILE:-smoke}"
CMD=(python3 scripts/validate_workspace.py --profile "${PROFILE}" --run-docker)
"${CMD[@]}"
