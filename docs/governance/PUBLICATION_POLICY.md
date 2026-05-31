# Publication Policy

JUDGE_ATLASX separates internal review workflow from public entity publication.

## Truth Statement

JUDGE_ATLASX is an evidence-governed Canadian legal intelligence alpha. Evidence is authoritative. AI and memory outputs are derivative only. All public-facing data requires human review approval and must be linked to an evidence snapshot. This is an alpha release, not a production legal authority.

The source registry is the authoritative source of truth for ingestion status. Only sources marked as "enabled_runnable" in the source registry are currently active.

## Status Model

`ReviewItem.status` is an internal workflow field. `approved` means approved for promotion, drafting, or further human review. It is not a public publication status.

Public entities use `review_status`:

- `pending_review`: non-public
- `verified_court_record`: public-eligible with evidence
- `official_police_open_data_report`: public-eligible with evidence
- `official_statistics_aggregate`: public-eligible for aggregate/statistical records
- `news_only_context`: non-public by default; context-only, not an accusation or map fact
- `corrected`: public-eligible only while evidence remains valid
- `disputed`: non-public
- `rejected`: non-public
- `removed_from_public`: non-public

## Evidence Anchors

Publication is decided by `backend/app/policies/publication_policy.py`.

- `Event`: must have an `EventSource` linked to a `LegalSource` with `url` and `url_hash`.
- `CrimeIncident`: must have `source_snapshot_id`; the `SourceSnapshot` must exist and have `content_hash`.
- `LegalSource`: must have non-empty `url` and `url_hash`.
- `LegalInstrument`: must have `raw_snapshot_id`; the `SourceSnapshot` must exist and have `content_hash`.
- `RelationshipEvidence`: must have `evidence_snapshot_id`; the `SourceSnapshot` must exist and have `content_hash`.

## Publication Flow

AI review and adapter ingestion create pending private records. Public visibility may only be set by an admin/reviewer decision path that calls the canonical policy.

Rejected, disputed, pending, and removed records clear public visibility. Corrections remain public only if the evidence gate still passes.

## Map Safety

The public map is backend-authoritative. It prefilters by public visibility, public review status, coordinates, and precision, then applies policy before serialization. Records with exact/private address precision are omitted.

Public detail endpoints return `404` for blocked records.

## Source Run Policy

Only active `machine_ingest` sources with `lifecycle_state=runnable`, `automation_status=machine_ready_enabled`, registered parser, parser version, safe base URL, non-empty allowed domains, and manual review enabled may run.

Reference, portal, manual, disabled, adapter-missing, inactive, and disabled automation sources cannot run.

## Decision: No `official_legislation_record` Constant

The status constant `official_legislation_record` was considered during hardening but intentionally **not added**.

Rationale:
- Legislation records (`LegalInstrument`) already have `review_status` set to `pending_review` (non-public) after a ReviewItem is approved. A human admin must then promote them via the normal publication gate.
- `verified_court_record` is used conservatively for `LegalInstrument` entities that have passed the full evidence and review path. This is sufficient.
- Adding a new status constant would require migrating all existing rows, updating the Zod schema, all serializers, and every test. The risk of misclassification outweighs any labelling benefit.
- If future auditors require a legislative-specific status, it should be introduced as a migration with a one-way data migration and reviewed by a legal domain expert.
