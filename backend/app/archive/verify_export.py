"""Verify a JSONL export file for completeness and custody-grade provenance.

Custody-grade verification requires:

For source snapshots:
  record_id, source_key, source_url, captured_at, content_hash,
  evidence_type, review_status, publication_status, payload

For memory claims:
  record_id, claim_key, claim_type, claim_text, status, confidence_score,
  created_at, evidence_snapshot_ids, payload

Usage::

    from app.archive.verify_export import verify_jsonl_export
    result = verify_jsonl_export(Path("artifacts/exports/source_snapshots.jsonl"))
    print(result.to_dict())
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.policies.state_model import ArchivePublicationStatus

logger = logging.getLogger(__name__)

# Custody-grade required fields for source snapshot exports.
# content_hash is required unless the record is explicitly marked incomplete.
_SNAPSHOT_REQUIRED_FIELDS = frozenset(
    {
        "record_id",
        "source_key",
        "source_url",
        "captured_at",
        "content_hash",
        "evidence_type",
        "review_status",
        "publication_status",
        "payload",
    }
)

# Custody-grade required fields for memory claim exports.
_MEMORY_REQUIRED_FIELDS = frozenset(
    {
        "record_id",
        "claim_key",
        "claim_type",
        "claim_text",
        "status",
        "confidence_score",
        "created_at",
        "evidence_snapshot_ids",
        "payload",
    }
)

# Fields that must be non-empty strings (not None, not "")
_SNAPSHOT_NONEMPTY_FIELDS = frozenset(
    {"record_id", "source_key", "source_url", "captured_at"}
)
_MEMORY_NONEMPTY_FIELDS = frozenset(
    {"record_id", "claim_key", "claim_type", "claim_text"}
)

# Valid review_status values for snapshot records.
# These are archive-domain statuses, not ingestion pipeline statuses.
_VALID_REVIEW_STATUSES = frozenset(
    {
        "captured",
        "approved",
        "rejected",
        "review_required",
        "pending_review",  # alias for review_required
        "quarantined_evidence",  # archive-specific quarantine label
    }
)

# Valid publication_status values (canonical archive publication states)
_VALID_PUBLICATION_STATUSES = frozenset(
    status.value for status in ArchivePublicationStatus
)


@dataclass
class VerifyResult:
    """Result of a JSONL export verification run."""

    path: str
    total_lines: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.invalid_records == 0 and self.total_lines > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "total_lines": self.total_lines,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "errors": self.errors[:20],
            "warnings": self.warnings[:20],
        }


def _check_snapshot_record(
    line_num: int, record: dict[str, Any], result: VerifyResult
) -> bool:
    """Validate a single snapshot record. Returns True if valid."""
    # Check all required fields are present.
    missing = _SNAPSHOT_REQUIRED_FIELDS - set(record.keys())
    if missing:
        result.errors.append(
            f"Line {line_num}: missing custody fields {sorted(missing)}"
        )
        return False

    # Check non-empty string fields.
    for f in _SNAPSHOT_NONEMPTY_FIELDS:
        if not record.get(f):
            result.errors.append(f"Line {line_num}: field '{f}' must be non-empty")
            return False

    # content_hash must be non-empty (unless explicitly marked incomplete).
    if not record.get("content_hash"):
        payload = record.get("payload") or {}
        if not payload.get("is_truncated") and not payload.get("incomplete"):
            result.errors.append(
                f"Line {line_num}: 'content_hash' is empty; "
                "set payload.incomplete=true if this is intentional"
            )
            return False

    # review_status must be a known value.
    review_status = record.get("review_status", "")
    if review_status and review_status not in _VALID_REVIEW_STATUSES:
        result.warnings.append(
            f"Line {line_num}: unknown review_status '{review_status}'"
        )

    # publication_status must be a known value.
    pub_status = record.get("publication_status", "")
    if pub_status and pub_status not in _VALID_PUBLICATION_STATUSES:
        result.warnings.append(
            f"Line {line_num}: unknown publication_status '{pub_status}'"
        )

    # payload must be a dict.
    if not isinstance(record.get("payload"), dict):
        result.errors.append(f"Line {line_num}: 'payload' must be a JSON object")
        return False

    return True


def _check_memory_record(
    line_num: int, record: dict[str, Any], result: VerifyResult
) -> bool:
    """Validate a single memory claim record. Returns True if valid."""
    # Check all required fields are present.
    missing = _MEMORY_REQUIRED_FIELDS - set(record.keys())
    if missing:
        result.errors.append(
            f"Line {line_num}: missing custody fields {sorted(missing)}"
        )
        return False

    # Check non-empty string fields.
    for f in _MEMORY_NONEMPTY_FIELDS:
        if not record.get(f):
            result.errors.append(f"Line {line_num}: field '{f}' must be non-empty")
            return False

    # evidence_snapshot_ids must be a list (may be empty for newly created claims).
    if not isinstance(record.get("evidence_snapshot_ids"), list):
        result.errors.append(
            f"Line {line_num}: 'evidence_snapshot_ids' must be a JSON array"
        )
        return False

    # confidence_score must be a number.
    score = record.get("confidence_score")
    if score is not None and not isinstance(score, (int, float)):
        result.errors.append(
            f"Line {line_num}: 'confidence_score' must be a number, got {type(score).__name__}"
        )
        return False

    # payload must be a dict.
    if not isinstance(record.get("payload"), dict):
        result.errors.append(f"Line {line_num}: 'payload' must be a JSON object")
        return False

    return True


def verify_jsonl_export(path: Path) -> VerifyResult:
    """Verify a JSONL export file for custody-grade provenance.

    Parameters
    ----------
    path:
        Path to the JSONL file to verify.

    Returns
    -------
    VerifyResult
        Verification result with counts and any errors found.
    """
    result = VerifyResult(path=str(path))

    if not path.exists():
        result.errors.append(f"File not found: {path}")
        return result

    # Detect record type from filename.
    is_memory = "memory" in path.name.lower()

    with path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            result.total_lines += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                result.invalid_records += 1
                result.errors.append(f"Line {line_num}: invalid JSON — {exc}")
                continue

            if not isinstance(record, dict):
                result.invalid_records += 1
                result.errors.append(f"Line {line_num}: record must be a JSON object")
                continue

            if is_memory:
                valid = _check_memory_record(line_num, record, result)
            else:
                valid = _check_snapshot_record(line_num, record, result)

            if valid:
                result.valid_records += 1
            else:
                result.invalid_records += 1

    logger.info(
        "Verified %s: %d valid, %d invalid out of %d lines (%d warnings)",
        path,
        result.valid_records,
        result.invalid_records,
        result.total_lines,
        len(result.warnings),
    )
    return result
