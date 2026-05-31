"""Export memory claims to JSONL format.

Each exported record includes provenance links to source snapshots.

Usage::

    from app.archive.export_memory_claims import export_memory_claims_to_jsonl
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        count = export_memory_claims_to_jsonl(db, Path("artifacts/exports/memory_claims.jsonl"))
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def export_memory_claims_to_jsonl(db: "Session", out_path: Path) -> int:
    """Export all MemoryClaim records to a JSONL file.

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
    from app.models.entities import MemoryClaim, MemoryEvidenceLink

    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for claim in db.query(MemoryClaim).yield_per(500):
            # Collect linked snapshot IDs.
            evidence_ids = [
                str(link.snapshot_id)
                for link in db.query(MemoryEvidenceLink)
                .filter_by(claim_id=claim.id)
                .all()
            ]

            record = {
                "record_id": str(claim.id),
                "claim_key": claim.claim_key,
                "source_key": None,  # MemoryClaim is entity-linked, not source-linked
                "claim_type": claim.claim_type,
                "claim_text": claim.claim_value,
                "status": claim.status,
                "confidence_score": claim.confidence,
                "created_at": (
                    claim.created_at.isoformat() if claim.created_at else None
                ),
                "updated_at": (
                    claim.updated_at.isoformat() if claim.updated_at else None
                ),
                "evidence_snapshot_ids": evidence_ids,
                "payload": {
                    "entity_id": claim.entity_id,
                    "extraction_model": claim.extraction_model,
                    "is_active": claim.is_active,
                    "invalidated_at": (
                        claim.invalidated_at.isoformat()
                        if claim.invalidated_at
                        else None
                    ),
                    "invalidation_reason": claim.invalidation_reason,
                },
            }
            fh.write(json.dumps(record, default=str) + "\n")
            count += 1

    logger.info("Exported %d memory claims to %s", count, out_path)
    return count
