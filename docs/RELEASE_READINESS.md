# RELEASE_READINESS

> [!WARNING]
> Manual source ZIPs (e.g., `JUDGE_ATLASX-main N.zip`, `workspace_snapshot.zip`) are **NOT authoritative release artifacts**. Only `dist/JUDGE_ATLAS-main-final.zip` produced by the canonical build pipeline may be distributed.

This document tracks release-readiness references for the active alpha surface.

## Artifact Classes

- Source snapshot archive: a raw tree export used for development exchange and inspection. It is not a distributable release artifact.
- Authoritative release archive: a zip produced only by `scripts/package_and_validate_release_archive.sh` and validated by the release/archive proof checks.

Only the authoritative release archive may be distributed as an alpha release artifact.

## Canonical References

- STATUS.md
- artifacts/proof/current/CURRENT_PROOF.md
- artifacts/proof/current/release_readiness.md

## Policy

Release readiness is determined by artifacts/proof/current/release_readiness.md and the machine-readable gate output in artifacts/proof/current/release_gate.json.
Production ready: false.

The final distributable must be the exact archive built by:

python scripts/build_release_archive.py

inside the package-and-validate flow, followed by:

- scripts/validate_release_archive.py
- scripts/check_release_surface.py
- scripts/validate_final_zip.py
- scripts/verify_archive_proof_freshness.py

Manual re-zipping of the workspace is not a supported release path.

Release publication must upload only:

- dist/JUDGE_ATLAS-main-final.zip
- dist/JUDGE_ATLAS-main-final.zip.sha256
- FINAL_RELEASE_HANDOFF.md

Wildcard archive renaming (for example, `mv dist/*.zip ...`) is not permitted in
release workflows because it can mask non-canonical wrapper archives.
