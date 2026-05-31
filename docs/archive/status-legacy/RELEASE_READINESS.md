# RELEASE_READINESS

This file explains how release readiness is determined for the current alpha state.

## Source of Truth

Use current run artifacts only:

- STATUS.md
- artifacts/proof/current/CURRENT_PROOF.md
- artifacts/proof/current/release_readiness.md
- artifacts/proof/current/source_registry_status.json
- artifacts/proof/current/frontend_build.log

## Allowed Recommendation Values

- blocked
- alpha-internal
- alpha-demo
- beta-candidate
- production-candidate

Current policy for this repository:

- Do not recommend above `alpha-demo` unless every gate in `scripts/proof_all_current.sh` passes and docs/proof are current.
- Do not claim production deployment readiness.
- Do not auto-publish ingested legal records; pending and rejected records must remain non-public.
- Federal law ingestion is legal context only and must not produce public map incidents/dots.
- Canonical current proof is `artifacts/proof/current/CURRENT_PROOF.md`.
- Canonical current release readiness is `artifacts/proof/current/release_readiness.md`.
