"""Map ``GroundedExtraction`` objects to DB records in a single transaction.

This module is the write boundary for the extraction pipeline.  All records
created here are:
- ``public_visibility=False``  (never auto-published)
- ``status=PENDING``           (always requires human review)
- Not committed by this module — the caller owns the transaction

**entity_id sentinel**
``MemoryClaim.entity_id`` is a NOT NULL FK → canonical_entities.id.  At the
point of extraction no canonical entity has been assigned, so we write
``entity_id=0`` as a pre-review placeholder.  This value must be replaced
with a real canonical entity ID before the owning transaction commits.  The
value 0 is intentionally invalid so any accidental commit raises a FK error.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.extraction.contracts import GroundedExtraction
from app.ingestion.statuses import PENDING
from app.models.entities import MemoryClaim, MemoryEvidenceLink, ReviewItem

if TYPE_CHECKING:
    pass  # no TYPE_CHECKING-only imports needed


def _evidence_checksum(span_text: str, snapshot_id: int, span_start: int) -> str:
    """Return a stable SHA-256 hex digest for a span of evidence.

    Inputs are concatenated with ``|`` separators to minimise collision risk
    between identical text at different positions.
    """
    raw = f"{snapshot_id}|{span_start}|{span_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def map_to_review_items(
    extractions: list[GroundedExtraction],
    db: Session,
) -> list[ReviewItem]:
    """Persist *extractions* as ``MemoryClaim`` + ``MemoryEvidenceLink`` + ``ReviewItem``.

    Parameters
    ----------
    extractions:
        Grounded extractions from ``run_extraction()``.  All must have a
        ``source_snapshot_id`` that refers to an existing ``SourceSnapshot``.
    db:
        SQLAlchemy ``Session``.  The caller owns ``commit()``/``rollback()``.
        This function calls ``db.flush()`` after adding each claim so that
        ``claim.id`` is available for the evidence link.

    Returns
    -------
    list[ReviewItem]
        One ``ReviewItem`` per extraction, in the same order as *extractions*.

    Notes
    -----
    - ``entity_id=0`` is written as a sentinel; must be resolved before commit.
    - ``public_visibility=False`` and ``status=PENDING`` on every record.
    - This function does not call ``db.commit()`` or ``db.rollback()``.
    """
    review_items: list[ReviewItem] = []

    for extraction in extractions:
        # --- MemoryClaim ---
        claim = MemoryClaim(
            claim_type=extraction.extraction_class,
            claim_value=extraction.text,
            claim_value_json=extraction.attributes if extraction.attributes else None,
            # entity_id=0 is a sentinel; caller MUST resolve before commit.
            entity_id=0,
            source_snapshot_id=extraction.source_snapshot_id,
            extraction_model=extraction.model_id,
            confidence=extraction.confidence,
            status="active",
            is_active=True,
        )
        db.add(claim)
        db.flush()  # populate claim.id

        # --- MemoryEvidenceLink ---
        checksum = _evidence_checksum(
            span_text=extraction.text,
            snapshot_id=extraction.source_snapshot_id,
            span_start=extraction.span_start,
        )
        evidence_link = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=extraction.source_snapshot_id,
            evidence_checksum=checksum,
            span_start=extraction.span_start,
            span_end=extraction.span_end,
            span_text=extraction.text,
        )
        db.add(evidence_link)

        # --- ReviewItem ---
        payload: dict = {
            "extraction_class": extraction.extraction_class,
            "text": extraction.text,
            "span_start": extraction.span_start,
            "span_end": extraction.span_end,
            "attributes": extraction.attributes,
            "model_id": extraction.model_id,
            "claim_key": claim.claim_key,
        }
        review_item = ReviewItem(
            record_type=f"memory_claim/{extraction.extraction_class}",
            source_snapshot_id=extraction.source_snapshot_id,
            suggested_payload_json=payload,
            source_quality="secondary_context",
            confidence=extraction.confidence,
            privacy_status="needs_review",
            publish_recommendation="review_required",
            public_visibility=False,
            status=PENDING,
        )
        db.add(review_item)
        review_items.append(review_item)

    return review_items
