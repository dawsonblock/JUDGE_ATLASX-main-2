"""Detect evidence corruption by scanning for known bad states."""
from __future__ import annotations

from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.models.entities import SourceSnapshot


@dataclass
class CorruptionReport:
    ok: bool
    snapshots_checked: int
    corrupted_ids: list[int] = field(default_factory=list)
    reasons: dict[int, str] = field(default_factory=dict)


def scan_snapshots(db: Session) -> CorruptionReport:
    """Scan all SourceSnapshot rows for corruption indicators."""
    rows = db.query(SourceSnapshot).all()
    corrupted: list[int] = []
    reasons: dict[int, str] = {}

    for snap in rows:
        if not snap.content_hash:
            corrupted.append(snap.id)
            reasons[snap.id] = "missing_content_hash"
        elif len(snap.content_hash) != 64:
            corrupted.append(snap.id)
            reasons[snap.id] = "invalid_hash_length"

    return CorruptionReport(
        ok=len(corrupted) == 0,
        snapshots_checked=len(rows),
        corrupted_ids=corrupted,
        reasons=reasons,
    )
