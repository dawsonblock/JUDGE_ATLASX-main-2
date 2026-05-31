# Legacy Shared-Token Auth Removal Plan

## Scope

This plan governs the removal of deprecated legacy shared-token mutation compatibility.

## Current State

- JWT mutation authority is the current mutation-auth standard.
- Legacy shared-token compatibility is deprecated and transition-only.
- Existing tests verify deprecation warnings, opt-in behavior, and guardrails.

## Removal Phases

1. Phase 1: Inventory
- Enumerate all shared-token code paths, configs, scripts, and tests.
- Produce an implementation checklist with owners.

2. Phase 2: Hard-disable mode
- Ensure a hard-disable mode exists for shared-token mutation auth in all environments.
- Keep default behavior deny-by-default.

3. Phase 3: JWT migration
- Migrate remaining admin scripts/tests to JWT-only mutation auth.
- Remove reliance on shared-token for operational paths.

4. Phase 4: Route removal
- Remove shared-token acceptance from mutation routes.
- Keep strict fail-closed behavior for audit and authorization.

5. Phase 5: Documentation cleanup
- Remove shared-token compatibility guidance from current-facing docs.
- Retain only historical notes where needed.

6. Phase 6: Regression guard
- Add CI guard/check preventing reintroduction of shared-token mutation acceptance.

## Exit Criteria

- No mutation route accepts shared-token authentication.
- No production configuration enables shared-token mutation authentication.
- Tests prove JWT-only mutation authority for mutation routes.
- Current-facing docs reflect JWT-only mutation authority.

## Target

- Target removal: before beta gate, and before any production deployment claim.

## Notes

- This plan does not weaken current safety controls.
- This plan does not imply production-readiness or legal authority.
