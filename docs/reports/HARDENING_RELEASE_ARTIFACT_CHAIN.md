# HARDENING_RELEASE_ARTIFACT_CHAIN

## Scope

This report documents hardening actions for release artifact integrity and proof-chain continuity.

## Problem Class

A raw source snapshot can pass many repository checks while still failing release artifact validation.
Common failure modes:

- required proof logs referenced by artifacts/proof/current/release_gate.json are missing from the packaged archive
- forbidden surface content appears in archive payloads (history, external reference, local validation residue)
- proof summary files are present but packaged evidence is incomplete
- manual workspace zips are mistaken for validated release archives

## Implemented Hardening

1. Canonical release flow is fixed to scripts/package_and_validate_release_archive.sh.
2. Legacy clean builder scripts/build_clean_release.py remains hard-fail deprecated.
3. Release packaging policy now explicitly distinguishes source snapshots from authoritative release archives.
4. scripts/create_release_zip.sh is now fail-closed by default and requires --allow-non-authoritative for internal source snapshot generation.
5. scripts/create_release_zip.sh blocks any attempt to output JUDGE_ATLAS-main-final.zip and redirects operators to scripts/package_and_validate_release_archive.sh.
6. package_and_validate_release_archive.sh now runs pre-build local proof integrity checks:
   - python scripts/check_proof_consistency.py
   - python scripts/check_single_proof_authority.py --root .
   - python scripts/check_required_proof_logs.py --root . --strict-required-files
7. Repo reality wording now reflects partial valid-time support and avoids false "missing valid_from/valid_to" claims.

## Required Operator Flow

1. Regenerate proof on the exact tree intended for shipment.
2. Confirm required proof logs are present:
   - python scripts/check_required_proof_logs.py --root . --strict-required-files
3. Build and validate through one command:
   - bash scripts/package_and_validate_release_archive.sh --archive-path dist/JUDGE_ATLAS-main-final.zip --package-root-name JUDGE_ATLAS-main
4. Ship only the produced archive and checksum. Do not manually re-zip the workspace.

## Acceptance Criteria

A release candidate is accepted only when all of the following pass against the same produced archive:

- scripts/check_required_proof_logs.py
- scripts/check_proof_freshness.py
- scripts/validate_release_archive.py
- scripts/check_release_surface.py
- scripts/validate_final_zip.py
- scripts/verify_archive_proof_freshness.py

## Notes

Production ready remains false for alpha.
This hardening addresses release-proof packaging integrity, not production operational readiness.
