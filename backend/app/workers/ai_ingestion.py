from typing import Any

from sqlalchemy.orm import Session

from app.ai.pipeline import run_ai_pipeline
from app.models.entities import ReviewItem


def ingest_raw_source(db: Session, raw_source: dict[str, Any]) -> ReviewItem:
    """Create a structured AI-assisted review item from a raw source payload."""
    item = run_ai_pipeline(db, raw_source, raw_source_id=raw_source.get("raw_source_id"))
    db.commit()
    db.refresh(item)
    return item

