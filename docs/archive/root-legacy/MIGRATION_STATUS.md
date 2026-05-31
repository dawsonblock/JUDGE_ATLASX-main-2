# MIGRATION STATUS

## Database Migration Policy
- Schema changes must be tracked in Alembic.
- Head consistency must be validated in CI and pre-release checks.

## Verification
Run:
- `pytest app/tests/test_alembic_heads.py`

## Notes
- Migration state is considered healthy only when tests pass in the active deployment branch/environment.
- Any drift between model and migration state is a release blocker.
