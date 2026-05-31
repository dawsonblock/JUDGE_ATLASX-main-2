"""Admin endpoints for evidence store management."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.admin import require_admin_token
from app.auth.actor import AdminActor
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import SourceSnapshot
from app.services.evidence_store_validation import validate_evidence_store_root
from app.services.snapshot_writer import read_snapshot_content

router = APIRouter(prefix="/api/admin/evidence-store", tags=["admin"])


@router.get("/status")
def get_evidence_store_status(
    _: AdminActor = Depends(require_admin_token),
    probe: bool = Query(False, description="Run write/hash probe before returning status"),
) -> dict:
    """Get evidence store configuration and validation status.
    
    Response does not include full filesystem path for security.
    """
    settings = get_settings()
    
    if not settings.evidence_store_root:
        return {
            "enabled": False,
            "root_configured": False,
            "storage_layout": None,
            "probe_ok": None,
            "probe_checked": False,
        }
    
    try:
        result = validate_evidence_store_root(
            settings.evidence_store_root,
            required=False,
            probe_write=probe,
            repo_root=str(Path(__file__).resolve().parents[4]),
        )
        return {
            "enabled": result["enabled"],
            "root_configured": True,
            "storage_layout": "snapshots/sha256/AA/BB/hash.bin",
            "probe_ok": result.get("reason") is None,
            "probe_checked": probe,
        }
    except RuntimeError as e:
        return {
            "enabled": False,
            "root_configured": True,
            "storage_layout": "snapshots/sha256/AA/BB/hash.bin",
            "probe_ok": False,
            "probe_checked": probe,
            "error": str(e),
        }


@router.get("/verify/{snapshot_id}")
def verify_snapshot(
    snapshot_id: int,
    _: AdminActor = Depends(require_admin_token),
    db: Session = Depends(get_db),
) -> dict:
    """Verify the integrity of a stored snapshot by recomputing its hash.

    Compares the SHA-256 of the on-disk (or DB-stored) content against
    the hash recorded at ingestion time. Returns 'ok' if they match,
    'corrupted' if they differ, or 'unavailable' if the content cannot
    be read.
    """
    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    content = read_snapshot_content(db, snapshot)
    if content is None:
        return {
            "snapshot_id": snapshot_id,
            "status": "unavailable",
            "detail": "Content not readable from storage backend",
            "storage_backend": snapshot.storage_backend,
            "is_truncated": snapshot.is_truncated,
        }

    actual_hash = hashlib.sha256(content).hexdigest()
    integrity_ok = actual_hash == snapshot.original_content_hash
    return {
        "snapshot_id": snapshot_id,
        "status": "ok" if integrity_ok else "corrupted",
        "stored_hash": snapshot.original_content_hash,
        "actual_hash": actual_hash,
        "is_truncated": snapshot.is_truncated,
        "storage_backend": snapshot.storage_backend,
    }
