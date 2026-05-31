# Final Release Handoff

This document is generated from the built archive and
canonical proof artifacts.
Manual edits are not authoritative.

## Authoritative Archive
- Path: dist/JUDGE_ATLAS-main-final.zip
- SHA-256: b67a8cb47daf2a439bfbb6e21362cb445eb7b97219637a1f1b55aa82d921de97

## Proof Anchors
- release_gate_path: artifacts/proof/current/release_gate.json
- release_gate_sha256: b6d47946f66f022e02946be98cc504e52983de2b810b717030b566a262f7dd55
- proof_manifest_path: artifacts/proof/current/proof_manifest.json
- proof_manifest_sha256: c5de91672ff0678299dd1f577502b484f9a918149bf114ebd8c70e924f604bec
- required_log_index_path: artifacts/proof/current/required_log_index.json
- required_log_index_sha256: e6ba82d84ef65a060823c675686ce1684b265e8c37cd424a26607d4d408cec03

## Release Status
- release_classification: proof-hardened alpha release candidate
- alpha_gate_passed: true
- release_candidate: true
- production_ready: false
- proof_complete: true
- blocked_release_checks: []

## Build Metadata
- created_at_utc: 2026-05-28T22:14:48.851190+00:00
- generated_at_utc: 2026-05-28T22:14:48.851190+00:00
- git_commit: unknown
- python: unknown
- node: unknown
- npm: unknown

## Notes
- This is a proof-hardened alpha release candidate.
- It is not ready for production deployment.
- Ship only the archive listed above.
- Validation must run against a fresh extraction
  of that archive.
- `release_gate.json` is only valid as a proof artifact when every
  log path it references exists inside `artifacts/proof/current/`
  at packaging time. Do not ship manually zipped working trees.
