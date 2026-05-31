# ARCHIVED / NOT CURRENT — see artifacts/proof/current/

# RELEASE_READINESS

- generated_at_utc: 2026-05-12T00:13:38Z
- commit: 26764ee
- proof_profile: current
- release_recommendation: blocked
- production_ready: false

## Gate Results

- backend_compile: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend_compile.log)
- backend_import: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend_import.log)
- backend_alembic_sqlite: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend_alembic_sqlite.log)
- backend_targeted_tests: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend_targeted_tests.log)
- backend_grouped_tests: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend_grouped_tests_summary.log)
- backend_justice_laws: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend/justice_laws.log)
- backend_source_registry: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend/source_registry.log)
- backend_boundary: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/backend/boundary.log)
- frontend_typecheck: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/frontend_typecheck.log)
- frontend_contracts: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/frontend_contracts.log)
- frontend_lint: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/frontend_lint.log)
- frontend_build: FAIL (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/frontend_build.log)
- source_registry_status: PASS (/Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/source_registry_status.log)

## Required Checks

- backend_compile: PASS
- backend_import: PASS
- backend_alembic_sqlite: PASS
- backend_grouped_tests: PASS
- backend_justice_laws: PASS
- backend_source_registry: PASS
- backend_boundary: PASS
- frontend_typecheck: PASS
- frontend_contracts: PASS
- frontend_lint: PASS
- frontend_build: FAIL

## Known Disabled Features

- Source ingestion remains disabled by default unless explicitly enabled by admin controls.
- Non-machine source classes (portal_reference, disabled_stub) are not runnable.
- Public publication remains review-gated and evidence-gated.

## Known Failures

- frontend_build (see /Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/frontend_build.log)

## Remaining Blockers

- frontend_build (FAIL): /Users/dawsonblock/Downloads/JUDGE_ATLAS-main-3/JUDGE-main/artifacts/proof/frontend_build.log
