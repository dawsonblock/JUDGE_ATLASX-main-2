# Canada Data Sources

**Status: alpha — Saskatchewan-first, partial coverage**

---

## Overview

THE-JUDGE is a Canada-first platform. The primary focus is Saskatchewan court records and Canadian public legal data.

---

## Active Machine-Ingest Sources

These sources have working adapters and can be run via `judgectl ingest canlii-sk`:

| Source Key | Name | API | Jurisdiction |
|------------|------|-----|--------------|
| `sk_courts_qb_decisions` | Saskatchewan Court of King's Bench | CanLII API | SK |
| `sk_courts_ca_decisions` | Saskatchewan Court of Appeal | CanLII API | SK |

**API key required**: Register at https://www.canlii.org/en/info/api.html and set `JTA_CANLII_API_KEY`.

---

## Portal-Reference Sources (not auto-ingestable)

These sources are registered in the source registry but cannot be automatically ingested:

| Source | Type | Notes |
|--------|------|-------|
| Saskatchewan Provincial Court | portal_reference | Search via https://www.sasklawcourts.ca/ |
| Federal Court of Canada | portal_reference | Search via https://www.fct-cf.gc.ca/ |
| Supreme Court of Canada | portal_reference | Decisions at https://www.scc-csc.ca/ |
| Statistics Canada crime data | manual_upload | Bulk CSV download required |
| RCMP crime statistics | manual_upload | Annual report download |
| Saskatchewan Legislation | portal_reference | https://publications.saskatchewan.ca/ |

---

## Planned Sources (disabled stubs)

| Source | Status | Blocker |
|--------|--------|---------|
| CanLII all-Canada search | disabled_stub | Rate limit / API quota |
| Manitoba courts | disabled_stub | No public API |
| Alberta courts | disabled_stub | No public API |
| BC courts | disabled_stub | No public API |

---

## CanLII API

CanLII provides a REST API for Canadian legal decisions.

**Database IDs used**:
- `skkb` — Saskatchewan Court of King's Bench
- `skca` — Saskatchewan Court of Appeal
- `skpc` — Saskatchewan Provincial Court (available but not yet in default path)

**Documentation**: https://api.canlii.org/

**Limitations**:
- 100 results per request maximum
- Pagination via offset parameter
- Full text not available via API; only metadata and citation
- API key required; free registration

---

## Legal Notes

- CanLII provides access to Canadian legal decisions under the terms of use at https://www.canlii.org/en/info/termsOfUse.html
- All ingested records are processed through the reviewer queue — no auto-publication
- Court records are not presented as evidence of guilt or criminal findings
- Saskatchewan court metadata is official public record; text is court-owned

---

## Data Quality

| Source | Trust Level | Confidence |
|--------|-------------|------------|
| CanLII / court decisions | official_court_record | High |
| News articles | news_context | Low (context only) |
| Police press releases | portal_reference | Medium (not court-verified) |
| Statistics Canada | government_data | High (aggregate only) |

---

## Alpha Coverage

Current coverage is limited to:
- Saskatchewan court decisions (QB + CA) via CanLII API
- Saskatchewan source registry entries (YAML: `backend/app/ingestion/sources/canada_saskatchewan_sources.yaml`)

Expansion to other provinces requires additional adapters and source registry entries.
