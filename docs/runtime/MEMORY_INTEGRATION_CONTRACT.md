# Memory Integration Contract

**Version**: 1.0  
**Date**: 2026-05-01  
**Status**: Contract defined; stale-claim invalidation implemented in JUDGE-22 (rebuild.py)

## Purpose

Define the boundaries between the evidence-authoritative system (SourceSnapshot, ReviewItem, GraphEdge) and a future memory/summarization layer. This contract ensures memory remains a **rebuildable cache**, never the source of truth.

## Core Principle

**Evidence is authoritative. Memory is derivative.**

Any data in the memory layer must be traceable back to:
- A `SourceSnapshot` (captured raw content)
- A `ReviewItem` (admin-reviewed extraction)
- A `GraphEdge` (provenanced relationship)

## What Memory May Store

Memory can store **derived, summarization, and indexing** data:

| Type | Example | Provenance Required |
|------|---------|---------------------|
| Entity summaries | "Judge Smith presided over 47 cases in 2024" | source_snapshot_ids, review_item_ids |
| Normalized aliases | "J. Smith" → "John Smith" | source_snapshot_id where alias found |
| Retrieval embeddings | Vector for semantic search | source_snapshot_id of training content |
| Timeline summaries | "Case timeline: filing → hearing → ruling" | court_event_ids, source_snapshot_ids |
| Relationship summaries | "Defendant linked to 3 incidents" | graph_edge_ids, confidence scores |
| Review status | "pending_review", "approved", "rejected" | review_item_id |

## What Memory Must NOT Store

Memory **cannot** be authoritative for:

- ❌ Unverified accusations against individuals
- ❌ Final case facts without source links
- ❌ Judge/crime conclusions without evidence pointers
- ❌ Private/sensitive data not present in allowed public sources
- ❌ Legal determinations (guilt/innocence)
- ❌ Sentencing calculations without court record links

## Required Memory Record Fields

Every memory record must include:

```python
{
  "memory_id": "uuid",
  "memory_type": "entity_summary|relationship_summary|timeline_summary|alias|embedding",
  
  # Provenance (at least one required)
  "source_snapshot_id": "id or null",
  "source_review_id": "id or null", 
  "ingestion_run_id": "id or null",
  "graph_edge_ids": ["id1", "id2"],
  "entity_ids": ["id1", "id2"],
  
  # Metadata
  "created_at": "iso_timestamp",
  "updated_at": "iso_timestamp",
  "confidence": 0.0-1.0,
  "review_status": "pending|approved|rejected|stale",
  
  # Invalidation
  "invalidated_at": "iso_timestamp or null",
  "invalidation_reason": "string or null",
  
  # Content (rebuildable from sources)
  "summary_text": "string",
  "embedding_vector": [...],
  "metadata_json": {}
}
```

## Rebuild Process

If memory is lost or corrupted, it must be rebuildable:

1. Query all `SourceSnapshot` records with `content_hash` verification
2. Query all `ReviewItem` records with `status='approved'`
3. Query all `GraphEdge` records with `status='active'`
4. Re-run extraction/summarization on source content
5. Re-generate embeddings from verified content
6. Verify rebuild checksums match prior memory (if available)

## Deletion and Invalidation

### Automatic Invalidation

Memory records must be invalidated when:
- Source `SourceSnapshot` is purged (retention expiry)
- `ReviewItem` status changes to `rejected`
- `GraphEdge` is retracted or disputed
- Newer `SourceSnapshot` supersedes prior evidence

### Manual Invalidation

Admins can invalidate memory records:
```python
{
  "invalidated_at": "2026-05-01T12:00:00Z",
  "invalidation_reason": "Factual error: defendant name incorrect"
}
```

Invalidated records are excluded from queries but kept for audit.

## Relationship to Core Tables

```
SourceSnapshot (authority)
    ↓ creates
ReviewItem (review queue)
    ↓ admin approves
GraphEdge (provenanced relationship)
    ↓ indexed by
Memory (searchable cache with provenance pointers)
```

## Query Rules

1. **Public queries** must filter: `review_status='approved'` AND `invalidated_at IS NULL`
2. **Admin queries** may include pending/rejected for debugging
3. **Confidence threshold** default: 0.7 for public display
4. **Always include provenance** in API responses

## Implementation Notes (Future)

When implementing memory:
- Use vector database (e.g., pgvector) for embeddings
- Implement cache warming from approved sources
- Add background jobs to invalidate stale memory
- Never expose memory without provenance metadata
- Consider memory as ephemeral cache with TTL

## Compliance Checklist

Before any memory feature ships:
- [ ] All memory records include `source_snapshot_id` or `source_review_id`
- [ ] Rebuild process documented and tested
- [x] Invalidation triggers connected to source table changes — stale-claim invalidation implemented in JUDGE-22 `rebuild.py` (`run_rebuild()` diff loop)
- [ ] Public API filters by `review_status='approved'`
- [ ] Admin can manually invalidate with reason
- [ ] Memory loss does not lose evidence (sources remain)

## Acceptance Criteria

This contract is satisfied when:
1. Evidence tables remain authoritative
2. Memory is demonstrably rebuildable from sources
3. Invalidation correctly cascades from source changes
4. No public data appears without provenance
5. Performance gains from memory do not compromise accuracy
