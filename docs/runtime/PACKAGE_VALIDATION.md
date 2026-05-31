# Package Validation Runbook

This runbook defines the package-level validation flow for the JUDGE-main runtime.

## Scope

- Current status: proof-hardened alpha.
- Not ready for production deployment.
- Does not hold legal authority.
- Evidence snapshots are authoritative; memory is derivative.
- AI is reviewer assistance only.

## Authoritative Runtime

- Runtime root: `JUDGE-main/`
- `external/` folders are reference-only and not runtime code.

## Supported Archive Root Shapes

Archive validation supports both package layouts:

- `JUDGE-main/`
- `*/JUDGE-main/`

Path detection is implemented by `scripts/archive_validation_paths.py` and exercised by `backend/app/tests/test_archive_validation_paths.py`.

## Local Validation Procedure

Preferred one-command flow:

```bash
make release-package-proof-local
```

This command runs release proof generation, builds a final nested distributable archive,
validates the archive, validates the extracted runtime tree, and checks hash synchronization
across current proof artifacts.

Equivalent script entry point:

```bash
bash scripts/package_and_validate_release_archive.sh
```

From `JUDGE-main/`:

```bash
bash scripts/check_no_pyc.sh
python scripts/check_external_boundaries.py
python backend/scripts/check_repo_boundaries.py
python backend/scripts/check_no_direct_ingestion_network_clients.py
python scripts/validate_workflows.py
python scripts/check_false_claims.py
python scripts/check_truth_claims.py
python scripts/check_proof_freshness.py
python scripts/check_proof_freshness.py --strict-extra-files
```

Regenerate current proof artifacts:

```bash
make release-proof-local
```

## Final Distributable Archive Validation

Create a final full-workspace archive from the parent directory that yields a nested runtime root:

```bash
cd ..
zip -qr /tmp/JUDGE_ATLAS-main-final.zip JUDGE_ATLAS-main
cd JUDGE_ATLAS-main/JUDGE-main
bash scripts/validate_archive_proof.sh /tmp/JUDGE_ATLAS-main-final.zip
```

Expected archive log entries include:

- archive path
- extraction directory
- resolved `JUDGE-main` path
- `release_gate.json` proof hash
- proof freshness hash
- PASS or FAIL per required package check
- final extracted-archive PASS or FAIL

Canonical log path:

- `artifacts/proof/current/archive_validation.log`

## Required Hash Synchronization

The following artifacts must report the same `proof_input_tree_hash`:

- `artifacts/proof/current/release_gate.json`
- `artifacts/proof/current/CURRENT_PROOF.md`
- `artifacts/proof/current/proof_freshness.log`
- `artifacts/proof/current/archive_validation.log`

## CI Expectations

`alpha-release-proof.yml` must:

1. run `scripts/package_and_validate_release_archive.sh`
2. create a nested archive shape (`*/JUDGE-main/`)
3. run `bash scripts/validate_archive_proof.sh <archive>` against that archive
4. upload current proof artifacts

This keeps package-level proof freshness and archive validation synchronized with the distributable zip shape.