"""Public source coverage endpoint.

GET /api/v1/sources/coverage — returns aggregate coverage counts broken
down by country, jurisdiction, and source tier.  Only active sources are
included in the summary.
"""

from __future__ import annotations

from app.db.session import get_db
from app.ingestion.source_status import derive_source_status
from app.models.entities import SourceRegistry
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


class CoverageItem(BaseModel):
    country: str | None
    jurisdiction: str | None
    source_tier: str
    count: int


class CoverageResponse(BaseModel):
    total_active_sources: int
    coverage: list[CoverageItem]


class PublicSourceStatusItem(BaseModel):
    source_key: str
    source_name: str
    source_type: str
    source_tier: str
    source_class: str | None
    source_status: str
    automation_status: str | None
    lifecycle_state: str | None
    is_active: bool


class PublicSourceStatusResponse(BaseModel):
    total_sources: int
    items: list[PublicSourceStatusItem]


@router.get("/coverage", response_model=CoverageResponse)
def get_source_coverage(db: Session = Depends(get_db)) -> CoverageResponse:
    """Return aggregate source coverage counts for active sources only."""
    rows = db.execute(
        select(
            SourceRegistry.country,
            SourceRegistry.jurisdiction,
            SourceRegistry.source_tier,
            func.count(SourceRegistry.id).label("count"),
        )
        .where(SourceRegistry.is_active.is_(True))
        .group_by(
            SourceRegistry.country,
            SourceRegistry.jurisdiction,
            SourceRegistry.source_tier,
        )
        .order_by(
            SourceRegistry.country,
            SourceRegistry.jurisdiction,
            SourceRegistry.source_tier,
        )
    ).all()

    total = (
        db.scalar(
            select(func.count(SourceRegistry.id)).where(
                SourceRegistry.is_active.is_(True)
            )
        )
        or 0
    )

    return CoverageResponse(
        total_active_sources=total,
        coverage=[
            CoverageItem(
                country=r.country,
                jurisdiction=r.jurisdiction,
                source_tier=r.source_tier,
                count=r.count,
            )
            for r in rows
        ],
    )


@router.get("/status", response_model=PublicSourceStatusResponse)
def get_public_source_status(
    db: Session = Depends(get_db),
    source_status: str | None = None,
    lifecycle_state: str | None = None,
) -> PublicSourceStatusResponse:
    """Return public-safe source status list without admin-only fields."""
    rows = db.scalars(
        select(SourceRegistry).order_by(SourceRegistry.source_name)
    ).all()

    items: list[PublicSourceStatusItem] = []
    for src in rows:
        status = derive_source_status(
            explicit_status=getattr(src, "source_status", None),
            lifecycle_state=src.lifecycle_state,
            automation_status=src.automation_status,
            source_class=src.source_class,
        ).value

        if source_status and status != source_status:
            continue
        if lifecycle_state and src.lifecycle_state != lifecycle_state:
            continue

        items.append(
            PublicSourceStatusItem(
                source_key=src.source_key,
                source_name=src.source_name,
                source_type=src.source_type,
                source_tier=src.source_tier,
                source_class=src.source_class,
                source_status=status,
                automation_status=src.automation_status,
                lifecycle_state=src.lifecycle_state,
                is_active=src.is_active,
            )
        )

    return PublicSourceStatusResponse(total_sources=len(items), items=items)
