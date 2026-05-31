# REPO_REALITY

## What This App Is

JUDGE-main is the runtime application: a proof-gated alpha judicial/legal accountability platform with a FastAPI backend, Next.js frontend, evidence snapshot storage, review workflows, and public visibility gates.

## What Is Live Runtime

- Backend runtime: JUDGE-main/backend
- Frontend runtime: JUDGE-main/frontend
- Canonical proof gate: JUDGE-main/scripts/release_gate.py
- Canonical status entry point: JUDGE-main/STATUS.md
- Canonical current proof artifacts: JUDGE-main/artifacts/proof/current
- Canonical current proof summary: JUDGE-main/artifacts/proof/current/CURRENT_PROOF.md
- Canonical current release readiness: JUDGE-main/artifacts/proof/current/release_readiness.md
- Canonical Justice law machine-ingest source key: `justice_canada_laws_xml`

## Reference-Only Trees

These folders are not runtime dependencies and must not be imported directly by runtime modules:

- external/CLI-Anything-main
- external/memvid-Human--main-main

Any exception requires an explicit wrapper, dedicated tests, and documentation.

## Disabled/Fail-Closed Defaults

- Source ingestion is disabled by default unless explicitly enabled in source registry controls.
- Non-machine source classes (for example `portal_reference`, `disabled_stub`) are not runnable.
- Public endpoints remain review/public-visibility gated.
- Memory claims are derivative and cannot override raw evidence/snapshots.

## Not Production Ready

- Current classification: proof-hardened alpha.
- Not ready for production deployment.
- No legal authority.
- No autonomous adjudication.

## Required Proof Commands

Run these before claiming current status:

- `backend/.venv/bin/python scripts/release_gate.py`
- `bash scripts/package_and_validate_release_archive.sh`
- `bash scripts/proof_all_current.sh`

Use artifacts from the same run only; do not present stale historical logs as current proof.
