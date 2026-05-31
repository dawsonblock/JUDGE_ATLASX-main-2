#!/usr/bin/env python3
"""Seed the proof DB with representative audit chain and evidence snapshots.

Designed to be called by scripts/prepare_proof_db.py via uv run context.

Usage:
    JTA_DATABASE_URL=sqlite:///path/to/proof.db python backend/scripts/seed_proof_db.py
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_BACKEND_DIR = _Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_DIR))

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

from app.models.entities import AuditLog, SourceSnapshot


GENESIS_HASH = "GENESIS"


def _sha256(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _payload_hash(payload: dict | None) -> str:
    canonical = json.dumps(payload or {}, sort_keys=True, default=str)
    return _sha256(canonical.encode())


def _row_digest(row_dict: dict, prev_hash: str) -> str:
    """Compute chain-v2 entry_hash from a row dictionary (mirrors chain_digest.row_digest)."""
    payload_hash = row_dict.get("payload_hash")
    ts = row_dict.get("created_at")
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts = ts.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    canonical = json.dumps(
        {
            "id": row_dict["id"],
            "action": row_dict["action"],
            "actor_id": row_dict["actor_id"],
            "actor_role": row_dict.get("actor_role"),
            "actor_auth_method": row_dict.get("actor_auth_method"),
            "entity_type": row_dict.get("entity_type"),
            "entity_id": row_dict.get("entity_id"),
            "payload_hash": payload_hash,
            "before_hash": row_dict.get("before_hash"),
            "after_hash": row_dict.get("after_hash"),
            "created_at": ts,
            "chain_version": row_dict.get("chain_version", 2),
            "prev": prev_hash,
        },
        sort_keys=True,
        default=str,
    )
    return _sha256(canonical.encode())


def seed_audit_chain(db_url: str) -> None:
    """Seed >= 3 chained AuditLog rows using SQLAlchemy."""
    engine = create_engine(db_url, echo=False)
    with Session(engine) as db:
        # Remove any existing seed entries (idempotent)
        db.query(AuditLog).filter(AuditLog.actor_id == "proof-seed").delete()
        db.commit()

        now = datetime.now(timezone.utc)
        prev_hash = GENESIS_HASH
        payloads = [
            {
                "action": "source.created",
                "entity_type": "SourceRegistry",
                "entity_id": "seed-source-001",
                "actor_id": "proof-seed",
                "actor_role": "admin",
                "actor_auth_method": "jwt",
                "payload": {"source_key": "seed-source-001", "source_class": "machine_ingest"},
                "before_hash": None,
                "after_hash": _sha256(b"seed-source-001"),
            },
            {
                "action": "ingestion.run.completed",
                "entity_type": "IngestionRun",
                "entity_id": "ingestion-run-001",
                "actor_id": "proof-seed",
                "actor_role": "system",
                "actor_auth_method": "internal",
                "payload": {"run_id": "ingestion-run-001", "status": "completed", "persisted_count": 1},
                "before_hash": _sha256(b"run-pending"),
                "after_hash": _sha256(b"run-completed"),
            },
            {
                "action": "review.approved",
                "entity_type": "ReviewItem",
                "entity_id": "review-item-001",
                "actor_id": "proof-seed",
                "actor_role": "reviewer",
                "actor_auth_method": "jwt",
                "payload": {"review_id": "review-item-001", "decision": "approved"},
                "before_hash": _sha256(b"review-pending"),
                "after_hash": _sha256(b"review-approved"),
            },
        ]

        max_id = db.query(func.max(AuditLog.id)).scalar() or 0

        for i, p in enumerate(payloads, start=1):
            ph = _payload_hash(p["payload"])
            ts = now + timedelta(seconds=i)
            row_id = int(max_id) + i
            row_dict = {
                "id": row_id,
                "action": p["action"],
                "entity_type": p["entity_type"],
                "entity_id": p["entity_id"],
                "actor_id": p["actor_id"],
                "actor_role": p["actor_role"],
                "actor_auth_method": p["actor_auth_method"],
                "payload_hash": ph,
                "before_hash": p["before_hash"],
                "after_hash": p["after_hash"],
                "created_at": ts,
                "chain_version": 2,
            }
            entry_hash = _row_digest(row_dict, prev_hash)

            entry = AuditLog(
                id=row_id,
                action=p["action"],
                entity_type=p["entity_type"],
                entity_id=p["entity_id"],
                actor_id=p["actor_id"],
                actor_type="user",
                actor_role=p["actor_role"],
                actor_auth_method=p["actor_auth_method"],
                payload=p["payload"],
                created_at=ts,
                payload_hash=ph,
                before_hash=p["before_hash"],
                after_hash=p["after_hash"],
                previous_entry_hash=prev_hash,
                entry_hash=entry_hash,
                chain_version=2,
            )
            db.add(entry)
            prev_hash = entry_hash

        db.commit()
        print(f"  Seeded {len(payloads)} audit chain entries (chain_version=2)")


def seed_evidence_snapshots(db_url: str) -> None:
    """Seed >= 3 SourceSnapshot rows for meaningful evidence verification."""
    engine = create_engine(db_url, echo=False)
    with Session(engine) as db:
        # Idempotent — remove previous seed snapshots
        db.query(SourceSnapshot).filter(
            SourceSnapshot.source_key == "proof-seed"
        ).delete()
        db.commit()

        now = datetime.now(timezone.utc)
        snapshots = [
            {
                "source_key": "proof-seed",
                "source_url": "https://proof.example.local/seed/verified",
                "content": b"Seed verified evidence content for proof gate.",
                "http_status": 200,
                "review_status": "verified",
            },
            {
                "source_key": "proof-seed",
                "source_url": "https://proof.example.local/seed/rejected",
                "content": b"Seed rejected evidence content for exclusion test.",
                "http_status": 200,
                "review_status": "rejected",
            },
            {
                "source_key": "proof-seed",
                "source_url": "https://proof.example.local/seed/quarantined",
                "content": b"Seed quarantined evidence content for exclusion test.",
                "http_status": 200,
                "review_status": "quarantined",
            },
        ]

        for i, s in enumerate(snapshots, start=1):
            content_bytes = s["content"]
            ch = _sha256(content_bytes)
            snap = SourceSnapshot(
                source_key=s["source_key"],
                source_url=s["source_url"],
                fetched_at=now + timedelta(seconds=i),
                content_hash=ch,
                original_content_hash=ch,
                stored_content_hash=ch,
                raw_content=content_bytes.decode("utf-8", errors="replace"),
                http_status=s["http_status"],
                content_type="text/plain",
                storage_backend="db",
                content_size_bytes=len(content_bytes),
                stored_size_bytes=len(content_bytes),
                is_truncated=False,
                created_at=now + timedelta(seconds=i),
            )
            db.add(snap)

        db.commit()
        print(f"  Seeded {len(snapshots)} evidence snapshots (verified, rejected, quarantined)")


def main() -> int:
    db_url = os.environ.get("JTA_DATABASE_URL")
    if not db_url:
        print("ERROR: JTA_DATABASE_URL environment variable not set")
        return 1

    try:
        seed_audit_chain(db_url)
        seed_evidence_snapshots(db_url)
        return 0
    except Exception as e:
        print(f"ERROR during seeding: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
