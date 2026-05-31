# TRUTH AUDIT — Phase 0 Cleanup

## Current Run Advisory (2026-05-11)

This file records a historical phase-0 cleanup snapshot. Current release claims must come from current-run proof artifacts under `artifacts/proof/` (especially `release_readiness.md`, `backend_grouped_tests_summary.log`, and `source_registry_status.json`).

Do not treat historical test totals in this document as current release evidence.

**Date:** 2026-05-04  
**Commit scope:** phase-0 truth audit, dead model cleanup, CanLII export

---

## Route Audit

All four "ambiguous" route files are **distinct and necessary**. No consolidation needed.

| File | Router prefix | Purpose |
|------|--------------|---------|
| `admin_ingest.py` | `/api/admin/ingest` | Trigger source ingestion (gdelt, chicago, toronto, saskatoon, la, statscan, fbi) |
| `admin_ingestion.py` | `/api/admin/ingestion-runs` | Monitor ingestion run history / observability |
| `ingestion.py` | (hardcoded paths) | Manual CSV import + CourtListener trigger |
| `chat.py` | `/api/chat` | Evidence chat Q&A |

---

## Dead Model Audit

### Removed (genuinely dead — no routes, services, or tests)

| Model | Table | Reason removed |
|-------|-------|---------------|
| `Topic` | `topics` | No routes, no services, no test references |
| `EventTopic` | `event_topics` | FK to `topics`; same dead status |

**Migration:** `20260504_0009_remove_dead_models.py` drops `event_topics` then `topics`.

### Retained (incorrectly flagged as dead in prior audit)

| Model | Table | Reason kept |
|-------|-------|------------|
| `EvidenceReview` | `evidence_reviews` | Actively used in `admin_review.py` (8 references) and `test_api.py` |

---

## CanLII Export Gap (Fixed)

`CanLIIAdapter` was created in the prior session but was not exported from  
`backend/app/ingestion/laws/__init__.py`. Fixed: adapter is now in `__all__`.

---

## Test Result

All **858 tests pass** after Phase 0 changes.
