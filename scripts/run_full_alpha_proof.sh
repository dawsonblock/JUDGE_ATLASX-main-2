#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROOF_DIR="${ROOT_DIR}/artifacts/proof/current"
ARCHIVE_PATH="${ROOT_DIR}/dist/JUDGE_ATLAS-main-final.zip"
PACKAGE_ROOT_NAME="JUDGE_ATLAS-main"
RUN_PACKAGE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-package)
      RUN_PACKAGE=true
      shift
      ;;
    --archive-path)
      ARCHIVE_PATH="$2"
      shift 2
      ;;
    --package-root-name)
      PACKAGE_ROOT_NAME="$2"
      shift 2
      ;;
    *)
      echo "ERROR: unknown argument: $1"
      exit 2
      ;;
  esac
done

mkdir -p "${PROOF_DIR}"
cd "${ROOT_DIR}"

echo "== release gate =="
if [[ -x backend/.venv/bin/python ]]; then
  backend/.venv/bin/python scripts/release_gate.py 2>&1 | tee "${PROOF_DIR}/release_gate_runner.log"
else
  python3 scripts/release_gate.py 2>&1 | tee "${PROOF_DIR}/release_gate_runner.log"
fi

echo "== proof checks =="
python3 scripts/check_required_proof_logs.py --root . --strict-required-files 2>&1 | tee "${PROOF_DIR}/required_proof_logs.log"
python3 scripts/check_proof_freshness.py 2>&1 | tee "${PROOF_DIR}/proof_freshness.log"
python3 scripts/check_proof_consistency.py 2>&1 | tee "${PROOF_DIR}/proof_consistency.log"
python3 scripts/check_single_proof_authority.py --root . 2>&1 | tee "${PROOF_DIR}/single_proof_authority.log"
python3 scripts/verify_proof_hash_sync.py --root . 2>&1 | tee "${PROOF_DIR}/proof_hash_sync.log"

if [[ "${RUN_PACKAGE}" == "true" ]]; then
  echo "== package and archive validation =="
  bash scripts/package_and_validate_release_archive.sh \
    --archive-path "${ARCHIVE_PATH}" \
    --package-root-name "${PACKAGE_ROOT_NAME}" \
    2>&1 | tee "${PROOF_DIR}/package_and_validate.log"

  python3 scripts/validate_final_zip.py "${ARCHIVE_PATH}" 2>&1 | tee "${PROOF_DIR}/validate_final_zip.log"
  python3 scripts/check_release_surface.py --archive "${ARCHIVE_PATH}" 2>&1 | tee "${PROOF_DIR}/check_release_surface.log"
  python3 scripts/validate_extracted_release.py \
    --archive "${ARCHIVE_PATH}" \
    --expected-root "${PACKAGE_ROOT_NAME}" \
    2>&1 | tee "${PROOF_DIR}/validate_extracted_release.log"
fi

echo "FULL_ALPHA_PROOF: PASS"
