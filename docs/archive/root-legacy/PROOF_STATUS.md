# PROOF STATUS

## Required Proof Commands
- `python -m backend.tools.validate_sources`
- `python -m backend.tools.verify_evidence_store`
- `python -m backend.tools.verify_audit_chain`
- Backend test suite (`pytest` from backend workspace)

## Current State
- Verification tooling is present and proof-gated in release scripts.
- Proof receipts must be regenerated after each material change.
- A release is not considered proven until fresh command outputs are captured.
- Current posture is alpha-only: not suitable for production deployment and not eligible for general release.

## Artifact Policy
Store proof outputs under `artifacts/proof/` with timestamped run metadata.
Referenced logs in proof manifests must exist on disk; missing referenced logs are a gate failure.
