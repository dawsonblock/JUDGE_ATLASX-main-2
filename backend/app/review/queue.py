"""Read-only helpers to query the review queue."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ReviewItem
from app.ingestion.statuses import PENDING


def get_pending_queue(db: Session, limit: int = 100) -> list[ReviewItem]:
    """Return up to *limit* ReviewItems with status=pending, oldest first."""
    return (
        db.query(ReviewItem)
        .filter(ReviewItem.status == PENDING)
        .order_by(ReviewItem.created_at.asc())
        .limit(limit)
        .all()
    )


def get_review_item(db: Session, item_id: int) -> ReviewItem | None:
    """Return a single ReviewItem by primary key, or None."""
    return db.query(ReviewItem).filter(ReviewItem.id == item_id).first()
