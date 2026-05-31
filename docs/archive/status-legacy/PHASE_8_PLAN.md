# Phase 8: Runtime Mutation Hardening

> Historical planning document.
> Current release authority is the active proof/gate scripts and current proof
> receipts under `artifacts/proof/current/`.
> This file does not indicate production or release readiness.

## Status: Planned for Phase 8 (after Phase 7 JWT enforcement)

This document outlines the Phase 8 work to enforce runtime mutation constraints: immutability, publication gates, audit trails, and AI contract validation.

## Current State (Post-Phase 7)

✅ **Implemented and working:**
- Audit logging infrastructure exists (`app.auth.admin.log_mutation`)
- Immutability guards exist (`app.evidence.immutable_store.assert_*_fields_immutable`)
- Publication gates exist (evidence snapshot requirement, public_visibility checks)
- JWT mutation enforcement is now default-on

⚠️ **Partially integrated:**
- Audit logging is called in some routes but not consistently wired
- Immutability checks exist but are not called anywhere in mutation endpoints
- Publication gates are checked for evidence but not for all entity types
- AI contract validation is not enforced at mutation time

## Phase 8 Subtasks

### 8.1: Audit Trail Wiring (CRITICAL)
**Objective:** Ensure all mutation endpoints log to AuditLog.

**Current gaps:**
- Some admin_ingest.py endpoints may not log
- Some admin_memory.py endpoints may not log
- admin_quarantine.py endpoints may not log

**Implementation:**
1. Add `log_mutation()` calls to all POST/PUT/DELETE endpoints that don't have them
2. Pass Request object, AdminActor, and mutation payload
3. Include action code (e.g., 'source.enable', 'review.approve', 'ingest.retry')
4. Verify all entries are written before response

**Acceptance Criteria:**
- 100+ mutation operations logged in pytest test suite
- No mutation endpoint can execute without AuditLog entry
- Request context (IP, user-agent) is captured

### 8.2: Immutability Enforcement (HIGH)
**Objective:** Prevent modification of evidence-linked and published records.

**Current gaps:**
- `assert_snapshot_fields_immutable()` is defined but never called
- `assert_incident_fields_immutable()` is defined but never called
- No check before editing CrimeIncident or Event records

**Implementation:**
1. Wire immutability checks into review decision endpoint (admin_review.py) before status update
2. Add immutability checks to any source/incident PATCH endpoints
3. Raise 422 with ImmutabilityError on violation
4. Add tests for immutability enforcement

**Acceptance Criteria:**
- Cannot re-edit review_status of published event
- Cannot change source_snapshot_id, external_id of incident linked to published record
- ImmutabilityError raises with clear message
- Tests cover success and failure paths

### 8.3: Publication Gate Enforcement (MEDIUM)
**Objective:** Ensure public visibility can only be set if all preconditions are met.

**Current state:**
- Evidence snapshot requirement is checked in admin_review.py (line 257)
- AI contract validation is not checked

**Implementation:**
1. Create `app.policies.publication_gate.py` module
2. Implement `can_publish_entity(entity, db)` function checking:
   - Evidence snapshot exists and has content_hash
   - No integrity violations (via verify_evidence_store)
   - AI contract validation (if configured)
3. Wire check into review decision endpoint before setting public_visibility
4. Add tests for gate enforcement

**Acceptance Criteria:**
- Cannot publish without snapshot
- Cannot publish with corrupted snapshot
- AI validation blocks publish if misconfigured
- Detailed error messages on gate failure

### 8.4: AI Contract Validation (MEDIUM)
**Objective:** Enforce AI-generated metadata constraints at mutation time.

**Current state:**
- AI modules exist but are not called during mutations
- No validation of AI output before publication

**Implementation:**
1. Check if AI-generated fields are present (confidence scores, classifications)
2. Validate confidence scores are within [0, 1]
3. Validate classification enums match allowed values
4. Log AI contract violations to audit trail
5. Add bypass for rule-based (non-AI) records

**Acceptance Criteria:**
- AI records have valid confidence/classification before publication
- Rule-based records bypass AI validation
- Violations are logged and monitored
- Errors are returned with 422 status

### 8.5: Boundary Runtime Enforcement (LOW)
**Objective:** Prevent violations of architectural boundaries at mutation time.

**Current state:**
- Boundaries are checked in CI via `check_repo_boundaries.py`
- Not enforced at runtime

**Implementation:**
1. Create `app.boundaries.runtime_check.py` module
2. Implement `verify_mutation_respects_boundaries(action, entity_type)` function
3. Check source class eligibility for auto-ingest
4. Check entity type is not from reference repos
5. Wire check into mutation endpoints

**Acceptance Criteria:**
- Cannot enable non-machine_ingest source
- Cannot create entities from reference repo provenances
- Boundary violations are logged with action code
- 422 error returned on boundary violation

## Phased Rollout

**Phase 8.1 (Session N+1):** Audit Trail Wiring
- Add log_mutation calls to all remaining endpoints
- Add audit trail tests
- Verify 100% endpoint coverage

**Phase 8.2 (Session N+2):** Immutability Enforcement
- Wire immutability checks
- Add tests for published record protection
- Document immutable fields per entity type

**Phase 8.3-8.5 (Session N+3+):** Publication Gates, AI Validation, Boundary Enforcement
- Implement in priority order based on known violations
- Integration test full mutation workflow

## Risk Mitigation

- **Breaking Changes:** Phase 8.1 audit trail is non-breaking (append-only). Phases 8.2-8.4 will require test updates.
- **AI Integration:** Phase 8.4 requires optional AI provider setup; bypass by default.
- **Boundary Runtime:** Phase 8.5 only blocks invalid source classes (already validated in registry).

## Validation

After Phase 8 completion:
- Run `bash scripts/ci_all.sh` with phase-8 blockers enabled
- Audit trail should show 2000+ entries for full test suite
- No mutation should bypass immutability, publication, or boundary checks
- Proof artifacts should show 100% enforcement

## Files to Create/Modify

**Create:**
- `app/policies/publication_gate.py` — Publication gate checks
- `app/policies/ai_contract_validation.py` — AI validation
- `app/boundaries/runtime_check.py` — Boundary enforcement

**Modify:**
- `app/api/routes/admin_*.py` — Add audit logging and gate checks to mutation endpoints
- `app/tests/conftest.py` — Add fixtures for audit trail verification
- `backend/scripts/proof_all.py` — Add Phase 8 checks

