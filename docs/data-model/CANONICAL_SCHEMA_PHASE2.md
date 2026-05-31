# JUDGE_ATLASX Phase 2: Canonical Data Model (Locked)

**Status:** Phase 2 Complete (May 16, 2026)  
**Effective Date:** May 16, 2026  
**Next Review:** Phase 8 (Entity Resolution)

This document locks the 8 canonical entities that form the core data model for JUDGE_ATLASX.

---

## Overview: 8 Canonical Entities

These entities represent the stable, production-ready schema for Phases 2–15. Changes to these entities require migrations and version bumping.

| Entity | Purpose | Immutability | Audit Trail |
|--------|---------|--------------|------------|
| **SourceRegistry** | Source metadata & health tracking | Soft (updatable) | created_at, updated_at |
| **SourceSnapshot** | Immutable evidence snapshots | Hard (no UPDATE) | created_at only |
| **IngestionRun** | Ingestion process audit trail | Soft (historical) | created_at, updated_at, timestamps |
| **ReviewItem** | Human review queue & decisions | Soft (status transitions) | created_at, reviewed_at |
| **AuditLog** | Immutable chain-of-custody log | Hard (append-only) | created_at only, no DELETE |
| **CanonicalEntity** | Entity deduplication & merging | Soft (merge tracking) | first_seen_at, last_verified_at |
| **RelationshipEvidence** | Relationship provenance | Soft (static after verification) | created_at only |
| **MemoryClaim** | Derivative claims (non-authoritative) | Soft (status changes) | created_at, updated_at |

---

## Entity Specifications

### 1. SourceRegistry

**Table:** `source_registry`  
**Purpose:** Centralized registry of all ingestion sources with metadata and health tracking.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique identifier |
| `source_key` | VARCHAR(100) | UNIQUE, NOT NULL, INDEX | Canonical key (machine name) |
| `source_name` | VARCHAR(255) | NOT NULL | Display name |
| `source_type` | VARCHAR(80) | NOT NULL, DEFAULT 'unknown' | Type (API, HTML, CSV, etc.) |
| `country` | VARCHAR(80) | NULLABLE | Country code (CA) |
| `province_state` | VARCHAR(80) | NULLABLE | Province/state (SK, AB) |
| `city` | VARCHAR(120) | NULLABLE | City |
| `source_tier` | VARCHAR(80) | INDEX, DEFAULT 'news_only_context' | Trust level (primary, secondary, news) |
| `parser_version` | VARCHAR(20) | NULLABLE, INDEX | Contract version for adapter |
| `automation_status` | VARCHAR(30) | NULLABLE | machine_ingest, portal_reference, manual_upload, disabled_stub |
| `fetch_method` | VARCHAR(20) | NOT NULL, DEFAULT 'manual' | API, HTML scrape, XML, CSV, etc. |
| `update_cadence` | VARCHAR(20) | NOT NULL, DEFAULT 'manual' | Daily, weekly, manual, never |
| `enabled` | BOOLEAN | NULLABLE | Is this source active? |
| `requires_manual_review` | BOOLEAN | NOT NULL, DEFAULT TRUE | Require reviewer approval before publish |
| `auto_publish_enabled` | BOOLEAN | NOT NULL, DEFAULT FALSE | Skip reviewer if high confidence |
| `last_successful_fetch` | DATETIME | NULLABLE | Timestamp of last successful ingestion |
| `last_error` | TEXT | NULLABLE | Most recent error message |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | When registered |
| `updated_at` | DATETIME | NOT NULL, DEFAULT now(), UPDATE now() | Last modification |

**Constraints:**
- `source_key` must be unique, immutable after creation
- `parser_version` must match adapters' version for ingestion to proceed
- `automation_status` gates auto-run capability

**Immutability:** Soft (updatable, but parser_version changes require migration)

---

### 2. SourceSnapshot

**Table:** `source_snapshots`  
**Purpose:** Immutable, timestamped snapshots of source content with full provenance.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique snapshot ID |
| `source_key` | VARCHAR(100) | INDEX, NULLABLE | Reference to SourceRegistry.source_key |
| `source_url` | VARCHAR(2048) | NOT NULL | URL fetched |
| `fetched_at` | DATETIME | NOT NULL | Exact fetch timestamp |
| `content_hash` | VARCHAR(64) | NOT NULL, INDEX | SHA-256 of raw content |
| `raw_content` | TEXT | NULLABLE | Full HTTP response body (if stored in DB) |
| `extracted_text` | TEXT | NULLABLE | Extracted/OCR text (if applicable) |
| `http_status` | INTEGER | NULLABLE | HTTP response code (200, 404, 500, etc.) |
| `content_type` | VARCHAR(255) | NULLABLE | Content-Type header (text/html, application/json, etc.) |
| `storage_backend` | VARCHAR(20) | NOT NULL, DEFAULT 'db' | db (JSONB) or s3 (external) |
| `storage_path` | VARCHAR(1024) | NULLABLE | S3 path or equivalent if external |
| `ingestion_run_id` | INTEGER | FK → ingestion_runs.id, INDEX | Which IngestionRun created this |
| `original_content_hash` | VARCHAR(64) | NULLABLE | Hash before any truncation |
| `stored_content_hash` | VARCHAR(64) | NULLABLE | Hash of what's actually stored |
| `content_size_bytes` | INTEGER | NULLABLE | Size of raw content |
| `stored_size_bytes` | INTEGER | NULLABLE | Size of stored content |
| `is_truncated` | BOOLEAN | NOT NULL, DEFAULT FALSE | Must always be FALSE after successful write |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | Creation timestamp |

**Constraints:**
- **No UPDATE after creation** (immutability enforced at application + database level)
- Deduplication: (source_key, content_hash) must be unique or result in skipped ingestion
- `is_truncated` must always be FALSE (evidence completeness)
- `stored_content_hash` must equal `original_content_hash` after successful write

**Immutability:** Hard (append-only, no updates post-creation)

**Lifecycle:**
1. Created by `SourceRunner.run()` after successful fetch + parse
2. Linked to ReviewItem for manual publication decision
3. Linked to MemoryClaim as evidence base
4. Referenced by RelationshipEvidence to prove edges
5. Archived to cold storage when retention_until reached

---

### 3. IngestionRun

**Table:** `ingestion_runs`  
**Purpose:** Audit trail of all ingestion executions with status and error tracking.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique run ID |
| `source_name` | VARCHAR(120) | NOT NULL, INDEX | Which source (SourceRegistry.source_key) |
| `started_at` | DATETIME | NOT NULL | Run start time |
| `finished_at` | DATETIME | NULLABLE | Run end time (NULL if in progress) |
| `status` | VARCHAR(80) | NOT NULL, DEFAULT 'running' | pending, running, success, partial_failure, failure |
| `fetched_count` | INTEGER | NOT NULL, DEFAULT 0 | Records fetched |
| `parsed_count` | INTEGER | NOT NULL, DEFAULT 0 | Records successfully parsed |
| `persisted_count` | INTEGER | NOT NULL, DEFAULT 0 | Records inserted/updated |
| `skipped_count` | INTEGER | NOT NULL, DEFAULT 0 | Records skipped (already seen) |
| `error_count` | INTEGER | NOT NULL, DEFAULT 0 | Number of errors |
| `errors` | JSON | NULLABLE | Array of error objects {message, code, record_id, timestamp} |
| `pipeline_stage` | VARCHAR(80) | NULLABLE, INDEX | fetch, parse, deduplicate, review, publish |
| `quarantine_reason` | TEXT | NULLABLE | If quarantined, why? |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | When logged |
| `updated_at` | DATETIME | NOT NULL, DEFAULT now(), UPDATE now() | Last update |

**Constraints:**
- `started_at` ≤ `finished_at` (if finished_at is set)
- `fetched_count` ≥ `parsed_count` (can't parse more than fetched)
- `parsed_count` ≥ `persisted_count` (can't persist more than parsed)
- `fetched_count` = `persisted_count + skipped_count + error_count` (conservation)

**Immutability:** Soft (historical record, updated until `finished_at`)

**Lifecycle:**
1. Created when source runner starts
2. Updated as run progresses (fetch → parse → persist)
3. Finalized when run completes (status = success/failure, finished_at set)
4. Linked to all SourceSnapshots created in this run
5. Linked to all ReviewItems generated from this run

---

### 4. ReviewItem

**Table:** `review_items`  
**Purpose:** Human review queue and publication workflow with decision history.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique review item ID |
| `record_type` | VARCHAR(80) | NOT NULL, INDEX | judge, court, case, defendant, incident, law, organization |
| `source_snapshot_id` | INTEGER | FK → source_snapshots.id, INDEX | Evidence for this review |
| `ingestion_run_id` | INTEGER | FK → ingestion_runs.id, INDEX, NULLABLE | Which run created this |
| `suggested_payload_json` | JSON | NOT NULL | Proposed entity/record to publish |
| `status` | VARCHAR(80) | NOT NULL, DEFAULT 'pending_review', INDEX | pending_review, approved, rejected, disputed, archived |
| `reviewer_id` | VARCHAR(120) | NULLABLE | Which user reviewed (Phase 6) |
| `reviewer_notes` | TEXT | NULLABLE | Reviewer comments |
| `reviewed_at` | DATETIME | NULLABLE | When review decision made |
| `public_visibility` | BOOLEAN | NOT NULL, DEFAULT FALSE | Is this publicly visible? |
| `publish_recommendation` | VARCHAR(80) | NOT NULL, INDEX | approved, rejected, disputed, flagged_for_review |
| `source_quality` | VARCHAR(80) | NOT NULL, INDEX | high, medium, low |
| `confidence` | FLOAT | NOT NULL, DEFAULT 0.0 | Parser confidence (0–1) |
| `privacy_status` | VARCHAR(80) | NOT NULL, INDEX | public, private, redacted, sealed |
| `source_url` | TEXT | NULLABLE | Original source URL |
| `ingestion_identity_hash` | VARCHAR(64) | NULLABLE, INDEX | Dedup hash |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | When created |

**Constraints:**
- Default `status = pending_review` (human approval required)
- `public_visibility = FALSE` until explicitly approved
- `reviewed_at` only set when `status` changes from pending_review
- `reviewer_id` only set when reviewed
- Transitions: pending_review → {approved, rejected, disputed} → archived

**Immutability:** Soft (status transitions are immutable, but history tracked via ReviewActionLog)

**Lifecycle:**
1. Created by SourceRunner when SourceSnapshot extracted
2. Status = pending_review (default)
3. Reviewer makes decision (approve/reject/dispute)
4. If approved: public_visibility = TRUE (if reviewer grants it)
5. If rejected: remains private, not published
6. If disputed: escalated for further review
7. Archived when decision final

---

### 5. AuditLog

**Table:** `audit_logs`  
**Purpose:** Immutable, append-only chain-of-custody log for all mutations.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique log entry ID |
| `action` | VARCHAR(120) | NOT NULL, INDEX | create, update, delete, approve, publish, reject, archive |
| `actor_id` | VARCHAR(120) | NULLABLE | User ID or system actor (Phase 6) |
| `actor_type` | VARCHAR(80) | NULLABLE | user, system, shared-admin-token |
| `actor_role` | VARCHAR(80) | NULLABLE | admin, reviewer, ingest_operator, viewer |
| `actor_ip` | VARCHAR(64) | NULLABLE | Client IP address |
| `user_agent` | VARCHAR(512) | NULLABLE | HTTP User-Agent header |
| `request_id` | VARCHAR(64) | NULLABLE | Correlation ID (Phase 6) |
| `entity_type` | VARCHAR(80) | NULLABLE, INDEX | judge, court, case, review_item, source_snapshot, etc. |
| `entity_id` | VARCHAR(255) | NULLABLE, INDEX | Which entity was modified |
| `payload` | JSON | NULLABLE | Request/action details |
| `entry_hash` | VARCHAR(64) | NULLABLE | SHA-256 of this entry (chain integrity, Phase 3) |
| `previous_entry_hash` | VARCHAR(64) | NULLABLE | Hash of prior entry (for chain verification) |
| `payload_hash` | VARCHAR(64) | NULLABLE | Hash of payload (integrity check) |
| `before_hash` | VARCHAR(64) | NULLABLE | Hash of state before (for rollback detection) |
| `after_hash` | VARCHAR(64) | NULLABLE | Hash of state after (for divergence detection) |
| `chain_version` | INTEGER | NULLABLE, DEFAULT 1 | Chain integrity version |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | Exact timestamp |

**Constraints:**
- **Append-only** (no UPDATE, no DELETE)
- `created_at` is immutable
- `entry_hash` chains to `previous_entry_hash` for integrity
- One entry per mutation (atomicity)
- All sensitive operations must log AuditLog entry

**Immutability:** Hard (append-only, no updates or deletes allowed)

**Chain Integrity (Phase 3):**
```
Entry N: entry_hash = SHA256(action | actor_id | entity_id | payload | previous_entry_hash)
Entry N+1: previous_entry_hash = Entry N's entry_hash
```

Verification: Replay all entries, recompute hashes, verify chain unbroken

---

### 6. CanonicalEntity

**Table:** `canonical_entities`  
**Purpose:** Central deduplication hub for entities appearing in multiple sources.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique canonical ID |
| `entity_type` | VARCHAR(50) | NOT NULL, INDEX | judge, court, law, incident, organization, location, defendant, case |
| `canonical_name` | VARCHAR(255) | NOT NULL | Preferred display name |
| `canonical_id_external` | VARCHAR(255) | NULLABLE | External ID (e.g., CourtListener judge ID) |
| `first_seen_at` | DATETIME | NOT NULL, DEFAULT now() | When first observed |
| `last_verified_at` | DATETIME | NULLABLE | Last manual or automatic verification |
| `merge_confidence` | FLOAT | NOT NULL, DEFAULT 1.0 | Confidence in this canonical identity (0–1) |
| `confidence_score` | FLOAT | NULLABLE | Per-entity confidence (e.g., judge's authority) |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'active', INDEX | active, merged_into, deprecated |
| `merged_into_id` | INTEGER | FK → canonical_entities.id, NULLABLE | If merged, which entity? |
| `created_by` | VARCHAR(120) | NULLABLE | auto_resolver, admin user ID |
| `notes` | TEXT | NULLABLE | Merge reason, dedup notes |

**Constraints:**
- `entity_type` + `canonical_name` should be (near-)unique within jurisdiction
- `merged_into_id` only set if status = merged_into
- Self-references forbidden (merged_into_id ≠ id)
- Merge is directional: A merged into B, then B is canonical

**Immutability:** Soft (can merge/deprecate, history preserved)

**Lifecycle:**
1. Created by auto-deduplication or manual admin merge
2. Status = active (entity exists)
3. Linked to via EntitySourceRecord (many sources → one canonical)
4. Can be merged into another canonical (status = merged_into)
5. Deprecated if found to be invalid (status = deprecated)

---

### 7. RelationshipEvidence

**Table:** `relationship_evidence`  
**Purpose:** Prove relationships between entities via evidence snapshots.

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique relationship ID |
| `from_entity_type` | VARCHAR(50) | NOT NULL, INDEX | judge, court, case, incident, law, etc. |
| `from_entity_id` | INTEGER | NOT NULL, INDEX | Source entity ID |
| `to_entity_type` | VARCHAR(50) | NOT NULL, INDEX | Target entity type |
| `to_entity_id` | INTEGER | NOT NULL, INDEX | Target entity ID |
| `relationship_type` | VARCHAR(50) | NOT NULL, INDEX | judge_presided_over, law_applied_in_case, incident_charged_as, etc. |
| `evidence_type` | VARCHAR(50) | NOT NULL | docket_text, statute, news_article, police_report, manual_review |
| `evidence_source` | VARCHAR(120) | NOT NULL, INDEX | SourceRegistry.source_key |
| `evidence_snapshot_id` | INTEGER | FK → source_snapshots.id, NULLABLE, INDEX | **Required: proves the relationship** |
| `evidence_excerpt` | TEXT | NULLABLE | Relevant quote from snapshot |
| `evidence_location` | VARCHAR(255) | NULLABLE | Page number, URL timestamp, section reference |
| `extracted_by` | VARCHAR(80) | NOT NULL | crawlee_runner, ai_linker, manual_admin |
| `confidence` | FLOAT | NOT NULL, DEFAULT 0.0 | How confident is this link? (0–1) |
| `verified_by` | VARCHAR(120) | NULLABLE | Reviewer who verified |
| `verified_at` | DATETIME | NULLABLE | When verified |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | When discovered |

**Constraints:**
- **Unique:** (from_entity_type, from_entity_id, to_entity_type, to_entity_id, relationship_type)
- `evidence_snapshot_id` must reference a valid SourceSnapshot (FK constraint)
- `confidence` in [0.0, 1.0]
- No self-relationships (from ≠ to)
- Multiple evidence_snapshot_ids can support same relationship (add new rows)

**Immutability:** Soft (static after creation, verified_at set once)

**Lifecycle:**
1. Created during entity resolution or linking phase
2. Requires evidence_snapshot_id (no orphan relationships)
3. Can be verified (verified_by, verified_at set)
4. Queried to build entity graph
5. Traversed for relationship lineage

---

### 8. MemoryClaim

**Table:** `memory_claims`  
**Purpose:** Derivative claims extracted from evidence (non-authoritative).

**Required Fields:**

| Field | Type | Constraints | Purpose |
|-------|------|-----------|---------|
| `id` | INTEGER | PK | Unique claim ID |
| `claim_key` | VARCHAR(64) | UNIQUE, NOT NULL, INDEX | UUID-based unique key |
| `claim_type` | VARCHAR(80) | NOT NULL, INDEX | biography, position, sentence, jurisdiction, etc. |
| `entity_id` | INTEGER | FK → canonical_entities.id, NOT NULL, INDEX | Which entity is this claim about? |
| `claim_value` | TEXT | NOT NULL | The actual claim text |
| `claim_value_json` | JSON | NULLABLE | Structured claim (if applicable) |
| `source_snapshot_id` | INTEGER | FK → source_snapshots.id, NULLABLE, INDEX | **Required: links to evidence** |
| `confidence` | FLOAT | NOT NULL, DEFAULT 0.0 | How confident? (0–1) |
| `extraction_model` | VARCHAR(80) | NULLABLE | Which AI/parser extracted this |
| `is_active` | BOOLEAN | NOT NULL, DEFAULT TRUE | Is this claim still valid? |
| `status` | VARCHAR(20) | NOT NULL, DEFAULT 'active', INDEX | active, contradicted, superseded, archived |
| `invalidated_at` | DATETIME | NULLABLE | When invalidated? |
| `invalidation_reason` | VARCHAR(255) | NULLABLE | Why invalidated? (conflicting evidence, etc.) |
| `last_seen_at` | DATETIME | NULLABLE | Last observation (salience) |
| `claim_embedding` | JSON | NULLABLE | Vector embedding (if enabled) |
| `created_at` | DATETIME | NOT NULL, DEFAULT now() | When extracted |
| `updated_at` | DATETIME | NOT NULL, DEFAULT now(), UPDATE now() | Last modification |

**Constraints:**
- **Non-authoritative marker:** `is_authoritative = FALSE` (immutable, Phase 10)
- `source_snapshot_id` required (all claims must trace to evidence)
- `confidence` in [0.0, 1.0]
- `status` in {active, contradicted, superseded, archived}
- One claim per (entity_id, claim_type, claim_value) (dedup)

**Immutability:** Soft (status transitions, salience updates, but claim_value immutable)

**Lifecycle:**
1. Extracted during evidence processing (is_authoritative = FALSE)
2. Source snapshot ID required (traceability)
3. Confidence scored (0–1)
4. Can be contradicted/superseded (status change)
5. Invalidated if conflicting evidence found (invalidated_at, invalidation_reason)
6. Salience decays over time (last_seen_at aging)

**Non-Authoritative Rule:**
- MemoryClaim.is_authoritative MUST be FALSE (immutable)
- Memory derives from evidence; evidence is authoritative
- AI outputs are suggestions only, not ground truth
- Must be reviewed before publication

---

## Indexing Strategy

**Mandatory Indices (High-Query)**

| Table | Column(s) | Reason |
|-------|-----------|--------|
| source_registry | source_key | Lookup by source |
| source_snapshots | source_key, content_hash | Dedup detection |
| source_snapshots | ingestion_run_id | Filter by run |
| review_items | status | Review queue filtering |
| review_items | source_snapshot_id | Link to evidence |
| audit_logs | created_at | Timeline queries |
| audit_logs | entity_type, entity_id | Entity mutation history |
| canonical_entities | entity_type | Dedup by type |
| memory_claims | entity_id, status | Claim retrieval |
| memory_claims | source_snapshot_id | Evidence lineage |

**Optional Indices (Search/Analytics)**

| Table | Column(s) | Reason |
|-------|-----------|--------|
| source_registry | automation_status | Source health dashboard |
| ingestion_runs | status | Pipeline monitoring |
| review_items | created_at, status | Queue age analytics |

---

## Foreign Key Constraints

| From | To | Constraint | On Delete |
|------|----|-----------|----|
| review_items | source_snapshots | RESTRICT | Snapshots immutable |
| review_items | ingestion_runs | SET NULL | Run deletion → NULL |
| audit_logs | (entities) | RESTRICT | Audit trail immutable |
| canonical_entities | canonical_entities | SET NULL | Merged entity deprecation |
| relationship_evidence | source_snapshots | RESTRICT | Evidence immutable |
| relationship_evidence | canonical_entities | CASCADE | Dedup cleanup |
| memory_claims | source_snapshots | RESTRICT | Evidence immutable |
| memory_claims | canonical_entities | CASCADE | Entity cleanup |

---

## Migration Path

Phase 2 establishes these 8 entities. Future phases will:

- **Phase 3:** Add ingestion contract validation (parser_version immutability)
- **Phase 5:** Add evidence vault operations (replay, lineage)
- **Phase 6:** Add user identity fields to AuditLog (Phase 2 has placeholders)
- **Phase 8:** Add entity resolution and merging logic
- **Phase 10:** Add is_authoritative field to MemoryClaim (non-updateable)
- **Phase 12:** Verify all constraints with comprehensive tests
- **Phase 14:** Enable chain integrity checks on AuditLog

---

## Testing

All 8 entities are tested in:
- `backend/app/tests/test_phase2_schema_lock.py` — Field presence, types, constraints
- Integration tests — Foreign key cascades, immutability enforcement
- Migration tests — Schema changes between versions

Run tests:
```bash
pytest backend/app/tests/test_phase2_schema_lock.py -v
```

---

## References

- **Data Model Diagram:** docs/data-model/ER_DIAGRAM.md
- **Phase 1:** docs/STRUCTURE.md (Repository organization)
- **Phase 3:** Ingestion hardening (contract validation)
- **Phase 5:** Evidence vault operations
- **Phase 6:** Auth + RBAC (AuditLog actor fields)
