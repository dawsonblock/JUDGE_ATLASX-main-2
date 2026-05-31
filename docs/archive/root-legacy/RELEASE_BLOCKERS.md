# RELEASE BLOCKERS

A release must be blocked if any condition below is true.

## Evidence/Audit Integrity
- `verify_evidence_store` reports hash/integrity failures.
- `verify_audit_chain` reports ordering or actor-attribution violations.

## Source Governance
- `validate_sources` fails contract/policy checks.

## Authorization and Review
- Mutation endpoints allow unauthorized non-JWT writes.
- Review/publication path bypasses required reviewer decisioning.

## Migration/Test Health
- Alembic head validation fails.
- Critical backend tests fail.

## Documentation Truthfulness
- Status/proof docs claim completion without fresh receipts.
