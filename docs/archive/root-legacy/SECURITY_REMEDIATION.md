# SECURITY REMEDIATION

## Implemented
- Added JWT-focused mutation enforcement guard for admin mutation endpoints.
- Preserved explicit actor context on reviewed/published decisions.
- Enforced stronger source contract checks in ingestion pathways.

## Remaining
- Expand JWT mutation guard coverage to every remaining write path.
- Promote audit replay verification to mandatory CI gate.
- Add explicit alerting for evidence/audit verification failures.

## Verification
- Run backend tests for auth/admin routes and review decisions.
- Run `python -m backend.tools.verify_audit_chain`.
