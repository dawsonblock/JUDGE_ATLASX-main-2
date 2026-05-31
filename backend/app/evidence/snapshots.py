"""Evidence snapshot retrieval with hash verification."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.evidence.hashing import EvidenceIntegrityError, compute_hash
from app.models.entities import SourceSnapshot
from app.services.snapshot_writer import read_snapshot_content


def retrieve_and_verify(
    snapshot_id: int,
    db: Session,
) -> tuple[SourceSnapshot, bytes]:
    """Fetch a :class:`SourceSnapshot` and verify its stored hash.

    Args:
        snapshot_id: Primary key of the snapshot to retrieve.
        db: Active database session.

    Returns:
        ``(snapshot, content_bytes)`` where *content_bytes* is the raw content
        as originally stored.

    Raises:
        ValueError: If *snapshot_id* does not exist.
        EvidenceIntegrityError: If the SHA-256 of the retrieved bytes does not
            match ``snapshot.original_content_hash``.
    """
    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError(f"SourceSnapshot {snapshot_id} not found")

    content = read_snapshot_content(db, snapshot)
    if content is None:
        raise ValueError(f"SourceSnapshot {snapshot_id} has no stored content")

    actual = compute_hash(content)
    expected = snapshot.original_content_hash or snapshot.content_hash
    if actual != expected:
        raise EvidenceIntegrityError(snapshot_id, expected, actual)

    return snapshot, content
