# Runtime Boundaries

Date: 2026-05-06

## Authority rule

JUDGE-main is the only authoritative runtime. It owns the database schema, API, source registry, evidence snapshots, review workflow, frontend, CLI, Docker stack, and deployment configuration.

**Mechanical enforcement:** `backend/scripts/check_repo_boundaries.py` runs in CI (and can be run locally) to verify these boundaries are upheld. `backend/scripts/check_no_direct_ingestion_network_clients.py` enforces the safe-fetch network boundary. Run both via `bash scripts/run_enforcement_proof.sh`.

## Reference repositories

| Repository | Allowed use | Disallowed use |
| --- | --- | --- |
| `CLI-Anything-main` | Study command UX, JSON envelopes, subprocess testing, and harness documentation patterns. | Runtime import, vendoring, copying broad architecture without tests, or claiming its coverage applies to JUDGE. |
| `memvid-Human--main-main` | Optional export/search sidecar for historical evidence snapshots after JSONL export. | Authoritative storage, replacing Postgres/evidence snapshots, or mutating canonical records. |

## Storage authority

1. Postgres/PostGIS is the canonical relational and geospatial store.
2. Evidence snapshots are canonical immutable source artifacts.
3. JSONL exports are derived artifacts.
4. memvid `.mv2` archives, if generated, are derived search artifacts only.

## AI boundary

AI and rule-based analysis modules may classify, summarize, suggest duplicates, detect anomalies, and assist reviewers. They must never assign guilt, convict, fabricate evidence, create unsupported legal claims, or publish records automatically.

## Source boundary

Only sources classified as `machine_ingest` may run automated ingestion. `manual_upload`, `portal_reference`, and `disabled_stub` sources must not fetch or parse as automated pipelines.
