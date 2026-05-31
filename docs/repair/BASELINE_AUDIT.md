# Baseline Audit

Date: 2026-05-12

## Repository Identity

- Current branch: `main`
- Current commit: `c337ec3`
- Repo name: `JUDGE_ATLAS`
- Repo root: `JUDGE-main`

## Baseline Commands Used

- `git rev-parse --short HEAD && git status --short`
- `python scripts/production_preflight.py`
- `python scripts/verify_status_consistency.py`
- `python scripts/check_proof_freshness.py`
- `python scripts/check_false_claims.py`

## Backend Entry Points

- FastAPI entrypoint: [backend/app/main.py](../../backend/app/main.py)
- Route registration: [backend/app/api/routes/**init**.py](../../backend/app/api/routes/__init__.py)
- CLI entrypoint: [backend/app/cli/main.py](../../backend/app/cli/main.py)

## Route Surface Summary

- Current route count: 103 routes (from the current backend import proof artifact)
- Main router includes public, map, ingestion, review, admin, chat, evidence, graph, and snapshot routers.
- Public endpoints are filtered through `app.serializers.public` helpers before serialization.

## Auth and Authority

- JWT/shared-token admin handling lives in [backend/app/auth/admin.py](../../backend/app/auth/admin.py).
- Import/admin role gating helpers live in [backend/app/security/import_authority.py](../../backend/app/security/import_authority.py).
- Current admin mutation routes already call JWT authority helpers, but legacy shared-token compatibility still exists in code paths.
- Frontend admin proxy auth helper lives in [frontend/app/api/admin/\_auth.ts](../../frontend/app/api/admin/_auth.ts).

## Source Registry and Ingestion Control

- Source registry control-plane helpers: [backend/app/ingestion/source_registry_ctl.py](../../backend/app/ingestion/source_registry_ctl.py)
- Admin source UI: [frontend/app/admin/sources/page.tsx](../../frontend/app/admin/sources/page.tsx)
- Source card UI: [frontend/components/SourceControlCard.tsx](../../frontend/components/SourceControlCard.tsx)
- Current source registry summary:
  - total sources: 26
  - machine_ingest sources: 7
  - runnable_when_active sources: 0
  - enableable sources: 3
  - sources requiring secrets: 5
- Secret-required sources currently unresolved:
  - `scc_judgments` -> `LEXUM_API_KEY`
  - `scc_decisions` -> `LEXUM_API_KEY`
  - `sk_courts_qb_decisions` -> `JTA_CANLII_API_KEY`
  - `sk_courts_ca_decisions` -> `JTA_CANLII_API_KEY`
  - `canlii_sk` -> `JTA_CANLII_API_KEY`

## Evidence, Review, and Public Boundary

- Evidence snapshot writer: [backend/app/services/snapshot_writer.py](../../backend/app/services/snapshot_writer.py)
- Evidence store validation: [backend/app/services/evidence_store_validation.py](../../backend/app/services/evidence_store_validation.py)
- Review/admin route surface: [backend/app/api/routes/admin_review.py](../../backend/app/api/routes/admin_review.py)
- Snapshot inspection route surface: [backend/app/api/routes/snapshots.py](../../backend/app/api/routes/snapshots.py)
- Public API filters/serializers: [backend/app/serializers/public.py](../../backend/app/serializers/public.py)
- Public event routes: [backend/app/api/routes/public_events.py](../../backend/app/api/routes/public_events.py)
- Evidence chat service: [backend/app/services/evidence_chat.py](../../backend/app/services/evidence_chat.py)
- Evidence chat API route: [backend/app/api/routes/chat.py](../../backend/app/api/routes/chat.py)

## Map and Frontend Canonical Path

- Baseline canonical public map at audit time: [frontend/app/map-v2/page.tsx](../../frontend/app/map-v2/page.tsx)
- Baseline legacy map route redirect at audit time: [frontend/app/map/page.tsx](../../frontend/app/map/page.tsx)
- Admin review UI: [frontend/app/admin/review/page.tsx](../../frontend/app/admin/review/page.tsx)

## Model Summary

`backend/app/models/entities.py` contains 45 ORM classes. Major groups:

- Core public entities: `Location`, `Court`, `Judge`, `Case`, `Defendant`, `CaseParty`, `Event`, `LegalSource`, `CrimeIncident`, `Outcome`
- Ingestion/review/proof: `IngestionRun`, `ReviewItem`, `EvidenceReview`, `ReviewActionLog`, `SourceSnapshot`, `SourceRegistry`, `SourceTierConflict`
- Audit/provenance: `AuditLog`, `ChainOfCustodyLog`, `CrimeIncidentSource`, `CrimeIncidentEventLink`, `RelationshipEvidence`, `EntityEvidenceLink`
- Canonical/memory state: `CanonicalEntity`, `EntitySourceRecord`, `EntityGraphEdge`, `MemoryRebuildRun`, `MemoryClaim`, `MemoryEvidenceLink`, `MemoryEntityState`, `MemoryInvalidation`, `MemoryRelationshipState`
- Legal and user/session: `LegalInstrument`, `LegalSection`, `CourtEvent`, `User`, `UserSession`, `CLBulkProvenance`, `CourtListenerBulkRun`, `AICorrectnessCheck`, `AICorrectnessFinding`, `Boundary`

## Production Preflight Baseline

Current production preflight result: FAIL

Failures reported by [scripts/production_preflight.py](../../scripts/production_preflight.py):

- `ENVIRONMENT=dev` is not production/staging
- `JTA_JWT_SECRET` is missing or weak
- `REDIS_URL` is missing
- `EVIDENCE_STORE_ROOT` is unset
- `CORS_ALLOWLIST` is unset
- `JTA_FETCH_EGRESS_PROXY` is missing
- `DATABASE_URL` is missing
- `BACKUP_POLICY` is missing

Passes reported:

- legacy shared admin token is disabled
- debug mode is disabled

## Known Stubs and Placeholders

Current stub inventory from [STUBS_AND_PLACEHOLDERS.md](../../STUBS_AND_PLACEHOLDERS.md):

- Canadian law modules under `backend/app/ingestion/laws` remain stubbed or partial
- Web monitor police/government release adapters remain experimental/stubbed
- Portal-root sources are automation stubs until machine-readable endpoints are proven
- At baseline time, `/map` was legacy and `/map-v2` was canonical
- Memory semantic search remains experimental/derivative
- memvid sidecar remains experimental/derivative
- AI review/checks UI remains experimental
- Workspace root `.sln` is a dead/editor artifact
- Frontend e2e tests are still missing as a suite
- Public API boundary tests are partial, not exhaustive

## Proof / Verification Baseline

- Proof freshness and false-claim checks exist and are currently honest enough to be run in CI.
- The current proof artifacts show a pass state for alpha proof gating, but production preflight still fails.
- The repository still contains archived proof history under `artifacts/history/proof/` from the current proof run.

## Immediate Implementation Targets

1. Make production preflight passable with strict config.
2. Lock admin mutations to JWT authority in production.
3. Harden external evidence vault startup/write/hash verification.
4. Make the source registry the real ingestion control plane.
5. Preserve review-gated public publishing while consolidating to a single canonical map route.
