"""API endpoints for source snapshot inspection and provenance.

Provides admin endpoints for viewing raw evidence that produced
review items and entity relationships.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.admin import require_admin_token
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.models.entities import RelationshipEvidence, ReviewItem, SourceSnapshot
from app.services.evidence_store import EvidenceStore
from app.services.snapshot_writer import read_snapshot_content

router = APIRouter(prefix="/api/admin/snapshots", tags=["snapshots"])


class SnapshotResponse(BaseModel):
    """Snapshot metadata response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_url: str
    fetched_at: str
    content_hash: str
    http_status: int | None
    content_type: str | None
    storage_backend: str
    storage_path: str | None
    retention_until: str | None
    created_at: str
    has_raw_content: bool


class SnapshotContentResponse(BaseModel):
    """Snapshot raw content response."""

    content: str
    content_type: str | None
    encoding: str = "utf-8"
    size_bytes: int
    hash_verified: bool


class SnapshotReviewItem(BaseModel):
    """Review item linked to snapshot."""

    review_item_id: int
    record_type: str
    raw_source_id: int | None
    source_url: str | None
    status: str
    created_at: str


class SnapshotEvidence(BaseModel):
    """Relationship evidence linked to snapshot."""

    evidence_id: int
    relationship_type: str
    from_entity_type: str
    from_entity_id: int
    to_entity_type: str
    to_entity_id: int
    confidence: float
    is_verified: bool


class SnapshotLinkedDataResponse(BaseModel):
    """Linked review items and evidence."""

    snapshot_id: int
    review_items: list[SnapshotReviewItem]
    evidence_records: list[SnapshotEvidence]
    total_review_items: int
    total_evidence: int


# Static routes must be defined BEFORE dynamic routes
# to avoid path parameter conflicts

@router.get("/by-hash/{content_hash}", response_model=SnapshotResponse)
def get_snapshot_by_hash(
    content_hash: str,
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> SnapshotResponse:
    """Find snapshot by content hash (admin only)."""
    snapshot = db.query(SourceSnapshot).filter_by(content_hash=content_hash).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Check if raw content exists
    has_raw = False
    if snapshot.storage_backend == "db":
        has_raw = snapshot.raw_content is not None
    elif snapshot.storage_path:
        store = EvidenceStore()
        has_raw = store.exists(snapshot.content_hash)

    return SnapshotResponse(
        id=snapshot.id,
        source_url=snapshot.source_url,
        fetched_at=snapshot.fetched_at.isoformat() if snapshot.fetched_at else "",
        content_hash=snapshot.content_hash,
        http_status=snapshot.http_status,
        content_type=snapshot.content_type,
        storage_backend=snapshot.storage_backend,
        storage_path=snapshot.storage_path,
        retention_until=snapshot.retention_until.isoformat() if snapshot.retention_until else None,
        created_at=snapshot.created_at.isoformat() if snapshot.created_at else "",
        has_raw_content=has_raw,
    )


@router.get("/search/by-url")
def search_snapshots_by_url(
    url_pattern: str = Query(..., description="URL pattern to search for"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> dict[str, Any]:
    """Search snapshots by URL pattern (admin only)."""
    from sqlalchemy import func

    snapshots = (
        db.query(SourceSnapshot)
        .filter(func.lower(SourceSnapshot.source_url).contains(func.lower(url_pattern)))
        .order_by(SourceSnapshot.created_at.desc())
        .limit(limit)
        .all()
    )

    return {
        "url_pattern": url_pattern,
        "total": len(snapshots),
        "snapshots": [
            {
                "id": s.id,
                "source_url": s.source_url,
                "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None,
                "content_hash": s.content_hash,
                "storage_backend": s.storage_backend,
            }
            for s in snapshots
        ],
    }


# Dynamic routes with path parameters

@router.get("/{snapshot_id}", response_model=SnapshotResponse)
def get_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> SnapshotResponse:
    """Get snapshot metadata by ID (admin only)."""
    snapshot = db.query(SourceSnapshot).filter_by(id=snapshot_id).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Check if raw content exists (DB or external)
    has_raw = False
    if snapshot.storage_backend == "db":
        has_raw = snapshot.raw_content is not None
    elif snapshot.storage_path:
        store = EvidenceStore()
        has_raw = store.exists(snapshot.content_hash)

    return SnapshotResponse(
        id=snapshot.id,
        source_url=snapshot.source_url,
        fetched_at=snapshot.fetched_at.isoformat() if snapshot.fetched_at else "",
        content_hash=snapshot.content_hash,
        http_status=snapshot.http_status,
        content_type=snapshot.content_type,
        storage_backend=snapshot.storage_backend,
        storage_path=snapshot.storage_path,
        retention_until=snapshot.retention_until.isoformat() if snapshot.retention_until else None,
        created_at=snapshot.created_at.isoformat() if snapshot.created_at else "",
        has_raw_content=has_raw,
    )


@router.get("/{snapshot_id}/raw", response_model=SnapshotContentResponse)
def get_snapshot_raw(
    snapshot_id: int,
    verify_hash: bool = Query(True, description="Verify content hash matches"),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> SnapshotContentResponse:
    """Get raw snapshot content (admin only).

    Retrieves from external storage if configured, otherwise from DB.
    """
    snapshot = db.query(SourceSnapshot).filter_by(id=snapshot_id).first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    content_bytes = read_snapshot_content(db, snapshot)

    if content_bytes is None:
        raise HTTPException(status_code=404, detail="No raw content available")

    # Verify hash against original bytes
    hash_verified = True
    if verify_hash:
        import hashlib
        computed_hash = hashlib.sha256(content_bytes).hexdigest()
        hash_verified = computed_hash == snapshot.content_hash
        if not hash_verified:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Content hash mismatch: stored {snapshot.content_hash!r}, "
                    f"computed {computed_hash!r}"
                ),
            )

    original_size_bytes = len(content_bytes)

    # Convert bytes to string for JSON response; detect encoding for caller
    encoding = "utf-8"
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        import base64
        content = base64.b64encode(content_bytes).decode("ascii")
        encoding = "base64"

    return SnapshotContentResponse(
        content=content,
        content_type=snapshot.content_type,
        encoding=encoding,
        size_bytes=original_size_bytes,
        hash_verified=hash_verified,
    )


@router.get("/{snapshot_id}/linked", response_model=SnapshotLinkedDataResponse)
def get_snapshot_linked(
    snapshot_id: int,
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> SnapshotLinkedDataResponse:
    """Get review items and evidence linked to this snapshot (admin only)."""
    # Verify snapshot exists
    snapshot = db.query(SourceSnapshot).filter_by(id=snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # Find review items linked to this snapshot
    review_items = (
        db.query(ReviewItem)
        .filter(ReviewItem.source_snapshot_id == snapshot_id)
        .all()
    )

    # Find relationship evidence linked to this snapshot
    evidence_records = (
        db.query(RelationshipEvidence)
        .filter(RelationshipEvidence.evidence_snapshot_id == snapshot_id)
        .all()
    )

    return SnapshotLinkedDataResponse(
        snapshot_id=snapshot_id,
        review_items=[
            SnapshotReviewItem(
                review_item_id=ri.id,
                record_type=ri.record_type,
                raw_source_id=ri.raw_source_id,
                source_url=ri.source_url,
                status=ri.status,
                created_at=ri.created_at.isoformat() if ri.created_at else "",
            )
            for ri in review_items
        ],
        evidence_records=[
            SnapshotEvidence(
                evidence_id=e.id,
                relationship_type=e.relationship_type,
                from_entity_type=e.from_entity_type,
                from_entity_id=e.from_entity_id,
                to_entity_type=e.to_entity_type,
                to_entity_id=e.to_entity_id,
                confidence=e.confidence,
                is_verified=e.verified_by is not None,
            )
            for e in evidence_records
        ],
        total_review_items=len(review_items),
        total_evidence=len(evidence_records),
    )
