"""Canonical snapshot writer service for source snapshots.

This service provides a unified interface for writing source snapshots,
supporting both filesystem storage (via EvidenceStore) and database fallback.
All snapshot writes should go through this service to ensure consistency.

Evidence integrity contract:
- The hash stored in content_hash / original_content_hash is ALWAYS the hash
  of the FULL, un-truncated content.
- stored_content_hash is the hash of what is actually stored; it MUST equal
  original_content_hash on every successful write (because read_snapshot_content()
  returns the original bytes in all storage paths).
- is_truncated MUST always be False after a successful write.
- If content is too large for DB storage and no evidence store is configured,
  write_snapshot() raises ValueError rather than creating a partial snapshot.

DB storage encoding:
- Text content that round-trips cleanly through UTF-8 is stored as-is.
- Binary content (e.g. PDFs, non-UTF-8 bytes) that would be damaged by UTF-8
  decoding is stored as 'base64:<base64-encoded-bytes>' so that
  read_snapshot_content() can return the original bytes exactly.
"""

import base64
import hashlib
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import SourceSnapshot
from app.services.evidence_store import EvidenceStore

if TYPE_CHECKING:
    pass


# Maximum size for DB storage (1MB)
MAX_DB_SIZE = 1024 * 1024

# Prefix used to flag base64-encoded binary DB content.
_BASE64_PREFIX = "base64:"


def _encode_for_db(content_bytes: bytes) -> str:
    """Encode raw bytes for lossless storage in a Text column.

    Returns the UTF-8 string if the bytes round-trip safely (i.e., the
    decode/re-encode cycle produces identical bytes).  Otherwise returns a
    ``base64:<base64-encoded-bytes>`` string so that no byte is lost.

    The ``base64:`` prefix is defined by :data:`_BASE64_PREFIX` and is
    recognised by :func:`_decode_from_db`.
    """
    try:
        text = content_bytes.decode("utf-8")
        # Verify the round-trip is lossless
        if text.encode("utf-8") == content_bytes:
            return text
    except UnicodeDecodeError:
        pass
    return _BASE64_PREFIX + base64.b64encode(content_bytes).decode("ascii")


def _decode_from_db(raw_content: str) -> bytes:
    """Decode a value previously stored by :func:`_encode_for_db`.

    Args:
        raw_content: The string stored in :attr:`SourceSnapshot.raw_content`.
            Either a plain UTF-8 string or a ``base64:<data>`` encoded string.

    Returns:
        The original raw bytes, identical to what was passed to
        :func:`_encode_for_db`.
    """
    if raw_content.startswith(_BASE64_PREFIX):
        return base64.b64decode(raw_content[len(_BASE64_PREFIX) :])
    return raw_content.encode("utf-8")


def write_snapshot(
    db: Session,
    source_url: str,
    fetched_at: datetime,
    content: bytes | str,
    extracted_text: str | None = None,
    headers: dict | None = None,
    http_status: int | None = None,
    content_type: str | None = None,
    error_message: str | None = None,
    ingestion_run_id: int | None = None,
    extractor_name: str | None = None,
    extractor_version: str | None = None,
    source_key: str | None = None,
) -> SourceSnapshot:
    """Write a source snapshot using canonical storage logic.

    Evidence integrity: stored content always matches the stored hash.
    If content is too large for DB and no evidence store is configured,
    raises ValueError rather than creating a partial snapshot.

    Args:
        db: Database session
        source_url: URL of the source
        fetched_at: Timestamp when content was fetched
        content: Raw content as bytes or string
        extracted_text: Extracted plain text (optional)
        headers: HTTP headers dict (optional)
        http_status: HTTP status code (optional)
        content_type: Content-Type header (optional)
        error_message: Error message if fetch failed (optional)
        ingestion_run_id: ID of the ingestion run that created this snapshot (optional)
        extractor_name: Name of the text extractor used (optional)
        extractor_version: Version of the text extractor used (optional)
        source_key: Source registry key identifying the crawl target (optional)

    Returns:
        SourceSnapshot: Created snapshot record (not yet committed)

    Raises:
        ValueError: If content exceeds MAX_DB_SIZE and no evidence store is configured.
    """
    # Normalise input to bytes
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    # Guard: reject empty payloads from named sources so silent zero-byte
    # snapshots cannot mask adapter failures.
    if not content_bytes and source_key is not None:
        raise ValueError(
            f"Empty content from {source_key!r}: adapter produced no bytes. "
            "Refusing to write a zero-byte snapshot."
        )

    # Compute SHA256 hash of full original content
    original_hash = hashlib.sha256(content_bytes).hexdigest()
    content_size = len(content_bytes)

    # Determine storage backend
    evidence_root = get_settings().evidence_store_root

    if content_size <= MAX_DB_SIZE:
        # Content fits in DB. Encode losslessly so read_snapshot_content()
        # can recover the original bytes exactly (important for binary formats).
        storage_backend = "db"
        storage_path = None
        raw_content = _encode_for_db(content_bytes)
        stored_hash = original_hash
        stored_size = content_size
    elif evidence_root:
        # Content is large; write to filesystem evidence store.
        # No decoding needed — bytes are stored directly.
        evidence_store = EvidenceStore(root_path=evidence_root)
        storage_path = evidence_store.write_snapshot(content_bytes, original_hash)
        storage_backend = "filesystem"
        raw_content = None  # Don't duplicate in DB
        stored_hash = original_hash
        stored_size = content_size
    else:
        # Content too large and no evidence store — refuse to create partial snapshot
        raise ValueError(
            f"Content size {content_size} bytes exceeds MAX_DB_SIZE ({MAX_DB_SIZE}) "
            "and JTA_EVIDENCE_STORE_ROOT is not configured. "
            "Configure an evidence store to handle large content, or ensure the "
            "fetcher enforces a size limit before calling write_snapshot()."
        )

    # Create SourceSnapshot with full integrity metadata
    snapshot = SourceSnapshot(
        source_url=source_url,
        fetched_at=fetched_at,
        content_hash=original_hash,
        raw_content=raw_content,
        extracted_text=extracted_text,
        http_status=http_status,
        content_type=content_type,
        headers_json=json.dumps(headers) if headers else None,
        error_message=error_message,
        storage_backend=storage_backend,
        storage_path=storage_path,
        ingestion_run_id=ingestion_run_id,
        # Evidence integrity fields
        original_content_hash=original_hash,
        stored_content_hash=stored_hash,
        content_size_bytes=content_size,
        stored_size_bytes=stored_size,
        is_truncated=False,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        source_key=source_key,
    )

    db.add(snapshot)
    # Flush to populate snapshot.id so the custody log FK resolves.
    db.flush()
    # Record the "created" custody event (append-only provenance chain).
    from app.evidence.provenance import record_custody_event  # noqa: PLC0415

    record_custody_event(db, snapshot, "created")
    # Caller is responsible for commit/refresh

    return snapshot


def read_snapshot_content(db: Session, snapshot: SourceSnapshot) -> bytes | None:
    """Read snapshot content from appropriate storage backend.

    Args:
        db: Database session
        snapshot: SourceSnapshot record

    Returns:
        Raw content as bytes, or None if unavailable
    """
    if snapshot.storage_backend == "filesystem" and snapshot.storage_path:
        evidence_root = get_settings().evidence_store_root
        if not evidence_root:
            raise OSError(
                f"read_snapshot_content: JTA_EVIDENCE_STORE_ROOT not set "
                f"for filesystem snapshot {snapshot.id}"
            )
        evidence_store = EvidenceStore(root_path=evidence_root)
        content = evidence_store.read_snapshot(snapshot.storage_path)
        if content is None:
            raise OSError(
                f"read_snapshot_content: file not found in evidence store "
                f"for snapshot {snapshot.id}: {snapshot.storage_path}"
            )
        return content

    # DB path — decode the stored representation back to original bytes
    if snapshot.raw_content:
        return _decode_from_db(snapshot.raw_content)

    return None
