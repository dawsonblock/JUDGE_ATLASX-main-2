# Fix Verification Report — Alpha Cleanup (Phases A–H)

**Date:** 2025-07-11
**Base commit:** a906bb7
**Status:** All verifiable checks PASS

---

## Changes Made

### Phase A — Repo Boundary & Path Hygiene

| File | Change |
|------|--------|
| `scripts/check_path_hygiene.py` | **Created.** CI guard that walks repo and fails on whitespace/control chars in any path component. Skip dirs include `research`, `external`, `.venv`, `.nox`, `node_modules`. |
| `scripts/check_no_generated_files.py` | Added `"research"` and `"external"` to `SKIP_DIRS`. |
| `.dockerignore` | Added `research/` after `external/` — research tree is never bundled in any Docker image. |

### Phase B — Archive Validation

| File | Change |
|------|--------|
| `scripts/build_release_archive.py` | Added `"archive_validation.md"` and `"archive_validation.log"` to `EXCLUDED_FILE_NAMES`. Added `--dry-run` flag: lists files that would be archived without writing the zip. |
| `scripts/validate_release_archive.py` | Added `"archive_validation.md"` and `"archive_validation.log"` to `FORBIDDEN_FILE_NAMES`. Added `research` path check: any `research/` component beyond the first emits `forbidden_research_path` error. |
| `backend/app/tests/test_validate_release_archive.py` | Added 3 new test cases: `rejects_research_path`, `rejects_archive_validation_md`, `rejects_archive_validation_log`. |
| `backend/app/tests/test_build_release_archive.py` | Added 2 new test cases: `dry_run_does_not_write_zip`, `archive_validation_files_excluded`. |

### Phase C — Proof & Backend Venv Enforcement

| File | Change |
|------|--------|
| `scripts/proof_postgis.sh` | Replaced silent `python3` fallback with hard `BLOCKED_BACKEND_VENV` exit. Added Python dependency preflight (`sqlalchemy`, `geoalchemy2`, `psycopg`, `alembic`) with `BLOCKED_MISSING_PYTHON_DEPS` on failure. |
| `Dockerfile.proof` | `FROM python:3.9.7-slim` → `FROM python:3.11-slim`. |
| `scripts/release_gate.py` | `BACKEND_PYTHON` block: missing-venv path now emits `BLOCKED_BACKEND_VENV` and returns 1 instead of silently falling back to `sys.executable`. |

### Phase D — Frontend Node 20 Enforcement

| File | Change |
|------|--------|
| `scripts/release_gate.py` | All 6 frontend `GateStepSpec` entries replaced with `["bash", "-lc", "NVM_DIR=... nvm use 20 || exit 1; <cmd>"]` variants. Node version mismatch emits `BLOCKED_NODE_VERSION` signal. |
| `docs/frontend_verification.md` | Replaced stale April 2025 content with current Node 20 setup guide (nvm install, verify, auto-switch, common failure modes, CI reference). |

### Phase G — CI Quality Gate

| File | Change |
|------|--------|
| `.github/workflows/quality-gate.yml` | Added `Guard — path hygiene` step (runs `check_path_hygiene.py --root .`) after the no-generated-files guard. |

---

## Verification Results

```
backend/app/tests/test_validate_release_archive.py  9/9 PASSED
backend/app/tests/test_build_release_archive.py     3/3 PASSED
Total: 12 passed in 0.19s
```

---

## Signals Introduced

| Signal | Trigger |
|--------|---------|
| `BLOCKED_BACKEND_VENV` | Backend venv not activated; `proof_postgis.sh` or `release_gate.py` cannot find correct Python. |
| `BLOCKED_MISSING_PYTHON_DEPS` | `sqlalchemy`, `geoalchemy2`, `psycopg`, or `alembic` missing from active Python. |
| `BLOCKED_NODE_VERSION` | `nvm use 20` fails — system Node is not 20 and NVM cannot switch. |
| `forbidden_research_path` | Release archive contains a path under `research/`. |
| `forbidden_secret_file` | Release archive contains `archive_validation.md` or `archive_validation.log`. |
