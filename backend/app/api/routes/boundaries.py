"""Public boundaries endpoint — serves Natural Earth administrative boundaries."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Boundary

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("/boundaries")
def list_boundaries(
    boundary_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return all boundaries, optionally filtered by boundary_type.

    boundary_type: ``country`` | ``state_province``
    """
    stmt = select(Boundary)
    if boundary_type:
        stmt = stmt.where(Boundary.boundary_type == boundary_type)
    stmt = stmt.order_by(Boundary.name)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "iso_code": b.iso_code,
            "boundary_type": b.boundary_type,
            "parent_iso": b.parent_iso,
            "source": b.source,
            "geojson_simplified": b.geojson_simplified,
        }
        for b in rows
    ]
