#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"

sanitize_archive_validation_artifacts() {
  python3 - <<'PY' || true
import json
import re
from pathlib import Path

root = Path('.').resolve()
log_path = root / 'artifacts/proof/current/archive_validation.log'
md_path = root / 'artifacts/proof/current/archive_validation.md'

patterns = (
  re.compile(r"/Users/[^\s\"'`]+"),
  re.compile(r"/home/[^\s\"'`]+"),
  re.compile(r"/private/[^\s\"'`]+"),
  re.compile(r"[A-Za-z]:\\[^\s\"'`]+"),
)

repo_prefix = str(root).replace('\\', '/')

def redact_text(text: str) -> str:
  normalized = text.replace('\\', '/')
  redacted = normalized.replace(repo_prefix, '[REDACTED_LOCAL_PATH]')
  for pattern in patterns:
    redacted = pattern.sub('[REDACTED_LOCAL_PATH]', redacted)
  return redacted

def redact_file(path: Path) -> None:
  if not path.exists() or not path.is_file():
    return

  if path.suffix.lower() == '.json':
    try:
      parsed = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
      parsed = None
    if parsed is not None:
      serialized = json.dumps(parsed, indent=2)
      path.write_text(redact_text(serialized) + '\n', encoding='utf-8')
      return

  text = path.read_text(encoding='utf-8', errors='ignore')
  redacted = redact_text(text)
  if redacted != text:
    path.write_text(redacted, encoding='utf-8')

redact_file(log_path)
redact_file(md_path)
PY
}

refresh_archive_validation_manifest_entry() {
  python3 - <<'PY' || true
import hashlib
import json
from pathlib import Path

root = Path('.').resolve()
manifest_path = root / 'artifacts/proof/current/proof_manifest.json'
log_rel = 'artifacts/proof/current/archive_validation.log'
log_path = root / log_rel

if not manifest_path.exists() or not log_path.exists():
  raise SystemExit(0)

try:
  manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
except json.JSONDecodeError:
  raise SystemExit(0)

commands = manifest.get('proof_commands')
if not isinstance(commands, list):
  raise SystemExit(0)

entry = None
for candidate in commands:
  if not isinstance(candidate, dict):
    continue
  candidate_path = candidate.get('path') or candidate.get('log_path')
  if candidate_path == log_rel:
    entry = candidate
    break

if entry is None:
  raise SystemExit(0)

data = log_path.read_bytes()
digest = hashlib.sha256(data).hexdigest()
size = len(data)

entry['size_bytes'] = size
entry['sha256'] = digest
entry['log_sha256'] = digest
entry['log_exists'] = True
entry['status'] = 'PASS'

manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
PY
}

cleanup() {
  sanitize_archive_validation_artifacts
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT INT TERM

ARCHIVE_VALIDATION_LOG="${ROOT_DIR}/artifacts/proof/current/archive_validation.log"

ARCHIVE_PATH="${ROOT_DIR}/dist/JUDGE_ATLAS-main-final.zip"
PACKAGE_ROOT_NAME="JUDGE_ATLAS-main"
SKIP_RELEASE_GATE=false
SKIP_HANDOFF_CHECK=false
SKIP_EXTRACTED_VALIDATION=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive-path)
      ARCHIVE_PATH="$2"
      shift 2
      ;;
    --package-root-name)
      PACKAGE_ROOT_NAME="$2"
      shift 2
      ;;
    --skip-release-gate)
      SKIP_RELEASE_GATE=true
      shift
      ;;
    --skip-handoff-check)
      SKIP_HANDOFF_CHECK=true
      shift
      ;;
    --skip-extracted-validation)
      SKIP_EXTRACTED_VALIDATION=true
      shift
      ;;
    *)
      echo "ERROR: unknown argument: $1"
      exit 2
      ;;
  esac
done

log() {
  echo "[release_package] $*"
}

cd "${ROOT_DIR}"

log "Validating toolchain versions"
python scripts/check_toolchain_versions.py --root .

if [[ "${SKIP_RELEASE_GATE}" != "true" ]]; then
  log "Running release proof gate"
  make release-proof-local
fi

log "Validating local proof freshness"
python scripts/check_proof_freshness.py
python scripts/check_proof_freshness.py --strict-extra-files

log "Validating local proof integrity"
python scripts/check_proof_consistency.py
python scripts/check_single_proof_authority.py --root .
python scripts/check_required_proof_logs.py --root . --strict-required-files
python scripts/check_no_local_paths_in_release_proof.py --root .
python scripts/verify_status_consistency.py --root .

if [[ -f "${ARCHIVE_PATH}" ]]; then
  log "Removing stale archive before fresh build: ${ARCHIVE_PATH}"
  rm -f "${ARCHIVE_PATH}" "${ARCHIVE_PATH}.sha256"
fi

log "Building archive at ${ARCHIVE_PATH}"
python scripts/build_release_archive.py \
  --output "${ARCHIVE_PATH}" \
  --root-name "${PACKAGE_ROOT_NAME}"

archive_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
    return
  fi
  shasum -a 256 "$1" | awk '{print $1}'
}

ARCHIVE_BASENAME="$(basename "${ARCHIVE_PATH}")"
ARCHIVE_SHA256="$(archive_sha256 "${ARCHIVE_PATH}")"
ARCHIVE_SHA256_FILE="${ARCHIVE_PATH}.sha256"
printf '%s  %s\n' "${ARCHIVE_SHA256}" "${ARCHIVE_BASENAME}" > "${ARCHIVE_SHA256_FILE}"
log "Built archive filename=${ARCHIVE_BASENAME} sha256=${ARCHIVE_SHA256}"
log "Wrote archive digest file ${ARCHIVE_SHA256_FILE}"

log "Generating authoritative handoff from built archive"
python3 scripts/generate_release_handoff.py \
  --root . \
  --archive "${ARCHIVE_PATH}" \
  --output FINAL_RELEASE_HANDOFF.md

if [[ "${SKIP_HANDOFF_CHECK}" != "true" ]]; then
  log "Validating final handoff consistency"
  python scripts/check_release_handoff_consistency.py \
    --root . \
    --handoff FINAL_RELEASE_HANDOFF.md \
    --archive "${ARCHIVE_PATH}"
fi

log "Running archive validation"
bash scripts/validate_archive_proof.sh "${ARCHIVE_PATH}"

python scripts/validate_final_zip.py "${ARCHIVE_PATH}"
python scripts/check_release_surface.py --archive "${ARCHIVE_PATH}"
python scripts/verify_archive_proof_freshness.py --archive "${ARCHIVE_PATH}"

sanitize_archive_validation_artifacts
refresh_archive_validation_manifest_entry

if [[ "${SKIP_EXTRACTED_VALIDATION}" != "true" ]]; then
  log "Running extracted-archive release validation"
  python3 scripts/validate_extracted_release.py \
    --root . \
    --archive "${ARCHIVE_PATH}" \
    --expected-root "${PACKAGE_ROOT_NAME}"
fi

log "Verifying proof hash synchronization"
python scripts/verify_proof_hash_sync.py --root .

log "PASS: release package and proof validation complete"
log "AUTHORITATIVE_RELEASE_ARCHIVE=${ARCHIVE_PATH}"
log "AUTHORITATIVE_RELEASE_ARCHIVE_SHA256=${ARCHIVE_SHA256}"
log "Ship the validated archive at ${ARCHIVE_PATH} exactly; do not re-zip the working tree."
