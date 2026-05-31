# JUDGE Repo Baseline — Phase 0 (Historical Snapshot)

> ⚠️ Historical capture from prior repair sessions; not authoritative for current release status.
> Current authoritative proof artifacts are under `artifacts/proof/current/`.

Generated after implementation of all 13 confirmed fixes (sessions JUDGE-main-20 + JUDGE-main-22).

---

## Runtime Versions

| Runtime | Version |
|---------|---------|
| Python  | 3.9.7   |
| Node.js | v24.15.0 |
| npm     | 11.12.1  |

---

## Backend Compile Check

AST-parsed all 294 `.py` files under `backend/app/`:

```
OK: 294  ERRORS: 0
```

No syntax errors.

---

## Alembic Migration Head

Latest migration (head):

```
20260506_0001_add_source_class_to_source_registry.py
```

Total migrations at capture time: 41

---

## Fixes Applied (This Repair Cycle)

| ID | File | Change |
|----|------|--------|
| A1 | `backend/app/api/routes/admin_sources.py` | `source_class: str \| None = None` added to `SourceResponse` |
| B1 | `backend/app/api/routes/admin_sources.py` | `update_source_health()` called after `persist_ingestion_result` in `run_source_now()` |
| A2 | `frontend/lib/sourceContracts.ts` | `SourceTier` union replaced with DB-actual values; colour/label maps updated; `tierColour()` fallback changed to `news_only_context` |
| A3 | `.github/workflows/codeql.yml` | Three step blocks (`Initialize CodeQL`, `Run manual build steps`, `Perform CodeQL Analysis`) re-indented from 4-space to 6-space (correct `steps:` list items) |
| B2 | `backend/app/api/routes/admin_ingestion.py` | `POST /{run_id}/retry` changed from HTTP 200 + `retry_queued: false` to `HTTP 501` |
| B3 | `backend/app/ingestion/web_monitor/crawlee_runner.py` | `_robots_allowed()` except block changed from `return True` to `return False` (fail-closed) |
| B4 | `backend/app/ingestion/source_rules.py` | URL scheme guard added in `check_domain_allowed()` before hostname check; non-http/https schemes return a `RuleViolation` |
| C1 | `backend/app/ingestion/sources/canada_saskatchewan_sources.yaml` | `saskatoon_open_data_portal` `source_class` changed from `machine_ingest` → `portal_reference` |
| C2 | `backend/app/ingestion/source_adapters/crawlee_gov_news.py` | Stub `return []` replaced with `raise NotImplementedError(...)` |
| C2 | `backend/app/ingestion/source_adapters/crawlee_police_release.py` | Stub `return []` replaced with `raise NotImplementedError(...)` |
| D1 | `backend/app/memory/invalidation.py` | `EntityGraphEdge` imported; `invalidate_claim()` now cascades to set `status = "retracted"` on active edges matching `(source_snapshot_id, entity_id)`, then calls `db.flush()` |
| D2 | `backend/pyproject.toml` | `sentence-transformers>=2.7.0` added to `embeddings` optional dependency group |

---

## Known Remaining Stubs

The following adapter files contain legitimate guard `return []` (error paths, not stubs) plus one TODO note. None require immediate action but are tracked here:

| Adapter | Notes |
|---------|-------|
| `canlii_api.py` | Error/empty-page guard returns — expected |
| `ckan_api.py` | Error/empty-page guard returns — expected |
| `federal_court_html.py` | Error/empty-page guard returns — expected |
| `laws_justice_html.py` | Error/empty-page guard returns — expected |
| `saskatoon_csv.py` | Error/empty-page guard returns — expected |
| `saskatoon_police_csv.py` | Error/empty-page guard returns — expected |
| `sk_courts_html.py` | Error/empty-page guard returns — expected |
| `statscan_table.py` | Error/empty-page guard returns — expected |
| `scc_lexum_api.py` | TODO comment: Lexum API bulk/historical not yet implemented |
| `crawlee_gov_news.py` | One guard `return []` (domain violation path) remains — correct |
| `crawlee_police_release.py` | One guard `return []` (domain violation path) remains — correct |

---

## Stale Proof Artifacts

| File | Date | Status |
|------|------|--------|
| `artifacts/proof/FINAL_SUMMARY.md` | 2025-05-03 | Covers prior session; superseded by this baseline |
| `artifacts/proof/JUDGE-22-proof.md` | 2025-05-03 | Covers JUDGE-22 repair; still valid reference |
| `artifacts/proof/truth_hardening_report.md` | 2025-05-03 | Covers prior session; still valid reference |
| `artifacts/proof/final_proof.log` | 2025-05-04 | Last full proof run |
| `artifacts/proof/proof_saskatoon_pipeline.log` | 2025-05-04 | Saskatoon pipeline smoke test |

---

## Next Steps

1. Re-run `scripts/proof_all.sh` to update proof artifacts with current fixes applied.
2. Implement `scc_lexum_api.py` bulk/historical fetch (tracked TODO).
3. Wire up Crawlee runner for `crawlee_gov_news` and `crawlee_police_release` adapters once crawler infrastructure is ready.
4. Consider fixing the 4-space comment lines in `.github/workflows/codeql.yml` (cosmetic — YAML parses correctly with current indentation).
