"""API endpoints for relationship evidence management.

Provides endpoints for viewing, creating, and verifying evidence
that supports entity relationships.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.admin import (
    log_mutation,
    require_admin_token,
)
from app.auth.actor import AdminActor
from app.db.session import get_db
from app.security.import_authority import require_reviewer_actor, require_source_admin_actor
from app.services.relationship_evidence import RelationshipEvidenceService

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceCreateRequest(BaseModel):
    """Request to create new relationship evidence."""

    model_config = ConfigDict(from_attributes=True)

    from_entity_type: str
    from_entity_id: int
    to_entity_type: str
    to_entity_id: int
    relationship_type: str
    evidence_type: str
    evidence_source: str
    evidence_excerpt: str | None = None
    evidence_location: str | None = None
    evidence_snapshot_id: int | None = None
    extracted_by: str = "api"
    confidence: float = 0.5


class EvidenceVerifyRequest(BaseModel):
    """Request to verify evidence."""

    notes: str | None = None


class EvidenceUnverifyRequest(BaseModel):
    """Request to unverify evidence."""

    reason: str | None = None


class EvidenceResponse(BaseModel):
    """Evidence response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    from_entity_type: str
    from_entity_id: int
    to_entity_type: str
    to_entity_id: int
    relationship_type: str
    evidence_type: str
    evidence_source: str
    evidence_excerpt: str | None
    evidence_location: str | None
    extracted_by: str
    confidence: float
    is_verified: bool
    verified_by: str | None
    verified_at: str | None
    created_at: str


class EvidenceListResponse(BaseModel):
    """List of evidence records."""

    total: int
    evidence: list[dict[str, Any]]


@router.get("/relationship/{from_type}/{from_id}/{to_type}/{to_id}")
def get_relationship_evidence(
    from_type: str,
    from_id: int,
    to_type: str,
    to_id: int,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_reviewer_actor),
) -> EvidenceListResponse:
    """Get all evidence for a specific relationship (reviewer only)."""
    service = RelationshipEvidenceService(db)
    evidence = service.get_evidence_for_relationship(
        from_entity_type=from_type,
        from_entity_id=from_id,
        to_entity_type=to_type,
        to_entity_id=to_id,
        limit=limit,
    )

    return EvidenceListResponse(
        total=len(evidence),
        evidence=[
            {
                "evidence_id": e.evidence_id,
                "relationship_type": e.relationship_type,
                "evidence_type": e.evidence_type,
                "evidence_source": e.evidence_source,
                "confidence": e.confidence,
                "is_verified": e.is_verified,
                "excerpt_preview": e.excerpt_preview,
            }
            for e in evidence
        ],
    )


@router.get("/entity/{entity_type}/{entity_id}")
def get_entity_evidence(
    entity_type: str,
    entity_id: int,
    as_source: bool = Query(True, description="Include as relationship source"),
    as_target: bool = Query(True, description="Include as relationship target"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_reviewer_actor),
) -> EvidenceListResponse:
    """Get all evidence involving an entity (reviewer only)."""
    service = RelationshipEvidenceService(db)
    evidence = service.get_evidence_for_entity(
        entity_type=entity_type,
        entity_id=entity_id,
        as_source=as_source,
        as_target=as_target,
        limit=limit,
    )

    return EvidenceListResponse(total=len(evidence), evidence=evidence)


@router.get("/unverified")
def get_unverified_evidence(
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    max_confidence: float = Query(1.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: AdminActor = Depends(require_admin_token),
) -> EvidenceListResponse:
    """Get unverified evidence within a confidence range (admin only)."""
    service = RelationshipEvidenceService(db)
    records = service.get_unverified_evidence(
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        limit=limit,
    )

    return EvidenceListResponse(
        total=len(records),
        evidence=[
            {
                "evidence_id": r.id,
                "relationship_type": r.relationship_type,
                "from_entity_type": r.from_entity_type,
                "from_entity_id": r.from_entity_id,
                "to_entity_type": r.to_entity_type,
                "to_entity_id": r.to_entity_id,
                "evidence_type": r.evidence_type,
                "confidence": r.confidence,
                "extracted_by": r.extracted_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    )


@router.post("/create", response_model=EvidenceResponse)
def create_evidence(
    request: EvidenceCreateRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_source_admin_actor),
) -> EvidenceResponse:
    """Create new relationship evidence (source_admin only)."""
    service = RelationshipEvidenceService(db)

    try:
        evidence = service.create_evidence(
            from_entity_type=request.from_entity_type,
            from_entity_id=request.from_entity_id,
            to_entity_type=request.to_entity_type,
            to_entity_id=request.to_entity_id,
            relationship_type=request.relationship_type,
            evidence_type=request.evidence_type,
            evidence_source=request.evidence_source,
            evidence_excerpt=request.evidence_excerpt,
            evidence_location=request.evidence_location,
            evidence_snapshot_id=request.evidence_snapshot_id,
            extracted_by=request.extracted_by,
            confidence=request.confidence,
            commit=False,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        log_mutation(
            action="evidence.create",
            entity_type="relationship_evidence",
            entity_id=str(evidence.id),
            payload={"relationship_type": request.relationship_type, "evidence_type": request.evidence_type},
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Audit logging failed; mutation aborted")

    return EvidenceResponse(
        id=evidence.id,
        from_entity_type=evidence.from_entity_type,
        from_entity_id=evidence.from_entity_id,
        to_entity_type=evidence.to_entity_type,
        to_entity_id=evidence.to_entity_id,
        relationship_type=evidence.relationship_type,
        evidence_type=evidence.evidence_type,
        evidence_source=evidence.evidence_source,
        evidence_excerpt=evidence.evidence_excerpt,
        evidence_location=evidence.evidence_location,
        extracted_by=evidence.extracted_by,
        confidence=evidence.confidence,
        is_verified=evidence.verified_by is not None,
        verified_by=evidence.verified_by,
        verified_at=evidence.verified_at.isoformat() if evidence.verified_at else None,
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


@router.post("/{evidence_id}/verify", response_model=EvidenceResponse)
def verify_evidence(
    evidence_id: int,
    request: EvidenceVerifyRequest,
    db: Session = Depends(get_db),
    admin_actor: AdminActor = Depends(require_reviewer_actor),
) -> EvidenceResponse:
    """Verify relationship evidence (reviewer only)."""
    service = RelationshipEvidenceService(db)

    evidence = service.verify_evidence(
        evidence_id=evidence_id,
        verified_by=admin_actor.actor_id,
        notes=request.notes,
        commit=False,
    )

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    try:
        log_mutation(
            action="evidence.verify",
            entity_type="relationship_evidence",
            entity_id=str(evidence_id),
            actor=admin_actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Audit logging failed; mutation aborted")

    return EvidenceResponse(
        id=evidence.id,
        from_entity_type=evidence.from_entity_type,
        from_entity_id=evidence.from_entity_id,
        to_entity_type=evidence.to_entity_type,
        to_entity_id=evidence.to_entity_id,
        relationship_type=evidence.relationship_type,
        evidence_type=evidence.evidence_type,
        evidence_source=evidence.evidence_source,
        evidence_excerpt=evidence.evidence_excerpt,
        evidence_location=evidence.evidence_location,
        extracted_by=evidence.extracted_by,
        confidence=evidence.confidence,
        is_verified=evidence.verified_by is not None,
        verified_by=evidence.verified_by,
        verified_at=evidence.verified_at.isoformat() if evidence.verified_at else None,
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


@router.post("/{evidence_id}/unverify", response_model=EvidenceResponse)
def unverify_evidence(
    evidence_id: int,
    request: EvidenceUnverifyRequest,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_reviewer_actor),
) -> EvidenceResponse:
    """Remove verification from evidence (reviewer only)."""
    service = RelationshipEvidenceService(db)

    evidence = service.unverify_evidence(
        evidence_id=evidence_id,
        reason=request.reason,
        commit=False,
    )

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    try:
        log_mutation(
            action="evidence.unverify",
            entity_type="relationship_evidence",
            entity_id=str(evidence_id),
            actor=actor,
            db=db,
            fail_closed=True,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Audit logging failed; mutation aborted")

    return EvidenceResponse(
        id=evidence.id,
        from_entity_type=evidence.from_entity_type,
        from_entity_id=evidence.from_entity_id,
        to_entity_type=evidence.to_entity_type,
        to_entity_id=evidence.to_entity_id,
        relationship_type=evidence.relationship_type,
        evidence_type=evidence.evidence_type,
        evidence_source=evidence.evidence_source,
        evidence_excerpt=evidence.evidence_excerpt,
        evidence_location=evidence.evidence_location,
        extracted_by=evidence.extracted_by,
        confidence=evidence.confidence,
        is_verified=evidence.verified_by is not None,
        verified_by=evidence.verified_by,
        verified_at=evidence.verified_at.isoformat() if evidence.verified_at else None,
        created_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )
