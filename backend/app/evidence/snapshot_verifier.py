"""Re-compute and compare SourceSnapshot content hashes on demand."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.entities import SourceSnapshot


@dataclass
class SnapshotVerificationResult:
    snapshot_id: int
    ok: bool
    stored_hash: str | None
    computed_hash: str | None
    mismatch: bool = False
    reason: str | None = None


def verify_snapshot(db: Session, snapshot_id: int) -> SnapshotVerificationResult:
    """Compare stored hash against re-computed hash of raw content."""
    snapshot = db.query(SourceSnapshot).filter(SourceSnapshot.id == snapshot_id).first()
    if snapshot is None:
        return SnapshotVerificationResult(
            snapshot_id=snapshot_id,
            ok=False,
            stored_hash=None,
            computed_hash=None,
            reason="not_found",
        )

    raw = getattr(snapshot, "raw_content", None)
    if raw is None:
        return SnapshotVerificationResult(
            snapshot_id=snapshot_id,
            ok=False,
            stored_hash=snapshot.content_hash,
            computed_hash=None,
            reason="no_raw_content",
        )

    computed = hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()
    stored = snapshot.content_hash
    ok = stored == computed

    return SnapshotVerificationResult(
        snapshot_id=snapshot_id,
        ok=ok,
        stored_hash=stored,
        computed_hash=computed,
        mismatch=not ok,
        reason=None if ok else "hash_mismatch",
    )


def verify_all_snapshots(db: Session) -> list[SnapshotVerificationResult]:
    """Verify every snapshot; return list of results (failures first)."""
    ids = [row[0] for row in db.query(SourceSnapshot.id).all()]
    results = [verify_snapshot(db, sid) for sid in ids]
    results.sort(key=lambda r: (r.ok, r.snapshot_id))
    return results
