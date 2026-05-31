# Source Registry Overview

JUDGE uses a **source registry** to track every data source that the ingestion
pipeline may fetch from. Each source is an entry in the `SourceRegistry` table
and has a corresponding YAML definition under
`backend/app/ingestion/sources/`.

---

## YAML definitions

| File | Jurisdiction | Sources |
|------|-------------|---------|
| `canada_saskatchewan_sources.yaml` | SK / CA | 16 |

All YAML files are loaded at startup by `backend/app/seed/source_registry.py`
and merged with any existing database rows (upsert by `source_key`).

---

## Source fields

| Field | Description |
|-------|-------------|
| `source_key` | Stable slug, e.g. `saskatoon_open_data_crime` |
| `name` | Human-readable label |
| `source_type` | `official_open_data`, `news_context`, `official_court_record`, … |
| `jurisdiction` | ISO-3166-2 code, e.g. `CA-SK` |
| `category` | Logical grouping (`crime_statistics`, `court_records`, …) |
| `priority` | Ingestion priority (1 = highest) |
| `enabled_default` | Whether the source is active immediately after seed |
| `public_record_authority` | Authority tier — controls what record types may be created |
| `base_url` | Root URL for the adapter |
| `allowed_domains` | JSON list of domains the adapter may contact |
| `refresh_interval_minutes` | How often the scheduler should call this source |
| `parser` | Key into `ADAPTER_REGISTRY` (see [parser keys](parser-keys.md)) |
| `creates` | JSON list of record types this source may produce |
| `public_publish_default` | If `true`, records may be published without review (subject to rules) |
| `terms_url` | URL to the data source's terms of use |
| `admin_notes` | Internal notes shown in the admin UI |
| `auto_publish_enabled` | Overrides publish gate; `false` forces manual review |
| `requires_manual_review` | If `true`, all records go through the review queue |

---

## Adapter dispatch

When the scheduler (or admin) triggers a source run, the backend:

1. Loads the `SourceRegistry` row by `source_key`.
2. Looks up `source.parser` in `ADAPTER_REGISTRY`.
3. Instantiates the adapter with `(source_key, base_url, allowed_domains, public_record_authority)`.
4. Calls `adapter.run()` which returns an `IngestionResult`.

See [parser-keys.md](parser-keys.md) for the full adapter map.

---

## Safety guarantees

All ingestion operations are gated by `source_rules.py`. No record is written
or published without passing:

- **Domain allow-list** – adapter may only contact domains in `allowed_domains`.
- **Record-type gate** – authority tier restricts which model types may be created.
- **Publish gate** – auto-publish requires eligible authority + both flags `true`.

See [safety-rules.md](safety-rules.md) for details.
