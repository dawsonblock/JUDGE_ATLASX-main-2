# JUDGE_ATLAS Source Registry Cleanup Report

Date: 2026-05-13

## Executive Summary

The source-registry cleanup objectives were implemented to reduce ambiguity, enforce truthful operational posture, and prioritize evidence-linked ingestion paths. The strongest runnable ingestion path remains Justice Canada XML. Admin surfaces now expose lifecycle and operator guidance directly, duplicate/deprecated sources are explicit, and language guards are strengthened to block unsupported public claims.

## What Changed

### Phase 3: Justice Canada XML Test Coverage

Added comprehensive tests with fixture-based XML and mocked fetchers:

- `backend/app/tests/test_justice_canada_xml_parser.py`
  - Index parsing assertions (acts/regulations, required fields, wrong-root handling)
  - Statute parsing assertions (identification, dates, sections/subsections, key stability)
- `backend/app/tests/test_laws_justice_xml_adapter.py`
  - Fetch behavior, parse output schema, and run lifecycle behavior
  - Updated one assertion to align with `IngestionResult.errors` list semantics

Validation:
- `41 passed` across the two new test modules on Python 3.11.9.

### Phase 5: lifecycle_state in Admin UI + API Contract

Lifecycle fields are now represented in both frontend type contracts and backend responses:

- `frontend/lib/api.ts`
  - `AdminSourceItem` includes:
    - `lifecycle_state`
    - `canonical_replacement_key`
    - `status_reason`
    - `operator_next_step`
- `frontend/lib/sourceContracts.ts`
  - Added `LifecycleState` union, labels, colours, and helpers
- `frontend/components/SourceControlCard.tsx`
  - Added lifecycle badge
  - Run gating recognizes runnable lifecycle state
  - Deprecated warning and operator guidance surfaced in-card
- `backend/app/api/routes/admin_sources.py`
  - `SourceResponse` now serializes lifecycle/replacement/reason/next-step fields

### Phase 6: Public Language Guard Hardening

Extended `scripts/check_truth_claims.py` with attribution and characterisation phrases to block unsupported public claims (including guilt/corruption/risk-score style language). Added scoped policy allowlist entries for files that contain these phrases only in prohibitory contexts (safety tests, legal constraints, suppression rules, and policy docs).

Validation:
- `scripts/check_truth_claims.py --root .` passes clean.

## Proof Commands Run

Executed on Python 3.11.9:

1. `python -m pytest backend/app/tests/test_justice_canada_xml_parser.py backend/app/tests/test_laws_justice_xml_adapter.py -v`
2. `python scripts/check_source_keys.py`
3. `python scripts/check_statuses.py`
4. `python scripts/check_truth_claims.py`
5. `python scripts/check_external_boundaries.py`
6. `python scripts/generate_source_registry_truth_table.py`

Artifacts produced/updated by proof run:

- `docs/SOURCE_REGISTRY_STATUS.md`
- `artifacts/proof/current/SOURCE_REGISTRY_STATUS.json`
- `artifacts/proof/current/source_registry_status.log`
- `docs/proof/source_registry_cleanup_20260513.txt`

## Current Outcome

- Truth posture: strengthened and CI-enforceable.
- Registry clarity: improved via lifecycle state + deprecated replacement metadata.
- Runnable path priority: Justice Canada XML is covered by robust tests.
- Operator UX: improved with explicit status reason and next-step guidance in admin card UI.

## Residual Notes

- A passlib deprecation warning (`crypt` removal in Python 3.13) appears in pytest output. This is non-blocking for this cleanup scope.