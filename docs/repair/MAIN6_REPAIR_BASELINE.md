# Main6 Repair Baseline

Date: 2026-05-16
Branch: repair/main6-proof-truth-hardening

## Baseline Refresh Commands

- `python scripts/release_gate.py`
- `cp artifacts/proof/current/release_gate.json artifacts/proof/current/release_gate.before_repair.json`
- `cp artifacts/proof/current/release_readiness.md artifacts/proof/current/release_readiness.before_repair.md`
- `cp artifacts/proof/current/source_registry_status.json artifacts/proof/current/source_registry_status.before_repair.json`
- `cp docs/SOURCE_REGISTRY_STATUS.md docs/SOURCE_REGISTRY_STATUS.before_repair.md`

## Baseline Truth Snapshot

- alpha_gate_passed: true
- production_ready: false
- failed_checks: []
- backend_pytest_passed: 2910
- backend_pytest_skipped: 9

## Baseline Scope Note

This baseline is captured after prior hardening work already present in this workspace.
The before_repair sidecars above are the canonical comparison points for the
remaining Main6 repair sequence executed on this branch.
