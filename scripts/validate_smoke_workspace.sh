#!/usr/bin/env bash
set -euo pipefail

PROFILE="${TOOLATHLON_PROFILE:-smoke}"
if [[ "${PROFILE}" != "smoke" ]]; then
  echo "validate_smoke_workspace.sh requires TOOLATHLON_PROFILE=smoke"
  exit 2
fi

RUN_DOCKER="${RUN_DOCKER:-0}"
CMD=(python3 scripts/validate_workspace.py --profile smoke)
if [[ "${RUN_DOCKER}" == "1" ]]; then
  CMD+=(--run-docker)
fi

"${CMD[@]}"
