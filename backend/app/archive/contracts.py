"""Archive export contracts for THE-JUDGE platform.

Defines the stable record schemas used in JSONL exports.
Every exported record must include provenance fields so the archive
is self-describing and verifiable without the live database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ArchiveSnapshotRecord:
    """A single source snapshot record for JSONL export.

    Includes all provenance fields required for chain-of-custody verification.
    """

    record_id: str
    source_key: str
    source_url: str | None
    captured_at: str  # ISO-8601 UTC
    content_hash: str | None
    evidence_type: str  # e.g. "court_decision", "legislation", "crime_statistics"
    review_status: str  # e.g. "pending", "approved", "rejected"
    publication_status: str  # e.g. "unpublished", "public"
    payload: dict[str, Any] = field(default_factory=dict)
    # Provenance fields
    fetch_url: str | None = None
    fetch_http_status: int | None = None
    fetch_content_type: str | None = None
    raw_bytes_sha256: str | None = None  # SHA-256 of raw_snapshot_bytes


@dataclass
class ArchiveMemoryClaimRecord:
    """A single memory claim record for JSONL export."""

    record_id: str
    source_key: str
    claim_type: str
    claim_text: str
    status: str  # active, invalidated, disputed, superseded, needs_review
    confidence_score: float
    created_at: str  # ISO-8601 UTC
    updated_at: str | None
    evidence_snapshot_ids: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
