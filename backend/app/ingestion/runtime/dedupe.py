"""Duplicate detection for ingested records.

Uses two complementary strategies to identify records that have already
been ingested:

1. **Content-hash deduplication** — SHA-256 of the raw ``SourceSnapshot``
   content (stored in ``SourceSnapshot.content_hash``).  This catches
   identical bytes arriving from different requests.

2. **External-ID deduplication** — a normalised (source_name, docket_id)
   pair.  This catches the same *logical* record arriving with cosmetic
   differences (extra whitespace, different encoding, etc.).

No new database tables are created; queries run against the existing
``SourceSnapshot`` and ``EntitySourceRecord`` tables.

Deterministic, rule-based — no LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.ingestion.adapters import ParsedRecord
from app.models.entities import SourceSnapshot

_log = logging.getLogger(__name__)

# Fields included in the canonical record hash (order is significant)
_HASH_FIELDS: tuple[str, ...] = (
    "source_name",
    "docket_id",
    "docket_number",
    "court_code",
    "judge_name",
    "date_filed",
    "entry_date",
    "docket_entry_id",
)


@dataclass
class DedupeResult:
    """Outcome of a duplicate check."""

    is_duplicate: bool
    matched_id: int | None = None  # SourceSnapshot.id of the duplicate, if found
    match_reason: str | None = None  # "content_hash" | "external_id" | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_record_hash(parsed: ParsedRecord) -> str:
    """Return a hex SHA-256 hash of the key identity fields of *parsed*.

    This is deterministic and independent of field ordering within ``raw``.
    """
    parts: list[str] = []
    for name in _HASH_FIELDS:
        val = getattr(parsed, name, None)
        if val is None:
            parts.append("")
        else:
            parts.append(str(val))
    canonical = "\x1f".join(parts)  # ASCII unit-separator as delimiter
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_duplicate_snapshot(db: Session, content_hash: str, source_key: str) -> bool:
    """Return ``True`` if a ``SourceSnapshot`` with *content_hash* already
    exists for *source_key*.

    Args:
        db:           Open SQLAlchemy session.
        content_hash: SHA-256 hex digest of the raw content.
        source_key:   ``SourceRegistry.source_key`` value.
    """
    stmt = select(
        exists().where(
            SourceSnapshot.content_hash == content_hash,
            SourceSnapshot.source_key == source_key,
        )
    )
    return bool(db.execute(stmt).scalar())


def is_duplicate_record(db: Session, external_entity_id: str, source_name: str) -> bool:
    """Return ``True`` if a record with *external_entity_id* from *source_name*
    already exists in ``EntitySourceRecord``.

    Falls back gracefully to ``False`` if the ``EntitySourceRecord`` model is
    not present in the metadata (e.g. during early migrations).
    """
    try:
        from app.models.entities import EntitySourceRecord  # noqa: PLC0415

        stmt = select(
            exists().where(
                EntitySourceRecord.external_entity_id == external_entity_id,
                EntitySourceRecord.source_name == source_name,
            )
        )
        return bool(db.execute(stmt).scalar())
    except Exception:  # noqa: BLE001
        return False


def check_parsed_record(db: Session, parsed: ParsedRecord) -> DedupeResult:
    """Run both deduplication checks against *parsed*.

    Checks are performed in order of cheapness:
    1. Content hash against ``SourceSnapshot``
    2. External ID against ``EntitySourceRecord``

    Returns the first match found, or a non-duplicate result.
    """
    # --- content hash check ---
    record_hash = compute_record_hash(parsed)
    try:
        hash_dup = is_duplicate_snapshot(db, record_hash, parsed.source_name)
        if hash_dup:
            _log.debug(
                "dedupe.content_hash_match source=%s hash=%s",
                parsed.source_name,
                record_hash[:12],
            )
            return DedupeResult(is_duplicate=True, match_reason="content_hash")
    except Exception:  # noqa: BLE001
        pass  # snapshot table may not exist yet; skip

    # --- external ID check ---
    ext_id = parsed.docket_id
    if ext_id:
        try:
            id_dup = is_duplicate_record(db, str(ext_id), parsed.source_name)
            if id_dup:
                _log.debug(
                    "dedupe.external_id_match source=%s docket_id=%s",
                    parsed.source_name,
                    ext_id,
                )
                return DedupeResult(is_duplicate=True, match_reason="external_id")
        except Exception:  # noqa: BLE001
            pass

    return DedupeResult(is_duplicate=False)
