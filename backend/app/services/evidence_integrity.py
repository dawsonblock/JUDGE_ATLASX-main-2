"""Evidence integrity verification and immutability enforcement.

Provides:
- ``verify_snapshot_integrity`` – re-hash stored content, compare to DB hash
- ``verify_all_recent_snapshots`` – bulk integrity check for recent snapshots
- ``record_custody_event`` – thin wrapper over provenance.record_custody_event
- ``assert_snapshot_append_only_change`` – raise ImmutabilityViolation on
  immutable-field mutation between two snapshot states
- SQLAlchemy ``before_update`` event listener blocking direct flush-time
  mutations to the immutable set of fields
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.evidence.hashing import compute_hash
from app.models.entities import SourceSnapshot
from app.services.snapshot_writer import read_snapshot_content
from sqlalchemy import desc, event
from sqlalchemy.orm import Session, attributes

if TYPE_CHECKING:
    from app.services.evidence_store import EvidenceStore


# ---------------------------------------------------------------------------
# Immutable field catalog
# ---------------------------------------------------------------------------

#: Fields on :class:`SourceSnapshot` that must never change after creation.
IMMUTABLE_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "content_hash",
    "source_url",
    "fetched_at",
    "raw_content",
    "stored_content_hash",
    "original_content_hash",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ImmutabilityViolation(Exception):
    """Raised when an attempt is made to mutate an immutable snapshot field."""

    def __init__(self, field_name: str, snapshot_id: int | None = None) -> None:
        self.field_name = field_name
        self.snapshot_id = snapshot_id
        id_part = (
            f" on SourceSnapshot id={snapshot_id}" if snapshot_id is not None else ""
        )
        super().__init__(f"Immutable field '{field_name}' cannot be modified{id_part}")


# ---------------------------------------------------------------------------
# IntegrityResult
# ---------------------------------------------------------------------------


class IntegrityResult:
    """Result of a single snapshot integrity check."""

    __slots__ = ("snapshot_id", "ok", "expected_hash", "actual_hash", "error_message")

    def __init__(
        self,
        snapshot_id: int,
        ok: bool,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.snapshot_id = snapshot_id
        self.ok = ok
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.error_message = error_message

    def __repr__(self) -> str:  # pragma: no cover
        status = "PASS" if self.ok else "FAIL"
        return f"IntegrityResult(snapshot_id={self.snapshot_id}, status={status})"


# ---------------------------------------------------------------------------
# Integrity verification
# ---------------------------------------------------------------------------


def verify_snapshot_integrity(
    snapshot_id: int,
    db: Session,
    store: EvidenceStore | None = None,
) -> IntegrityResult:
    """Re-hash stored snapshot content and compare to the recorded hash.

    Args:
        snapshot_id: Primary key of the :class:`SourceSnapshot` to verify.
        db: Active SQLAlchemy session.
        store: Optional :class:`EvidenceStore` for filesystem-backed snapshots.
            If ``None`` the function still reads DB-backed snapshots;
            filesystem-backed snapshots without a store are reported as errors.

    Returns:
        :class:`IntegrityResult` with ``ok=True`` if the hash matches.
    """
    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        return IntegrityResult(
            snapshot_id=snapshot_id,
            ok=False,
            error_message=f"SourceSnapshot {snapshot_id} not found",
        )

    expected = snapshot.content_hash

    try:
        content = read_snapshot_content(db, snapshot)
    except OSError as exc:
        return IntegrityResult(
            snapshot_id=snapshot_id,
            ok=False,
            expected_hash=expected,
            error_message=str(exc),
        )

    if content is None:
        return IntegrityResult(
            snapshot_id=snapshot_id,
            ok=False,
            expected_hash=expected,
            error_message="No content available for integrity check",
        )

    actual = compute_hash(content)
    ok = actual == expected

    return IntegrityResult(
        snapshot_id=snapshot_id,
        ok=ok,
        expected_hash=expected,
        actual_hash=actual,
        error_message=(
            None
            if ok
            else f"Hash mismatch: expected {expected[:16]}…, got {actual[:16]}…"
        ),
    )


def verify_all_recent_snapshots(
    db: Session,
    store: EvidenceStore | None = None,
    limit: int = 100,
) -> list[IntegrityResult]:
    """Run integrity checks on the *limit* most recently created snapshots.

    Args:
        db: Active SQLAlchemy session.
        store: Optional :class:`EvidenceStore` for filesystem-backed content.
        limit: Maximum number of snapshots to check.  Defaults to 100.

    Returns:
        List of :class:`IntegrityResult`, one per snapshot checked.
    """
    snapshots = (
        db.query(SourceSnapshot)
        .order_by(desc(SourceSnapshot.created_at))
        .limit(limit)
        .all()
    )
    return [verify_snapshot_integrity(snap.id, db, store) for snap in snapshots]


# ---------------------------------------------------------------------------
# Custody event wrapper
# ---------------------------------------------------------------------------


def record_custody_event(
    snapshot_id: int,
    actor: str,
    action: str,
    db: Session,
) -> None:
    """Append a chain-of-custody entry for the given snapshot.

    Thin wrapper around :func:`app.evidence.provenance.record_custody_event`
    that accepts *snapshot_id* (int) rather than the ORM instance.

    Args:
        snapshot_id: Primary key of the target :class:`SourceSnapshot`.
        actor: Identifier of the acting principal (e.g. user ID or ``"system"``).
        action: One of the strings in :data:`app.evidence.provenance.CUSTODY_ACTIONS`.
        db: Active SQLAlchemy session.

    Raises:
        ValueError: If the snapshot does not exist.
    """
    # Late import avoids potential circular-import cycles at module load time.
    from app.evidence.provenance import record_custody_event as _record  # noqa: PLC0415

    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError(f"SourceSnapshot {snapshot_id} not found")

    _record(db, snapshot, action, actor=actor)


# ---------------------------------------------------------------------------
# Append-only field assertion
# ---------------------------------------------------------------------------


def assert_snapshot_append_only_change(
    old_snap: SourceSnapshot,
    new_snap: SourceSnapshot,
) -> None:
    """Assert that no immutable field was altered between two snapshot states.

    Compares each field in :data:`IMMUTABLE_SNAPSHOT_FIELDS` across *old_snap*
    and *new_snap*.  Both arguments should represent the same logical snapshot
    at different points in time (e.g. before and after a flush).

    Args:
        old_snap: Snapshot state before the proposed change.
        new_snap: Snapshot state after the proposed change.

    Raises:
        :class:`ImmutabilityViolation`: If any immutable field differs between
            the two states.
    """
    snap_id = getattr(old_snap, "id", None)
    for field_name in IMMUTABLE_SNAPSHOT_FIELDS:
        old_val = getattr(old_snap, field_name, None)
        new_val = getattr(new_snap, field_name, None)
        if old_val != new_val:
            raise ImmutabilityViolation(field_name=field_name, snapshot_id=snap_id)


# ---------------------------------------------------------------------------
# SQLAlchemy before_update event listener
# ---------------------------------------------------------------------------


def _block_immutable_update(
    mapper,  # noqa: ANN001 – standard SQLAlchemy event signature
    connection,  # noqa: ANN001
    target: SourceSnapshot,
) -> None:
    """Block any flush-time mutation of immutable :class:`SourceSnapshot` fields.

    Registered as a SQLAlchemy ``before_update`` event listener so that direct
    attribute assignments that reach ``session.flush()`` are intercepted before
    any SQL UPDATE is emitted.

    Args:
        mapper: SQLAlchemy mapper (unused, required by event signature).
        connection: Database connection (unused, required by event signature).
        target: The :class:`SourceSnapshot` instance being flushed.

    Raises:
        :class:`ImmutabilityViolation`: If any immutable field has been changed.
    """
    for field_name in IMMUTABLE_SNAPSHOT_FIELDS:
        hist = attributes.get_history(target, field_name)
        # hist.deleted holds the pre-change value; hist.added holds the new value.
        # Only raise if both are present AND the values actually differ — a
        # no-op re-assignment of the same value does not count as a mutation.
        if hist.deleted and hist.added and hist.deleted[0] != hist.added[0]:
            raise ImmutabilityViolation(
                field_name=field_name,
                snapshot_id=getattr(target, "id", None),
            )


event.listen(SourceSnapshot, "before_update", _block_immutable_update)


# ---------------------------------------------------------------------------
# Orphan detection and evidence chain retrieval  (Sprint D — item 3.2)
# ---------------------------------------------------------------------------


def detect_orphaned_snapshots(db: Session) -> list[int]:
    """Return IDs of :class:`SourceSnapshot` rows not linked to any
    :class:`~app.models.entities.ReviewItem`.

    A snapshot is considered *orphaned* when no ``ReviewItem.source_snapshot_id``
    references it.  Orphaned snapshots represent evidence that was fetched but
    never entered the review pipeline — they should be investigated before
    any release gate.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        Sorted list of orphaned snapshot primary-key IDs (may be empty).
    """
    from app.models.entities import ReviewItem  # noqa: PLC0415
    from sqlalchemy import exists, not_, select  # noqa: PLC0415

    stmt = (
        select(SourceSnapshot.id)
        .where(
            not_(
                exists(
                    select(ReviewItem.id).where(
                        ReviewItem.source_snapshot_id == SourceSnapshot.id
                    )
                )
            )
        )
        .order_by(SourceSnapshot.id)
    )
    return list(db.scalars(stmt))


def get_evidence_chain(
    snapshot_id: int,
    db: Session,
) -> dict[str, object] | None:
    """Return the full evidence chain for a snapshot.

    Assembles a structured dict containing the snapshot metadata, its
    chain-of-custody log, and any linked :class:`~app.models.entities.ReviewItem`
    rows.  Returns ``None`` if the snapshot does not exist.

    Args:
        snapshot_id: Primary key of the :class:`SourceSnapshot` to retrieve.
        db: Active SQLAlchemy session.

    Returns:
        A dict with keys ``snapshot``, ``custody_log``, and ``review_items``,
        or ``None`` if the snapshot is not found.
    """
    from app.models.entities import ChainOfCustodyLog, ReviewItem  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        return None

    custody_rows = db.scalars(
        select(ChainOfCustodyLog)
        .where(ChainOfCustodyLog.snapshot_id == snapshot_id)
        .order_by(ChainOfCustodyLog.created_at)
    ).all()

    review_rows = db.scalars(
        select(ReviewItem)
        .where(ReviewItem.source_snapshot_id == snapshot_id)
        .order_by(ReviewItem.id)
    ).all()

    return {
        "snapshot": snapshot,
        "custody_log": list(custody_rows),
        "review_items": list(review_rows),
    }
