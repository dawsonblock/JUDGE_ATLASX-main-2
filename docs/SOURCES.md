# Source Registry and Data Boundaries

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

The source registry is the authoritative source of truth for ingestion status. Only sources marked as "enabled_runnable" in the source registry are currently active.

Current source registry status for release decisions is exported to:

- `artifacts/proof/source_registry_status.json` (proof_all_current)
- `artifacts/proof/current/source_registry_status.json` (release gate)

JudgeTracker Atlas separates legal decision records from reported crime incident context. Court records verify legal outcomes. Police/open-data records are reported incidents, not proof of guilt or conviction. News is secondary context only.

## Source Tiers

1. Court record, docket, court order, judgment, or appeal decision
2. Official police, prosecutor, corrections, or government release
3. Official city or police open-data portal
4. Reputable news article as secondary context
5. User submission pending moderator review

## Crime Incident Source Targets

Canada:

- Saskatoon Police Crime Mapping
- Toronto Police Public Safety Data Portal
- Calgary Police crime/statistics dashboards
- Vancouver Police open data, if available and licensing permits
- Statistics Canada geospatial crime explorer for aggregate context

United States:

- FBI Crime Data API for national context
- BJS NIBRS estimates API for estimates and trend analysis
- Chicago Data Portal crimes dataset
- Los Angeles Open Data crime dataset
- NYC Open Data complaint data, if licensing permits

## Crime Layer Rules

- Use generalized public-area coordinates only.
- Do not expose exact private locations, suspect names, victim details, private residences, DOBs, family details, or person profiles.
- Do not visually connect crime dots and judge/court dots unless a court record, official docket, police release, or official outcome document supports that connection.
- Treat reported incidents as mutable records that may change due to late reporting, reclassification, correction, or unfounded reports.
- Manual/import adapters are the only Phase 1 ingestion path. No aggressive scraping or terms-of-service bypassing is implemented.

## Legal Decision Rules

- CourtListener/RECAP remains the first court-data integration.
- PACER-direct access is a later option when RECAP does not contain required records.
- News cannot create a verified legal outcome by itself.
- Repeat-offender wording must remain indicator-based unless a source explicitly supports the legal fact.

## Canadian Law Source Status

Justice Canada law ingestion is implemented as a reviewed legal-context pipeline.

### Canonical machine-ingest source

- source_key: `justice_canada_laws_xml`
- base_url: `https://laws-lois.justice.gc.ca/eng/XML/Legis.xml`
- parser: `laws_justice_xml`
- parser_version: `justice_laws_xml_v1`
- source_class: `machine_ingest`
- requires_manual_review: `true`
- public_publish_default: `false`

### Deprecated compatibility key

- `canada_justice_laws` is retained as a compatibility alias entry only.
- It is non-runnable (`source_class=disabled_stub`, `automation_status=disabled_stub`).
- Runtime ingestion must use `justice_canada_laws_xml`.

### Justice GitHub repositories

- `justice_canada_laws_xml_repo`: manual reference for fixtures/examples only.
- `justice_canada_lims_xml_dtd`: manual schema reference only.
- `justice_canada_otto_reference`: architecture reference only.

Otto remains reference-only due to runtime-boundary and licensing constraints. It is not imported or vendored into runtime code.

### Validation level

Justice XML validation is structural fail-closed validation. This does not claim complete DTD validation coverage.

## Source Classes

Each source registry entry carries a `source_class` that determines whether automated ingestion is eligible. Only `machine_ingest` sources can be enabled or triggered via the admin API; all other classes are reference or stub entries only.

| `source_class` | Description | Automated ingestion |
|----------------|-------------|---------------------|
| `machine_ingest` | Automated HTTP/CSV adapter with a working fetcher | ✅ Eligible |
| `portal_reference` | A known public portal that requires human-driven import | ❌ Not eligible |
| `manual_reference` | A data source managed by manual CSV upload | ❌ Not eligible |
| `disabled_stub` | Placeholder entry intentionally kept inactive | ❌ Not eligible |
| `archive_only` | Historical snapshot — no ongoing ingestion | ❌ Not eligible |
| `research_scope_only` | In-scope for research; ingestion not yet implemented | ❌ Not eligible |

Attempting to enable or run a non-`machine_ingest` source via `POST /api/admin/sources/{id}/enable` or `POST /api/admin/sources/{id}/run` returns `HTTP 422` with a remediation hint.

The admin UI (`/admin/sources`) displays the source class label and disables the Enable button with an explanatory tooltip for non-eligible sources.

## Proof Commands

Use current-run proofs only:

- `backend/.venv/bin/python scripts/release_gate.py`
- `bash scripts/proof_all_current.sh`

Do not claim source readiness from historical proof directories.

## Review Workflow

New ingested legal events, legal sources, and crime incidents enter `pending_review` by default. Public endpoints only show records with public review statuses: `verified_court_record`, `official_police_open_data_report`, `news_only_context`, or `corrected`. Statuses `pending_review`, `disputed`, `rejected`, and `removed_from_public` are never exposed on public endpoints.

Review decisions are auditable through `evidence_reviews` and should capture:

- previous and new status
- reviewer
- reviewed date
- notes, correction notes, or dispute notes
- public visibility decision

Rejected and removed records should remain in the database for auditability, but they should not appear in public maps, timelines, or source lists.

## Web Monitoring (Crawlee)

Judge Atlas uses Crawlee for **controlled source monitoring only** — not open-ended web crawling.

### Purpose

Monitor known public pages for:
- Court announcement pages
- Police media release pages
- City/open data pages without APIs
- RSS/news feeds for source snapshots

### Safety Rules

1. **Strict allowlists** — Only domains explicitly configured (e.g., `saskatoonpolice.ca`)
2. **Disabled by default** — All targets require explicit admin enablement
3. **Request limits** — Max 100 requests per run (default: 25)
4. **Depth limits** — Max crawl depth 3 (default: 1)
5. **Low concurrency** — Max 5 concurrent requests (default: 2)
6. **Robots.txt compliance** — Enabled by default (intent; Crawlee does not expose per-crawl enforcement at runtime)
7. **Never auto-publish** — All crawled content → `pending_review`
8. **Low confidence** — Max 0.5 confidence for crawled content
9. **Evidence snapshots** — Store source_url, fetched_at, content_hash, raw_content
10. **Pass through safety gates** — source_verifier, public_safety, publish_rules

### Flow

```
known source target → Crawlee fetch → snapshot → extractor → candidate item
→ pending_review → publication gate → public map (after approval only)
```

### Extractors

- `police_release_index/detail` — Police news releases
- `court_news_index/detail` — Court announcement pages
- `city_open_data_landing_page` — Open data portals
- `rss_or_news_listing` — RSS feeds

All extractors flag:
- Private address patterns
- Person names (for review)
- Low confidence scores

### CLI Usage

```bash
# List targets
python scripts/run_web_monitor.py --list

# Run specific target
python scripts/run_web_monitor.py --target saskatoon_police_news --limit 25

# Dry run (config check only)
python scripts/run_web_monitor.py --target saskatoon_police_news --dry-run
```

### Example Target (Disabled by Default)

```python
{
  "name": "Saskatoon Police News Releases",
  "source_type": "official_police_media",
  "base_url": "https://saskatoonpolice.ca",
  "allowed_domains": ["saskatoonpolice.ca"],
  "start_urls": ["https://saskatoonpolice.ca/news/"],
  "max_depth": 1,
  "max_requests": 25,
  "concurrency": 2,
  "source_tier": "official_police_open_data",
  "enabled": false,  // Must enable in admin panel
  "extractor_type": "police_release_index"
}
```

### Do NOT Use Crawlee For

- Open-ended web crawling
- Scraping entire websites
- Bypassing terms of service
- Collecting private social media profiles
- Collecting personal addresses or contact info
- Mass downloading documents
- Any use that violates robots.txt or site terms

### Data Retention

Raw HTML snapshots stored for provenance (up to configured retention). Extracted text limited to 2000 chars. Source URLs and content hashes retained permanently for audit trail.

## External Evidence Storage

By default, source snapshots are stored in the database (`raw_content` field). For large-scale deployments or archival requirements, you can configure external filesystem storage.

### Setup

Set the environment variable:

```bash
export JTA_EVIDENCE_STORE_ROOT=/path/to/evidence/store
```

Or in `.env`:

```
JTA_EVIDENCE_STORE_ROOT=/Volumes/ExternalDrive/JudgeAtlasEvidence
```

### Storage Structure

When external storage is enabled, snapshots are stored at:

```
{JTA_EVIDENCE_STORE_ROOT}/snapshots/sha256/{aa}/{bb}/{full_hash}.bin
```

Where:
- `aa` = first 2 characters of SHA256 hash
- `bb` = next 2 characters of SHA256 hash
- Content is addressed by SHA256 hash for deduplication

### Database Fields

When using external storage:
- `storage_backend` = "filesystem"
- `storage_path` = relative path (e.g., `snapshots/sha256/ab/cd/abcdef1234...89.bin`)
- `raw_content` = NULL (content stored externally)
- `content_hash` = SHA256 of content (verified on write)
- `extracted_text` = still stored in DB (for search/audit)

When NOT using external storage:
- `storage_backend` = "db"
- `storage_path` = NULL
- `raw_content` = actual content (limited to ~10KB)

### Fallback Behavior

If external storage fails (e.g., disk full, permissions error), the system falls back to DB storage and logs the error. No data is lost.

### External Hard Drive Setup Example

```bash
# 1. Mount external drive
mkdir -p /mnt/evidence-store
mount /dev/sdb1 /mnt/evidence-store

# 2. Create directory for Judge Atlas
mkdir -p /mnt/evidence-store/judge-atlas
chown $USER:$USER /mnt/evidence-store/judge-atlas

# 3. Set environment variable
export JTA_EVIDENCE_STORE_ROOT=/mnt/evidence-store/judge-atlas

# 4. Verify
python -c "from app.services.evidence_store import EvidenceStore; \
           print(EvidenceStore().enabled)"  # Should print: True
```

### Backup Considerations

- **External storage**: Backup the directory structure along with the database
- **Content-addressed**: Files are immutable (named by hash), so incremental backups work well
- **Database**: Must be backed up with external storage to maintain integrity
- **Restoration**: If external storage is lost but DB remains, records will show `storage_backend="filesystem"` but content will be unavailable
