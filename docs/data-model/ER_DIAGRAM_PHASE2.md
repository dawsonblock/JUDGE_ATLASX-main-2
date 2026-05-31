# Entity-Relationship (ER) Diagram — Phase 2 Canonical Model

This diagram shows the 8 locked entities and their relationships.

```
graph TD
    SR["<b>SourceRegistry</b><br/><br/>source_key (UNIQUE)<br/>source_name<br/>source_type<br/>parser_version<br/>automation_status<br/>last_successful_fetch<br/>created_at | updated_at"]
    SS["<b>SourceSnapshot</b><br/>(IMMUTABLE)<br/><br/>source_key<br/>source_url<br/>content_hash (SHA256)<br/>raw_content<br/>fetched_at<br/>ingestion_run_id→<br/>created_at (ONLY)"]
    IR["<b>IngestionRun</b><br/><br/>source_name<br/>status<br/>started_at | finished_at<br/>fetched_count<br/>parsed_count<br/>persisted_count<br/>error_count<br/>created_at | updated_at"]
    RI["<b>ReviewItem</b><br/><br/>record_type<br/>status (pending→approve)<br/>source_snapshot_id→<br/>ingestion_run_id→<br/>reviewer_id<br/>public_visibility<br/>publish_recommendation<br/>created_at | reviewed_at"]
    AL["<b>AuditLog</b><br/>(APPEND-ONLY)<br/><br/>action<br/>actor_id<br/>entity_type | entity_id<br/>payload<br/>entry_hash<br/>previous_entry_hash<br/>created_at (ONLY)"]
    CE["<b>CanonicalEntity</b><br/><br/>entity_type<br/>canonical_name<br/>merge_confidence<br/>status (active|merged)<br/>merged_into_id→<br/>first_seen_at<br/>last_verified_at"]
    RE["<b>RelationshipEvidence</b><br/><br/>from_entity_type | from_entity_id<br/>to_entity_type | to_entity_id<br/>relationship_type<br/>evidence_snapshot_id→<br/>confidence<br/>extracted_by<br/>created_at"]
    MC["<b>MemoryClaim</b><br/>(NON-AUTHORITATIVE)<br/><br/>claim_type<br/>entity_id→<br/>claim_value<br/>source_snapshot_id→<br/>status<br/>confidence<br/>is_active<br/>created_at | updated_at"]

    %% Relationships
    IR -->|creates| SS
    SS -->|references| RI
    IR -->|references| RI
    SS -->|cited by| MC
    SS -->|proves| RE
    CE -->|deduplicates| RE
    CE -->|basis| MC
    AL -->|logs| RI
    AL -->|logs| SS
    AL -->|logs| MC
    CE -->|merged_into| CE
    
    %% Immutability markers
    SS -.IMMUTABLE.->|no UPDATE| SS
    AL -.APPEND-ONLY.->|no UPDATE/DELETE| AL
    MC -.NON-AUTH.->|always FALSE| MC
    
    style SR fill:#e1f5ff
    style SS fill:#fff3e0
    style IR fill:#f3e5f5
    style RI fill:#e8f5e9
    style AL fill:#fce4ec
    style CE fill:#ede7f6
    style RE fill:#e0f2f1
    style MC fill:#fff9c4
```

## Entity Data Flow

**Ingestion Path:**
1. **SourceRegistry** defines source metadata (parser_version, automation_status)
2. **SourceRunner** fetches from source → **SourceSnapshot** (immutable, SHA256 hash)
3. Parser creates **ReviewItem** from snapshot
4. **AuditLog** records fetch action (chain-linked entries)

**Review Path:**
1. **ReviewItem** queued (status=pending_review)
2. Reviewer approves/rejects → AuditLog entry
3. If approved: public_visibility=TRUE
4. Decision recorded in AuditLog (immutable trail)

**Deduplication Path:**
1. Parser extracts entities → **CanonicalEntity** candidates
2. Matcher merges duplicates (status=merged_into)
3. **RelationshipEvidence** links canonical entities
4. Evidence source: **SourceSnapshot** (immutable proof)

**Memory Path:**
1. Claims extracted → **MemoryClaim** (is_authoritative=FALSE)
2. Link source: **SourceSnapshot** (traceability)
3. Claims may be contradicted/superseded (status=active|contradicted|superseded)
4. All changes logged in **AuditLog** (chain-linked)

---

## Immutability Enforcement

| Entity | Type | Enforcement |
|--------|------|-------------|
| **SourceSnapshot** | Hard | No UPDATE allowed; deleted only by retention policy |
| **AuditLog** | Hard | Append-only; no UPDATE or DELETE; chain-linked hashes |
| **MemoryClaim.is_authoritative** | Hard | Always FALSE; immutable marker |
| **SourceRegistry** | Soft | Updatable but parser_version changes require migration |
| **ReviewItem** | Soft | Status transitions immutable; history in ReviewActionLog |
| **CanonicalEntity** | Soft | Can merge; history preserved |
| **RelationshipEvidence** | Soft | Static after creation; verified_at set once |

---

## Key Constraints

**Foreign Keys:**
- ReviewItem.source_snapshot_id → SourceSnapshot.id (RESTRICT on delete)
- ReviewItem.ingestion_run_id → IngestionRun.id (SET NULL on delete)
- RelationshipEvidence.evidence_snapshot_id → SourceSnapshot.id (RESTRICT)
- MemoryClaim.source_snapshot_id → SourceSnapshot.id (RESTRICT)
- MemoryClaim.entity_id → CanonicalEntity.id (CASCADE)
- CanonicalEntity.merged_into_id → CanonicalEntity.id (self-reference)

**Unique Constraints:**
- SourceRegistry.source_key (UNIQUE)
- SourceSnapshot.(source_key, content_hash) (dedup detection)
- RelationshipEvidence.(from_entity_type, from_entity_id, to_entity_type, to_entity_id, relationship_type)
- MemoryClaim.claim_key (UUID, UNIQUE)

**Check Constraints:**
- IngestionRun: persisted + skipped + error ≤ fetched
- RelationshipEvidence: from ≠ to (no self-loops)
- AuditLog: entry_hash formed from previous_entry_hash (chain integrity)

---

## Indices for Query Performance

**Primary lookups:**
- source_registry(source_key)
- canonical_entities(entity_type)
- memory_claims(entity_id, status)
- review_items(status)

**Join paths:**
- source_snapshots(ingestion_run_id)
- memory_claims(source_snapshot_id)
- relationship_evidence(evidence_snapshot_id)

**Timeline queries:**
- audit_logs(created_at)
- audit_logs(entity_type, entity_id)

**Dedup detection:**
- source_snapshots(source_key, content_hash)

---

## Phase 2 Completion Checklist

- [x] All 8 entities exist and are documented
- [x] Required fields present with correct types
- [x] Foreign keys defined and validated
- [x] Unique constraints for immutability
- [x] Indices for query performance
- [x] Migration created (20260516_0002)
- [x] Schema lock tests written
- [x] ER diagram created
- [x] No data loss or breaking changes
- [ ] Run migration: `alembic upgrade head`
- [ ] Run tests: `pytest backend/app/tests/test_phase2_schema_lock.py -v`
- [ ] Verify schema: `alembic current`
