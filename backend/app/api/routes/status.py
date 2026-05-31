"""Public ingestion status endpoint.

GET /api/v1/status/ingestion — returns a summary of recent ingestion run
statuses so operators can confirm the pipeline is healthy without admin auth.
Only summary counts and status codes are exposed; no error message text
is included in the public response.
"""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.runtime_profile import resolve_runtime_profile
from app.db.session import get_db
from app.ingestion.statuses import (
    COMPLETED,
    COMPLETED_WITH_WARNINGS,
    FAILED,
    RUNNING,
)
from app.models.entities import IngestionRun, SourceRegistry
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.orm import Session

router = APIRouter(tags=["status"])

_HANDOFF_PATH_RE = re.compile(
    r"^\s*-\s*Path:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_HANDOFF_SHA_RE = re.compile(
    r"^\s*-\s*SHA-256:\s*([0-9a-fA-F]{64})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class StatusBucket(BaseModel):
    status: str
    count: int


class IngestionStatusResponse(BaseModel):
    window_hours: int
    total_runs: int
    running: int
    completed: int
    completed_with_warnings: int
    failed: int
    other: int
    last_run_at: datetime | None
    buckets: list[StatusBucket]


class AlphaReadinessResponse(BaseModel):
    alpha_gate_passed: bool
    production_ready: bool
    proof_chain_complete: bool
    archive_self_verifying: bool
    runnable_sources: int
    enable_ready_sources: int
    deprecated_sources: int
    total_sources: int
    evidence_store: str
    public_review_gate: str
    public_platform: str
    experimental_live_map: str
    workflow_admin: str
    storage_backend: str
    queue_backend: str
    rate_limit_backend: str
    warnings: list[str]


def _load_release_gate(root: Path) -> dict:
    release_gate_path = root / "artifacts/proof/current/release_gate.json"
    if not release_gate_path.exists():
        return {}
    try:
        data = json.loads(release_gate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _check_exists(path_value: str | None) -> bool:
    if not path_value:
        return False
    try:
        return Path(path_value).expanduser().exists()
    except OSError:
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_logs_complete(repo_root: Path) -> tuple[bool, str | None]:
    index_path = (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "required_log_index.json"
    )
    if not index_path.is_file():
        return False, "required_log_index_missing"

    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, "required_log_index_invalid_json"

    missing_required = payload.get("missing_required_logs")
    if isinstance(missing_required, list) and missing_required:
        return False, "required_logs_missing"

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return False, "required_log_index_entries_missing"

    for entry in entries:
        if not isinstance(entry, dict):
            return False, "required_log_index_entry_invalid"
        rel_path = entry.get("path") or entry.get("log_path")
        if not isinstance(rel_path, str) or not rel_path:
            return False, "required_log_index_entry_invalid"

        # Resolve against repository root and block path escapes.
        try:
            actual_path = (repo_root / rel_path).resolve()
            actual_path.relative_to(repo_root.resolve())
        except (OSError, ValueError):
            return False, "required_log_path_invalid"

        if not actual_path.is_file():
            return False, "required_log_missing_on_disk"
        if actual_path.stat().st_size <= 0:
            return False, "required_log_empty"

        if not bool(entry.get("exists", False)):
            return False, "required_logs_missing"
        if str(entry.get("status", "")).upper() != "PASS":
            return False, "required_logs_not_pass"

        expected_hash = entry.get("actual_sha256") or entry.get("recorded_sha256")
        if isinstance(expected_hash, str) and expected_hash:
            if _compute_sha256(actual_path) != expected_hash.lower():
                return False, "required_log_hash_mismatch"

        expected_size = entry.get("actual_size_bytes")
        if expected_size is None:
            expected_size = entry.get("recorded_size_bytes")
        if isinstance(expected_size, int) and expected_size >= 0:
            if actual_path.stat().st_size != expected_size:
                return False, "required_log_size_mismatch"

    return True, None


def _proof_freshness_complete(repo_root: Path) -> tuple[bool, str | None]:
    freshness_log = (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "proof_freshness.log"
    )
    if not freshness_log.is_file():
        return False, "proof_freshness_missing_or_failed"

    text = freshness_log.read_text(encoding="utf-8", errors="ignore")
    normalized = text.lower()
    if "proof_freshness: pass" in normalized:
        return True, None
    if "status\": \"pass\"" in normalized:
        return True, None
    return False, "proof_freshness_missing_or_failed"


def _archive_handoff_verified(repo_root: Path) -> tuple[bool, str | None]:
    archive_path = repo_root / "dist" / "JUDGE_ATLAS-main-final.zip"
    if not archive_path.is_file():
        return False, "release_archive_missing"

    handoff_path = repo_root / "FINAL_RELEASE_HANDOFF.md"
    if not handoff_path.is_file():
        return False, "release_handoff_missing"

    handoff_text = handoff_path.read_text(encoding="utf-8", errors="ignore")
    path_match = _HANDOFF_PATH_RE.search(handoff_text)
    sha_match = _HANDOFF_SHA_RE.search(handoff_text)
    if not path_match or not sha_match:
        return False, "release_handoff_missing_claims"

    claimed_path = path_match.group(1).strip()
    claimed_sha = sha_match.group(1).lower()
    resolved_claim_path = Path(claimed_path)
    if not resolved_claim_path.is_absolute():
        resolved_claim_path = (repo_root / resolved_claim_path).resolve()
    else:
        resolved_claim_path = resolved_claim_path.resolve()

    if resolved_claim_path != archive_path.resolve():
        return False, "release_handoff_path_mismatch"

    actual_sha = _compute_sha256(archive_path)
    if actual_sha != claimed_sha:
        return False, "release_handoff_hash_mismatch"

    return True, None


def _proof_chain_state(
    repo_root: Path,
    release_gate: dict,
) -> tuple[bool, bool, list[str]]:
    warnings: list[str] = []

    proof_manifest_path = (
        repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    )
    release_readiness_path = (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "release_readiness.md"
    )
    release_gate_path = (
        repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    )

    if not release_gate_path.is_file():
        warnings.append("release_gate_missing")
    if not proof_manifest_path.is_file():
        warnings.append("proof_manifest_missing")
    if not release_readiness_path.is_file():
        warnings.append("release_readiness_missing")

    required_logs_ok, required_logs_warning = _required_logs_complete(
        repo_root
    )
    if required_logs_warning:
        warnings.append(required_logs_warning)

    proof_freshness_ok, proof_freshness_warning = _proof_freshness_complete(
        repo_root
    )
    if proof_freshness_warning:
        warnings.append(proof_freshness_warning)

    handoff_ok, handoff_warning = _archive_handoff_verified(repo_root)
    if handoff_warning:
        warnings.append(handoff_warning)

    checks = release_gate.get("checks")
    check_items = checks if isinstance(checks, list) else []
    archive_check_pass = any(
        isinstance(item, dict)
        and item.get("name") == "archive_validation"
        and str(item.get("status", "")).upper() == "PASS"
        for item in check_items
    )
    if not archive_check_pass:
        warnings.append("archive_validation_not_verified")

    archive_self_verifying = archive_check_pass and handoff_ok
    proof_chain_complete = (
        release_gate_path.is_file()
        and proof_manifest_path.is_file()
        and release_readiness_path.is_file()
        and required_logs_ok
        and proof_freshness_ok
        and archive_self_verifying
    )

    return proof_chain_complete, archive_self_verifying, warnings


@router.get("/api/v1/status/ingestion", response_model=IngestionStatusResponse)
@router.get("/status/ingestion", response_model=IngestionStatusResponse)
def get_ingestion_status(
    window_hours: int = Query(
        24, ge=1, le=168, description="Look-back window in hours"
    ),
    db: Session = Depends(get_db),
) -> IngestionStatusResponse:
    """Return ingestion run status summary for the last look-back window."""
    since = datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)

    rows = db.execute(
        select(
            IngestionRun.status,
            func.count(IngestionRun.id).label("count"),
        )
        .where(IngestionRun.started_at >= since)
        .group_by(IngestionRun.status)
    ).all()

    bucket_map: dict[str, int] = {
        str(row[0]): int(row[1] or 0)
        for row in rows
    }
    total = sum(bucket_map.values())

    last_run_at = db.scalar(
        select(func.max(IngestionRun.started_at)).where(
            IngestionRun.started_at >= since
        )
    )

    known = {COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, RUNNING}
    other = sum(v for k, v in bucket_map.items() if k not in known)

    return IngestionStatusResponse(
        window_hours=window_hours,
        total_runs=total,
        running=bucket_map.get(RUNNING, 0),
        completed=bucket_map.get(COMPLETED, 0),
        completed_with_warnings=bucket_map.get(COMPLETED_WITH_WARNINGS, 0),
        failed=bucket_map.get(FAILED, 0),
        other=other,
        last_run_at=last_run_at,
        buckets=[
            StatusBucket(status=k, count=v)
            for k, v in sorted(bucket_map.items())
        ],
    )


@router.get("/status/alpha-readiness", response_model=AlphaReadinessResponse)
@router.get(
    "/api/v1/status/alpha-readiness",
    response_model=AlphaReadinessResponse,
)
def get_alpha_readiness(
    db: Session = Depends(get_db),
) -> AlphaReadinessResponse:
    settings = get_settings()
    runtime_profile = resolve_runtime_profile(settings)

    repo_root = _repo_root()
    release_gate = _load_release_gate(repo_root)

    alpha_gate_passed = bool(release_gate.get("alpha_gate_passed", False))
    production_ready = bool(release_gate.get("production_ready", False))
    (
        proof_chain_complete,
        archive_self_verifying,
        proof_warnings,
    ) = _proof_chain_state(repo_root, release_gate)

    source_registry_unavailable = False
    total_sources = 0
    runnable_sources = 0
    enable_ready_sources = 0
    deprecated_sources = 0
    try:
        total_sources = db.scalar(select(func.count(SourceRegistry.id))) or 0
        runnable_sources = db.scalar(
            select(func.count(SourceRegistry.id)).where(
                SourceRegistry.lifecycle_state == "runnable"
            )
        ) or 0
        enable_ready_sources = db.scalar(
            select(func.count(SourceRegistry.id)).where(
                SourceRegistry.lifecycle_state == "runnable_disabled"
            )
        ) or 0
        deprecated_sources = db.scalar(
            select(func.count(SourceRegistry.id)).where(
                SourceRegistry.lifecycle_state == "deprecated"
            )
        ) or 0
    except (OperationalError, DatabaseError):
        source_registry_unavailable = True

    warnings: list[str] = []
    if not alpha_gate_passed:
        warnings.append("alpha_gate_not_passed")
    if production_ready:
        warnings.append("production_ready_true_requires_manual_verification")
    if not proof_chain_complete:
        warnings.append("proof_chain_incomplete")
    if runnable_sources == 0:
        warnings.append("no_runnable_sources")
    if source_registry_unavailable:
        warnings.append("source_registry_unavailable")
        warnings.append("database_not_migrated_or_unreachable")
    if not settings.evidence_store_required:
        warnings.append("evidence_store_not_required")
    if settings.enable_experimental_live_map:
        warnings.append("experimental_live_map_enabled")
    if settings.enable_public_platform:
        warnings.append("public_platform_enabled")
    if settings.enable_workflow_admin:
        warnings.append("workflow_admin_enabled")

    evidence_store_ok = _check_exists(settings.evidence_store_root)
    if not evidence_store_ok:
        warnings.append("evidence_store_root_missing")

    return AlphaReadinessResponse(
        alpha_gate_passed=alpha_gate_passed,
        production_ready=production_ready,
        proof_chain_complete=proof_chain_complete,
        archive_self_verifying=archive_self_verifying,
        runnable_sources=int(runnable_sources),
        enable_ready_sources=int(enable_ready_sources),
        deprecated_sources=int(deprecated_sources),
        total_sources=int(total_sources),
        evidence_store="ok" if evidence_store_ok else "missing",
        public_review_gate=(
            "enabled" if settings.enable_admin_review else "disabled"
        ),
        public_platform=(
            "enabled" if settings.enable_public_platform else "disabled"
        ),
        experimental_live_map=(
            "enabled" if settings.enable_experimental_live_map else "disabled"
        ),
        workflow_admin=(
            "enabled" if settings.enable_workflow_admin else "disabled"
        ),
        storage_backend=settings.storage_backend,
        queue_backend=settings.ingestion_queue_backend,
        rate_limit_backend=settings.rate_limit_backend,
        warnings=(
            warnings
            + proof_warnings
            + [f"runtime_profile={runtime_profile.name}"]
        ),
    )
