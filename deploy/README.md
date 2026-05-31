# Deploy Directory

Deployment-facing runtime assets belong here for alpha packaging.

Current workflow uses repository scripts for proof-gated release generation:

- `make proof`
- `bash scripts/package_and_validate_release_archive.sh --archive-path dist/JUDGE_ATLAS-main-final.zip --package-root-name JUDGE_ATLAS-main`

Do not publish raw source snapshot ZIP files as release artifacts.
