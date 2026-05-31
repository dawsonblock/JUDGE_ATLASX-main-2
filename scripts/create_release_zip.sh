#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_OUTPUT="JUDGE_ATLAS-main-final.zip"
DEFAULT_ROOT_NAME="JUDGE_ATLAS-main"

OUTPUT="${DEFAULT_OUTPUT}"
ROOT_NAME="${DEFAULT_ROOT_NAME}"
ALLOW_NON_AUTHORITATIVE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --root-name)
      ROOT_NAME="$2"
      shift 2
      ;;
    --allow-non-authoritative)
      ALLOW_NON_AUTHORITATIVE=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      exit 2
      ;;
  esac
done

if [[ "${OUTPUT}" = /* ]]; then
  OUT_PATH="${OUTPUT}"
else
  OUT_PATH="${ROOT_DIR}/${OUTPUT}"
fi

if [[ "${ALLOW_NON_AUTHORITATIVE}" != "true" ]]; then
  echo "BLOCKED_RELEASE_PATH: create_release_zip.sh is non-authoritative and disabled by default."
  echo "Use scripts/package_and_validate_release_archive.sh for distributable release archives."
  echo "Pass --allow-non-authoritative only for internal/source-snapshot exchange." 
  exit 1
fi

if [[ "${OUT_PATH}" == *"JUDGE_ATLAS-main-final.zip"* ]]; then
  echo "BLOCKED_RELEASE_PATH: non-authoritative helper cannot produce JUDGE_ATLAS-main-final.zip"
  echo "Use scripts/package_and_validate_release_archive.sh for canonical release output."
  exit 1
fi

echo "[create_release_zip] Building archive: ${OUT_PATH}"
python3 "${ROOT_DIR}/scripts/build_release_archive.py" \
  --output "${OUT_PATH}" \
  --root-name "${ROOT_NAME}"

echo "[create_release_zip] NON_AUTHORITATIVE_SNAPSHOT: true"
echo "[create_release_zip] Do not publish this archive as a release artifact."

echo "[create_release_zip] Running release zip validation"
python3 "${ROOT_DIR}/scripts/validate_release_zip.py" --zip "${OUT_PATH}"

echo "[create_release_zip] Running release surface validation"
python3 "${ROOT_DIR}/scripts/check_release_surface.py" --archive "${OUT_PATH}"

echo "[create_release_zip] Archive is clean and validated: ${OUT_PATH}"
