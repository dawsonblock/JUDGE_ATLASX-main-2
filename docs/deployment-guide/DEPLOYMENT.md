# DEPLOYMENT (Alpha)

This document describes alpha deployment posture only.

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

The source registry is the authoritative source of truth for ingestion status. Only sources marked as "enabled_runnable" in the source registry are currently active.

## Deployment Classification

- Target: proof-gated alpha deployment
- Not ready for production deployment
- No legal authority claims
- Canadian source coverage is partial; do not claim full Canadian ingestion completeness.
- Release recommendation must not exceed `alpha-demo` for this repository profile.

## Required Pre-Deploy Proof

Run and review all of the following on the current code state:

- `backend/.venv/bin/python scripts/release_gate.py`
- `bash scripts/package_and_validate_release_archive.sh`
- `bash scripts/proof_all_current.sh`

Required artifacts:

- STATUS.md
- artifacts/proof/current/CURRENT_PROOF.md
- artifacts/proof/current/release_gate.json
- artifacts/proof/current/release_readiness.md

## Hard Safety Gates

- Ingestion remains fail-closed.
- Public visibility remains review/evidence gated.
- Evidence snapshots remain immutable and hash-checked.
- Memory remains derivative of evidence.

If any gate fails, release recommendation is `blocked`.
