# Phases 4–6 Implementation Roadmap

**Status:** Phase 4 Complete, Phase 5 Partially Complete (config + validation route done), Phase 6 Designed

## Phase 4: Source Registry Admin UI ✅ COMPLETE

**Completed:**

1. **frontend/app/admin/sources/page.tsx**
   - Displays all source registry entries from `/api/admin/sources`
   - Enable/disable buttons call POST endpoints to control `is_active`
   - Shows recent runs and health metrics on expand
   - Clear visual indicating: is_active=true → ingestion allowed, is_active=false → blocked

2. **frontend/components/Nav.tsx**
   - Added "Sources" link to admin navigation

3. **backend/app/tests/test_source_registry_control_plane.py**
   - Tests that disabled sources block ingestion
   - Tests that missing sources auto-create as disabled
   - Tests that enabled sources allow ingestion
   - Tests that admin enable/disable endpoints flip is_active
   - Proves SourceRegistry.is_active is sole runtime authority

**Key Principle:** Backend control already exists in `backend/app/ingestion/source_registry_ctl.py`. Phase 4 only exposed it in the UI. No new backend logic added.

**Done when:** Disabled source creates failed IngestionRun with error. Enabled source allows ingestion to proceed.

---

## Phase 5: Evidence Vault with Startup Verification

**Specification Design:**

### 5.1: Configuration (✅ COMPLETE)

Added to `backend/app/core/config.py`:
```python
evidence_store_root: str | None = None
evidence_store_required: bool = False
evidence_store_probe_write: bool = True
```

Env vars:
- `JTA_EVIDENCE_STORE_ROOT` — filesystem path (e.g., `/Volumes/JUDGE_EVIDENCE/judge-atlas-evidence`)
- `JTA_EVIDENCE_STORE_REQUIRED` — if true, startup fails if path missing
- `JTA_EVIDENCE_STORE_PROBE_WRITE` — if true, writes/deletes probe file on startup to verify write access

### 5.2: Validation Service (✅ COMPLETE)

`backend/app/services/evidence_store_validation.py` exists with `validate_evidence_store_root()`.
`/api/admin/evidence-store/status` endpoint wired in `backend/app/api/routes/evidence_store.py`
(uses `get_settings().evidence_store_root` and `repo_root=` correctly as of JUDGE-22).

### 5.3: Startup Integration (TODO)

In `backend/app/main.py` lifespan:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from pathlib import Path
    from app.services.evidence_store_validation import validate_evidence_store_root
    
    validate_evidence_store_root(
        settings.evidence_store_root,
        required=settings.evidence_store_required,
        probe_write=settings.evidence_store_probe_write,
        repo_root=str(Path(__file__).resolve().parents[2]),
    )
    
    initialize_postgis(engine)
    ...
```

### 5.4: Admin Status Endpoint (TODO)

Create `backend/app/api/routes/evidence_store_status.py`:
```
GET /api/admin/evidence-store/status
```

Response:
```json
{
  "enabled": true,
  "root_configured": true,
  "storage_layout": "snapshots/sha256/aa/bb/hash.bin",
  "probe_ok": true
}
```

Do not expose full filesystem path in response.

### 5.5: EvidenceStore Fail-Hard (TODO)

Update `backend/app/services/evidence_store.py`:
- If `root_path` is explicitly configured, fail startup if path does not exist
- Do not silently disable; raise RuntimeError
- Create `snapshots/sha256/` subdirectories on first write

**Example .env:**
```bash
JTA_EVIDENCE_STORE_ROOT=/Volumes/JUDGE_EVIDENCE/judge-atlas-evidence
JTA_EVIDENCE_STORE_REQUIRED=true
JTA_EVIDENCE_STORE_PROBE_WRITE=true
```

**Verification:**
```bash
cd backend
JTA_EVIDENCE_STORE_ROOT="/Volumes/JUDGE_EVIDENCE/judge-atlas-evidence" \
JTA_EVIDENCE_STORE_REQUIRED=true \
python -m uvicorn app.main:app --reload
# Should pass startup validation and print: [STARTUP] Evidence store validated
```

---

## Phase 6: Fluid Memory State Engine

**Specification Design:**

### 6.1: Memory Tables (TODO)

New Alembic migration `20260503_0004_add_memory_tables.py`:

```python
class MemoryClaim(Base, TimestampMixin):
    __tablename__ = "memory_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    claim_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_id: Mapped[str] = mapped_column(String(120), index=True)
    predicate: Mapped[str] = mapped_column(String(120), index=True)
    object_type: Mapped[str | None] = mapped_column(String(80))
    object_id: Mapped[str | None] = mapped_column(String(120))
    normalized_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), index=True, default="active")  # active, stale, disputed, invalidated, superseded
    truth_status: Mapped[str] = mapped_column(String(30), index=True, default="unverified")  # unverified, source_supported, review_supported, contradicted, rejected
    evidence_checksum: Mapped[str] = mapped_column(String(64))
    state_checksum: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(40))
    last_rebuilt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class MemoryEvidenceLink(Base, TimestampMixin):
    __tablename__ = "memory_evidence_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    memory_claim_id: Mapped[int] = mapped_column(ForeignKey("memory_claims.id"), index=True)
    source_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id"), index=True)
    review_item_id: Mapped[int | None] = mapped_column(ForeignKey("review_items.id"), index=True)
    relationship_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("relationship_evidence.id"), index=True)
    graph_edge_id: Mapped[int | None] = mapped_column(ForeignKey("entity_graph_edges.id"), index=True)
    support_role: Mapped[str] = mapped_column(String(30))  # supports, contradicts, context, source_only, review_decision
    evidence_hash: Mapped[str] = mapped_column(String(64))

class MemoryEntityState(Base, TimestampMixin):
    __tablename__ = "memory_entity_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    summary: Mapped[str] = mapped_column(Text)
    claim_count: Mapped[int] = mapped_column(default=0)
    active_claim_count: Mapped[int] = mapped_column(default=0)
    disputed_claim_count: Mapped[int] = mapped_column(default=0)
    evidence_checksum: Mapped[str] = mapped_column(String(64))
    state_checksum: Mapped[str] = mapped_column(String(64))
    rebuild_version: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), index=True, default="current")  # current, stale, rebuilding

class MemoryRelationshipState(Base, TimestampMixin):
    __tablename__ = "memory_relationship_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    from_entity_id: Mapped[str] = mapped_column(String(120), index=True)
    to_entity_type: Mapped[str] = mapped_column(String(80), index=True)
    to_entity_id: Mapped[str] = mapped_column(String(120), index=True)
    relationship_type: Mapped[str] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(30), index=True, default="suggested")  # suggested, review_supported, rejected, stale, invalidated
    evidence_checksum: Mapped[str] = mapped_column(String(64))
    state_checksum: Mapped[str] = mapped_column(String(64))
```

**Key Rule:** Memory relationship state is **suggestion only**, not graph authority.

### 6.2: Checksums (TODO)

Create `backend/app/memory/checksums.py`:

```python
import hashlib, json

def stable_json_hash(payload: Any) -> str:
    """Deterministic SHA256 of stable JSON."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def claim_key(payload: dict) -> str:
    """Deterministic key for claim based on content, not ID."""
    return stable_json_hash({
        "claim_type": payload["claim_type"],
        "subject_type": payload["subject_type"],
        "subject_id": str(payload["subject_id"]),
        "predicate": payload["predicate"],
        "object_type": payload.get("object_type"),
        "object_id": str(payload.get("object_id")) if payload.get("object_id") else None,
        "normalized_text": payload["normalized_text"].strip().lower(),
    })

def evidence_checksum(items: list[dict]) -> str:
    """Checksum across multiple evidence items."""
    clean = sorted(items, key=lambda x: json.dumps(x, sort_keys=True, default=str))
    return stable_json_hash(clean)
```

### 6.3–6.6: Services (TODO)

Create modules with deterministic-first logic (no embeddings yet):

- `backend/app/memory/extract_claims.py` — Extract claims from SourceSnapshot, ReviewItem, RelationshipEvidence
- `backend/app/memory/invalidation.py` — Mark memory stale/invalidated when evidence changes or is rejected
- `backend/app/memory/rebuild.py` — Rebuild entity and relationship summaries from evidence
- `backend/app/api/routes/admin_memory.py` — Expose memory status, rebuild, invalidation endpoints

### 6.7: Tests (TODO)

Prove:
- Claim keys are stable across rebuilds
- Rejected review invalidates linked memory
- Changed snapshots mark old claims stale
- Entity summaries rebuild deterministically
- Memory never publishes public map records
- Relationship memory is suggestion, not graph edge

### 6.8: Embeddings (TODO, AFTER CORRECTNESS)

Only after deterministic memory works correctly:
- Add embeddings table
- Integrate vector search
- Use memory as retrieval augmentation, not truth

---

## Next Implementation Order

1. **Phase 5.2–5.5:** Evidence store validation (3–4 files, ~500 lines)
2. **Phase 6.1–6.2:** Memory tables + migration + checksums (~300 lines)
3. **Phase 6.3–6.6:** Services and API endpoints (~2000 lines)
4. **Phase 6.7:** Tests (~500 lines)
5. **Phase 6.8:** Embeddings (after Phase 6.7 passes)

Total remaining: ~3500–4000 lines across 5 phases.

---

## Critical Mental Models

**Phase 5 (Evidence Vault):**
- Path is authority. Startup fails fast if not found or not writable.
- No silent fallbacks. If JTA_EVIDENCE_STORE_REQUIRED=true, startup must succeed or die.

**Phase 6 (Memory):**
- Evidence is authority.
- Review is authority.
- Memory is **derived state only**.
- Memory summarizes, clusters, suggests. It cannot create public truth.
- Invalidation prevents old memory from pretending to be fact.
- Checksums enable deterministic rebuilds from unchanged evidence.

---

## Testing the Complete Phases

After all three phases:

```bash
# Phase 4: Disable a source in UI, verify ingestion run fails
curl -X POST http://localhost:8000/api/admin/sources/courtlistener/disable \
  -H "X-JTA-Admin-Token: ..." 

# Phase 5: Start with external drive configured
export JTA_EVIDENCE_STORE_ROOT="/Volumes/JUDGE_EVIDENCE/judge-atlas-evidence"
export JTA_EVIDENCE_STORE_REQUIRED=true
python -m uvicorn app.main:app --reload  # Should validate and start

# Phase 6: Invalidate a source snapshot
POST /api/admin/memory/invalidate/snapshot/{id}
# Should mark all linked memory claims "invalidated"
# Rebuild should not resurrect invalidated claims
```

---

## Commits Ready to Push

- **Phase 4 complete:** 5fc6801
- **Phase 5.1 config:** backend/app/core/config.py (ready)

---

**Status Summary:**
- ✅ Phase 4 complete (source registry UI, control plane tests)
- ⏳ Phase 5 spec complete, implementation ready (evidence store validation)
- ⏳ Phase 6 spec complete, implementation ready (memory state engine)
- ⏳ All phases designed to follow correct principles: fail-closed, evidence-authority, derivative-state

**Recommended:** Implement Phase 5 next (evidence vault), then Phase 6 (memory layer). Do not add embeddings until Phase 6 deterministic logic passes all tests.
