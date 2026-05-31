# Source Enablement Checklist (Disabled-Ready Sources)

This checklist is for enablement planning only. It does not auto-enable any source.

Current verified counts must remain unchanged during this checklist phase:

- total_sources: 26
- machine_ingest_sources: 8
- runnable_now: 2
- enable_ready: 5
- deprecated: 3
- machine_ready_disabled: 5
- adapter_missing: 16

All five sources below are intentionally disabled in alpha and require explicit governance sign-off before enablement.

## Global Preconditions (Required For Any Enablement)

- Confirm legal terms of use permit machine ingestion and local evidence retention.
- Confirm source endpoint availability and stable fetch behavior over multiple runs.
- Run adapter contract tests and source-specific replay/fixture tests.
- Run one non-publishing dry ingestion via `POST /api/admin/sources/{source_key}/dry-run`.
- Confirm dry-run indicates expected evidence snapshot behavior before any real run.
- Verify review queue payload quality and citation/evidence binding quality.
- Regenerate proof artifacts and verify source registry truth table consistency.
- Obtain documented approval from release/security/governance owners.
- Enable exactly one source at a time, never as a bulk toggle.

## Source-Specific Checklist

### `scc_decisions`

- [ ] Endpoint reachable and stable over repeated fetch windows.
- [ ] Terms reviewed for ingest/caching/republication constraints.
- [ ] Adapter contract + replay tests green.
- [ ] Dry run evidence snapshot captured and indexed.
- [ ] Governance approval documented for alpha scope expansion.

**Implementation Details:**
- Adapter: `backend/app/ingestion/source_adapters/scc_lexum_api.py`
- Test files:
  - `backend/app/tests/test_adapter_evidence_contract.py` (TestSCCLexumApiAdapterContract)
  - `backend/app/tests/test_ingestion_safe_fetch_boundary.py` (test_scc_lexum_adapter_uses_injected_fetcher)
- Fixture: `backend/app/tests/fixtures/sources/scc_feed.xml`
- Config flags: None (uses source registry enablement)

### `federal_court_canada`

- [ ] Endpoint reachable and stable over repeated fetch windows.
- [ ] Terms reviewed for ingest/caching/republication constraints.
- [ ] Adapter contract + replay tests green.
- [ ] Dry run evidence snapshot captured and indexed.
- [ ] Governance approval documented for alpha scope expansion.

**Implementation Details:**
- Adapter: `backend/app/ingestion/source_adapters/federal_court_html.py`
- Test files:
  - `backend/app/tests/test_federal_court_html_adapter.py`
- Fixture: `backend/app/tests/fixtures/sources/federal_court_index.html`
- Config flags: None (uses source registry enablement)

### `sk_courts_qb_decisions`

- [ ] Endpoint reachable and stable over repeated fetch windows.
- [ ] Terms reviewed for ingest/caching/republication constraints.
- [ ] Adapter contract + replay tests green.
- [ ] Dry run evidence snapshot captured and indexed.
- [ ] Governance approval documented for alpha scope expansion.

**Implementation Details:**
- Adapter: `backend/app/ingestion/source_adapters/canlii_api.py`
- Test files:
  - `backend/app/tests/test_canlii_sk_ingest.py`
  - `backend/app/tests/test_ingestion_safe_fetch_boundary.py` (test_sk_courts_adapter_uses_injected_fetcher)
  - `backend/app/tests/test_adapter_evidence_contract.py` (TestCanLIIApiAdapterSKContract)
- Fixture: `backend/app/tests/fixtures/sources/sk_courts_qb_decisions/sample.json`
- Config flags: None (uses source registry enablement)

### `sk_courts_ca_decisions`

- [ ] Endpoint reachable and stable over repeated fetch windows.
- [ ] Terms reviewed for ingest/caching/republication constraints.
- [ ] Adapter contract + replay tests green.
- [ ] Dry run evidence snapshot captured and indexed.
- [ ] Governance approval documented for alpha scope expansion.

**Implementation Details:**
- Adapter: `backend/app/ingestion/source_adapters/canlii_api.py`
- Test files:
  - `backend/app/tests/test_canlii_sk_ingest.py`
  - `backend/app/tests/test_adapter_evidence_contract.py` (TestCanLIIApiAdapterSKContract)
- Fixture: `backend/app/tests/fixtures/sources/sk_courts_ca_decisions/sample.json`
- Config flags: None (uses source registry enablement)

### `sk_legislature_hansard`

- [ ] Endpoint reachable and stable over repeated fetch windows.
- [ ] Terms reviewed for ingest/caching/republication constraints.
- [ ] Adapter contract + replay tests green.
- [ ] Dry run evidence snapshot captured and indexed.
- [ ] Governance approval documented for alpha scope expansion.

**Implementation Details:**
- Adapter: `backend/app/ingestion/source_adapters/sk_legislature_html.py`
- Test files:
  - `backend/app/tests/test_canadian_laws.py`
- Fixture: `backend/app/tests/fixtures/sources/sk_legislature_hansard.html`
- Config flags: None (uses source registry enablement)

## Non-Goals (Alpha Integrity)

- No production-readiness claim is implied by this checklist.
- No source is enabled automatically.
- Evidence, review, and publication guardrails remain unchanged.
