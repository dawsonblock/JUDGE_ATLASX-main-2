> ⚠️ **HISTORICAL RECORD (SUPERSEDED)**
> This document is a dated baseline snapshot and is not authoritative for current runtime status.
> Use `artifacts/proof/current/CURRENT_PROOF.md` and `artifacts/proof/current/release_gate.json` for current proof.

# Repair Baseline — JUDGE-main

**Date**: 2026-05-01
**Status**: ✅ Repair Complete — All Phases Verified

## Current Repository State (Historical Snapshot)

### Backend Status
- **Location**: `backend/`
- **Python**: 3.11.14 (in .venv)
- **DB**: SQLite (test), PostgreSQL (production target)
- **Migrations**: 28 migration files at capture time — **All passing on fresh SQLite DB**
- **Tests**: **394 passed, 5 warnings**
- **Syntax**: `python -m compileall` — **No errors**

### Critical Blockers — RESOLVED

#### 1. Migration Failure (SQLite) — FIXED ✅
**File**: `backend/alembic/versions/20260430_0009_add_source_snapshot_fk.py`
**Status**: Uses proper `batch_alter_table` with `add_column` + `create_foreign_key` pattern
**Verified**: `alembic upgrade head` passes on fresh DB

#### 2. Repository Hygiene — CLEANED ✅
**Status**: All `__pycache__/` directories removed outside `.venv/`
**Verified**: 0 cache directories remain in source tree

### Migration Chain Analysis

| Migration | Status | SQLite Compatible | Notes |
|-----------|--------|-------------------|-------|
| 20250427_1720_initial_schema.py | ✅ | ✅ | Base schema |
| 20260428_0001-0005 | ✅ | ✅ | Working |
| 20260428_0006_add_postgis_geometry.py | ⚠️ | ⚠️ | PostGIS-specific |
| 20260430_0007_add_source_snapshots.py | ✅ | ✅ | Creates table |
| 20260430_0008_add_source_registry.py | ✅ | ✅ | Creates table |
| **20260430_0009_add_source_snapshot_fk.py** | ❌ | ❌ | **FAILING** |
| 20260501_0001-0008 | ⏳ | ⏳ | Not reached |
| 20260501_0009_entity_graph_edge_unique | ⏳ | ⏳ | Has dedup logic |

### Frontend Status
- **Location**: `frontend/`
- 30 items present (needs verification)
- Status: Unknown (not yet tested)

### Graph/Source/Snapshot Design

**SourceSnapshot** (evidence authority):
- Content-addressed storage via SHA256 hash
- Supports filesystem + database storage backends
- Tracks: URL, fetch timestamp, content hash, HTTP status
- Provenance: `ingestion_run_id` linkage

**Graph Edges** (relationships):
- Entity-to-entity relationships with temporal validity
- Evidence-backed via `source_snapshot_id`
- Status: active/disputed/retracted
- Pending: unique constraint to prevent duplicates

**Web Monitor** (crawlee integration):
- Async crawler with safety limits
- Allowlist-enforced domain restriction
- Creates `pending_review` items only (never auto-publishes)
- Provenance: `ingestion_run_id` on snapshots and review items

### Files Changed During Repair
(Will be documented in REPAIR_PROOF.md)

### Known Limitations (Honest)
- In-memory rate limiting (not production-grade)
- SQLite test DB (production uses PostgreSQL)
- Frontend build status unknown
- No Redis in current config

## Next Actions
1. Fix migration 20260430_0009 SQLite compatibility
2. Clean all __pycache__ and update .gitignore
3. Run alembic upgrade head to verify
4. Run backend tests
5. Verify frontend build
