# Source Enablement Checklist

This checklist documents the concrete test files, proof artifacts, and acceptance criteria for each ingestion source. Before enabling a source in production, ensure all items in its checklist are satisfied.

## Canada-First Sources (Saskatchewan and Federal Canada)

### saskatoon_open_data_crime
- **Test File**: `app/tests/test_saskatoon_ingest_endpoint.py`
- **Adapter**: `app/ingestion/source_adapters/saskatoon_csv.py`
- **Config Flags**: `JTA_LOCAL_FEEDS_ENABLED=true`
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - CSV upload endpoint returns 200 with valid Saskatoon police CSV
  - Records are persisted to database with correct external IDs
  - Ingestion run is audited in mutation log
  - Source registry status reflects successful runs
- **Proof Artifacts**:
  - Ingestion run record in database
  - Mutation audit log entry
  - Source registry truth table entry

### saskatoon_police_open_data
- **Test File**: `app/tests/test_saskatoon_pipeline_wiring.py`
- **Adapter**: `app/ingestion/source_adapters/saskatoon_police_csv.py`
- **Config Flags**: `JTA_LOCAL_FEEDS_ENABLED=true`
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - CSV adapter parses police open data format correctly
  - External ID deduplication prevents duplicate records
  - Snapshot is preserved if evidence store is configured
- **Proof Artifacts**:
  - Ingestion run record
  - Snapshot preservation record (if evidence store enabled)
  - Source registry truth table entry

### web_monitor_saskatoon_police_news
- **Test File**: `app/tests/test_crawlee_runner.py` (general web monitor tests)
- **Adapter**: `app/ingestion/source_adapters/crawlee_police_release.py`
- **Config Flags**: `JTA_LOCAL_FEEDS_ENABLED=true`
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Web monitor successfully crawls police news pages
  - HTML content is extracted and normalized
  - Safe fetch is used (no direct network clients)
  - Egress proxy is used in production
- **Proof Artifacts**:
  - Crawl run record
  - Evidence snapshots for fetched pages
  - Source registry truth table entry

### sk_courts_qb_decisions
- **Test Files**:
  - `app/tests/test_canlii_sk_ingest.py`
  - `app/tests/test_adapter_evidence_contract.py` (TestCanLIIApiAdapterSKContract)
  - `app/tests/test_ingestion_safe_fetch_boundary.py` (test_sk_courts_adapter_uses_injected_fetcher)
- **Adapter**: `app/ingestion/source_adapters/canlii_api.py`
- **Fixture**: `app/tests/fixtures/sources/sk_courts_qb_decisions/sample.json`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - CanLII `skkb` decisions are fetched and parsed correctly
  - Evidence snapshot bytes and fetch metadata are preserved
  - Output remains review-gated (no auto-publish)
- **Proof Artifacts**:
  - Ingestion run record
  - ReviewItem records for QB decisions
  - Source registry truth table entry

### sk_courts_ca_decisions
- **Test Files**:
  - `app/tests/test_canlii_sk_ingest.py`
  - `app/tests/test_adapter_evidence_contract.py` (TestCanLIIApiAdapterSKContract)
- **Adapter**: `app/ingestion/source_adapters/canlii_api.py` (same adapter; `skca` database)
- **Fixture**: `app/tests/fixtures/sources/sk_courts_ca_decisions/sample.json`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - CanLII `skca` decisions are fetched and parsed correctly
  - Evidence snapshot bytes and fetch metadata are preserved
  - Output remains review-gated (no auto-publish)
- **Proof Artifacts**:
  - Ingestion run record
  - ReviewItem records for CA decisions
  - Source registry truth table entry

### statscan_ccjs_crime_sk
- **Test File**: `app/tests/test_statscan_table_adapter_boundary.py`
- **Adapter**: `app/ingestion/source_adapters/statscan_table.py`
- **Config Flags**: `JTA_STATSCAN_ENABLED=true`
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - StatsCan ZIP files are downloaded and extracted
  - CSV tables are parsed with correct column mapping
  - Saskatchewan-specific crime statistics are extracted
- **Proof Artifacts**:
  - Ingestion run record
  - Raw snapshot preserved (ZIP + CSV)
  - Source registry truth table entry

### statscan_ucr_national
- **Test File**: `app/tests/test_statscan_table_adapter_boundary.py`
- **Adapter**: `app/ingestion/source_adapters/statscan_table.py`
- **Config Flags**: `JTA_STATSCAN_ENABLED=true`
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - National UCR statistics are ingested
  - Data is normalized to match Saskatchewan schema
- **Proof Artifacts**:
  - Ingestion run record
  - Raw snapshot preserved
  - Source registry truth table entry

### canlii_sk
- **Test File**: `app/tests/test_canlii_sk_ingest.py`
- **Adapter**: `app/ingestion/source_adapters/canlii_api.py`
- **Config Flags**: `JTA_CANLII_API_KEY` (required)
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - CanLII API key is valid
  - Saskatchewan cases are fetched via API
  - API rate limits are respected
- **Proof Artifacts**:
  - Ingestion run record
  - API response logs
  - Source registry truth table entry

### federal_court_canada
- **Test File**: `app/tests/test_federal_court_html_adapter.py`
- **Adapter**: `app/ingestion/source_adapters/federal_court_html.py`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Federal court decisions are parsed from HTML
  - Federal case metadata is extracted
- **Proof Artifacts**:
  - Ingestion run record
  - Entity records for federal cases
  - Source registry truth table entry

### scc_decisions
- **Test File**: `app/tests/test_justice_laws_phase4.py` (Lexum API tests)
- **Adapter**: `app/ingestion/source_adapters/scc_lexum_api.py`
- **Config Flags**: `JTA_LEXUM_API_KEY` (required)
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Lexum API key is valid
  - Supreme Court decisions are fetched
  - Bilingual content is handled correctly
- **Proof Artifacts**:
  - Ingestion run record
  - API response logs
  - Source registry truth table entry

### sk_justice_ministry
- **Test File**: `app/tests/test_crawlee_gov_news_adapter.py`
- **Adapter**: `app/ingestion/source_adapters/crawlee_gov_news.py`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Ministry news releases are crawled
  - Content is extracted and normalized
- **Proof Artifacts**:
  - Crawl run record
  - Evidence snapshots
  - Source registry truth table entry

### sk_legislature_hansard
- **Test File**: `app/tests/test_crawlee_gov_news_adapter.py` (general gov adapter)
- **Adapter**: `app/ingestion/source_adapters/sk_legislature_html.py`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Hansard transcripts are parsed
  - Speaker attribution is preserved
- **Proof Artifacts**:
  - Ingestion run record
  - Entity records for legislative sessions
  - Source registry truth table entry

### canada_open_data_crime
- **Test File**: `app/tests/test_crawlee_adapter_stubs.py` (CKAN API tests)
- **Adapter**: `app/ingestion/source_adapters/ckan_api.py`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Canada Open Data CKAN API is queried
  - Crime datasets are identified and downloaded
- **Proof Artifacts**:
  - Ingestion run record
  - Raw dataset snapshots
  - Source registry truth table entry

### rcmp_sk_news
- **Test File**: `app/tests/test_crawlee_gov_news_adapter.py`
- **Adapter**: `app/ingestion/source_adapters/crawlee_gov_news.py`
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - RCMP Saskatchewan news releases are crawled
  - Content is extracted and normalized
- **Proof Artifacts**:
  - Crawl run record
  - Evidence snapshots
  - Source registry truth table entry

### justice_canada_laws_xml
- **Test File**: `app/tests/test_laws_justice_xml_adapter.py`
- **Adapter**: `app/ingestion/source_adapters/laws_justice_xml.py`
- **Config Flags**: `JTA_LAWS_XML_TARGET_IDS` (default: C-46)
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Justice Canada XML laws are fetched
  - XML is parsed into structured legal instrument data
  - Law sections and amendments are tracked
- **Proof Artifacts**:
  - Ingestion run record
  - Raw XML snapshot
  - Legal instrument entity records
  - Source registry truth table entry

### saskatoon_open_data_portal
- **Test File**: `app/tests/test_crawlee_adapter_stubs.py` (general portal tests)
- **Adapter**: `app/ingestion/source_adapters/ckan_api.py` (Saskatoon uses CKAN)
- **Config Flags**: None
- **Source Registry**: Must be active in `canada_saskatchewan_sources.yaml`
- **Acceptance Criteria**:
  - Saskatoon Open Data portal is queried
  - Dataset metadata is extracted
- **Proof Artifacts**:
  - Ingestion run record
  - Dataset metadata records
  - Source registry truth table entry

### courtlistener_bulk
- **Test File**: `app/tests/test_admin_ingestion.py` (bulk import tests)
- **Adapter**: `app/ingestion/courtlistener_bulk_normalizer.py`
- **Config Flags**: `JTA_COURTLISTENER_BULK_DATA_DIR`, `JTA_COURTLISTENER_BULK_SNAPSHOT_DATE`
- **Source Registry**: Not in Saskatchewan YAML (U.S. federal courts)
- **Acceptance Criteria**:
  - Bulk CSV files are normalized into database
  - Courts, people, dockets, opinions are linked
  - Batch processing handles large files
- **Proof Artifacts**:
  - Bulk run records in database
  - Normalized entity records
  - Source registry truth table entry (if enabled)
- **Note**: This is a legacy U.S. source, disabled by default. Enable via `JTA_ENABLE_LEGACY_US_INGEST_ROUTES=true`.

## Legacy U.S. Sources (Disabled by Default)

The following sources are in `LEGACY_SOURCE_ALIASES` but map to `None`, meaning they are explicitly disabled:

- **chicago_crime**: Chicago Data Portal (U.S.) - disabled
- **toronto_crime**: Toronto Police Service (Canada - legacy CSV) - disabled
- **la_crime**: Los Angeles Open Data (U.S.) - disabled
- **fbi_crime**: FBI Crime Data (U.S.) - disabled

These sources are not part of the Canada-first strategy and have been moved to `admin_legacy_ingest.py`. To use them, set `JTA_ENABLE_LEGACY_US_INGEST_ROUTES=true` (not recommended for production).

## General Enablement Requirements

All sources must satisfy these general requirements before enablement:

1. **Source Registry Entry**: Source must be defined in `canada_saskatchewan_sources.yaml` with:
   - `source_key` matching canonical key
   - `display_name` and `description`
   - `enabled: true`
   - `automation_status` (one of: `active`, `inactive`, `blocked`, `experimental`)

2. **Adapter Implementation**: Source must have a working adapter in `app/ingestion/source_adapters/` that:
   - Implements the adapter contract
   - Handles errors gracefully
   - Preserves raw snapshots (if evidence store enabled)
   - Uses safe_fetch for network requests

3. **Test Coverage**: Source must have at least one test file in `app/tests/` that:
   - Tests the adapter with real or mock data
   - Validates external ID generation
   - Checks entity creation
   - Verifies source registry integration

4. **Proof Artifacts**: After a successful run, the following must be verifiable:
   - Ingestion run record in database with `state=completed`
   - Entity records created with correct external IDs
   - Mutation audit log entry (if manual ingestion)
   - Source registry truth table shows last run timestamp

5. **Configuration**: Required config flags must be set:
   - API keys (if applicable)
   - Feature flags (e.g., `JTA_LOCAL_FEEDS_ENABLED`)
   - Evidence store configuration (if preserving snapshots)

## Source Enablement Workflow

To enable a new source or re-enable a disabled source:

1. **Review Checklist**: Complete all items in the source's checklist above
2. **Run Tests**: Execute the source's test file and ensure all tests pass
3. **Manual Test Run**: Use admin ingestion endpoint to trigger a manual run
4. **Verify Proof Artifacts**: Check database for run records, entities, and audit logs
5. **Update Source Registry**: Set `enabled: true` in `canada_saskatchewan_sources.yaml`
6. **Regenerate Proof**: Run `scripts/release_gate.py` to update source registry truth table
7. **Commit Changes**: Commit source registry YAML and proof artifacts

## Blocking Criteria

A source will be blocked from enablement if:

- No test file exists or tests fail
- Adapter raises NotImplementedError or has TODO comments
- Source is marked as `automation_status: blocked` in registry
- Required config flags are missing or invalid
- Source is in legacy U.S. list and `JTA_ENABLE_LEGACY_US_INGEST_ROUTES=false`
- Source has no source registry entry
