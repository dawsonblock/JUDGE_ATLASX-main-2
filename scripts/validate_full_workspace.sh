#!/usr/bin/env bash
set -euo pipefail

PROFILE="${TOOLATHLON_PROFILE:-full}"
if [[ "${PROFILE}" != "full" ]]; then
  echo "validate_full_workspace.sh requires TOOLATHLON_PROFILE=full"
  exit 2
fi

RUN_DOCKER="${RUN_DOCKER:-0}"
CMD=(python3 scripts/validate_workspace.py --profile full)
if [[ "${RUN_DOCKER}" == "1" ]]; then
  CMD+=(--run-docker)
fi

"${CMD[@]}"
