"""Export source snapshots to JSONL format.

Each exported record includes all provenance fields required for
chain-of-custody verification without the live database.

Usage::

    from app.archive.export_snapshots import export_snapshots_to_jsonl
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        count = export_snapshots_to_jsonl(db, Path("artifacts/exports/source_snapshots.jsonl"))
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.policies.state_model import (
    PublicationState,
    archive_publication_status_for_state,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def export_snapshots_to_jsonl(db: "Session", out_path: Path) -> int:
    """Export all SourceSnapshot records to a JSONL file.

    Parameters
    ----------
    db:
        Active SQLAlchemy session.
    out_path:
        Destination JSONL file path.  Parent directories are created if needed.

    Returns
    -------
    int
        Number of records exported.
    """
    from app.models.entities import SourceSnapshot

    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for snap in db.query(SourceSnapshot).yield_per(500):
            # Compute SHA-256 of raw content for archive verification.
            raw_bytes_sha256: str | None = None
            if snap.content_hash:
                raw_bytes_sha256 = snap.content_hash  # already a hash

            record = {
                "record_id": str(snap.id),
                "source_key": snap.source_key,
                "source_url": snap.source_url,
                "captured_at": (
                    snap.fetched_at.isoformat() if snap.fetched_at else None
                ),
                "content_hash": snap.content_hash,
                "evidence_type": "source_snapshot",
                "review_status": "captured",
                "publication_status": archive_publication_status_for_state(
                    PublicationState.DRAFT
                ).value,
                "fetch_url": snap.source_url,
                "fetch_http_status": snap.http_status,
                "fetch_content_type": snap.content_type,
                "raw_bytes_sha256": raw_bytes_sha256,
                "payload": {
                    "extracted_text": snap.extracted_text,
                    "storage_backend": snap.storage_backend,
                    "ingestion_run_id": snap.ingestion_run_id,
                    "extractor_name": snap.extractor_name,
                    "is_truncated": snap.is_truncated,
                },
            }
            fh.write(json.dumps(record, default=str) + "\n")
            count += 1

    logger.info("Exported %d source snapshots to %s", count, out_path)
    return count
