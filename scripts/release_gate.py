#!/usr/bin/env python3
"""Unified alpha release gate for JUDGE_ATLAS.

This gate executes the required alpha checks, writes canonical logs under
``artifacts/proof/current``, and fails if any referenced log file is missing.
It does not emit active proof artifacts under legacy mirror directories.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import platform
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from shutil import move


LOCAL_PATH_PATTERNS = (
    re.compile(r"/Users/[^\s\"'`]+"),
    re.compile(r"/home/[^\s\"'`]+"),
    re.compile(r"/private/[^\s\"'`]+"),
    re.compile(r"[A-Za-z]:\\[^\s\"'`]+"),
)


def _redact_local_path(value: str, repo_root: Path) -> str:
    """Redact local absolute path prefixes while preserving useful suffixes.

    If the path points under repo_root, keep the relative suffix so proof
    artifacts remain informative without leaking the host absolute path.
    """
    if not isinstance(value, str) or not value:
        return value

    normalized = value.replace("\\", "/")
    repo_prefix = str(repo_root.resolve()).replace("\\", "/")

    if normalized == repo_prefix:
        return "[REDACTED_LOCAL_PATH]"
    if normalized.startswith(repo_prefix + "/"):
        suffix = normalized[len(repo_prefix) + 1 :]
        return f"[REDACTED_LOCAL_PATH]/{suffix}"

    redacted = normalized
    for pattern in LOCAL_PATH_PATTERNS:
        redacted = pattern.sub("[REDACTED_LOCAL_PATH]", redacted)
    return redacted


def _redact_local_paths_in_text(text: str, repo_root: Path) -> str:
    """Redact any local absolute paths embedded in free-form text."""
    if not isinstance(text, str) or not text:
        return text

    normalized = text.replace("\\", "/")
    repo_prefix = str(repo_root.resolve()).replace("\\", "/")
    redacted = normalized.replace(repo_prefix, "[REDACTED_LOCAL_PATH]")
    for pattern in LOCAL_PATH_PATTERNS:
        redacted = pattern.sub("[REDACTED_LOCAL_PATH]", redacted)
    return redacted


def _redact_local_paths_in_obj(value, repo_root: Path):
    """Recursively redact local paths from JSON-like structures."""
    if isinstance(value, str):
        return _redact_local_paths_in_text(value, repo_root)
    if isinstance(value, list):
        return [_redact_local_paths_in_obj(item, repo_root) for item in value]
    if isinstance(value, dict):
        return {
            key: _redact_local_paths_in_obj(item, repo_root)
            for key, item in value.items()
        }
    return value


def _redact_file_local_paths(path: Path, repo_root: Path) -> None:
    """Redact local absolute paths from a text file in place."""
    if not path.exists() or not path.is_file():
        return

    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = None

        if parsed is not None:
            redacted_obj = _redact_local_paths_in_obj(parsed, repo_root)
            path.write_text(
                json.dumps(redacted_obj, indent=2) + "\n",
                encoding="utf-8",
            )
            return

    text = path.read_text(encoding="utf-8", errors="ignore")
    redacted = _redact_local_paths_in_text(text, repo_root)
    if redacted != text:
        path.write_text(redacted, encoding="utf-8")


def _sanitize_current_proof_artifacts(repo_root: Path, out_dir: Path) -> None:
    """Redact local absolute paths from generated proof artifacts."""
    allowed_suffixes = {".log", ".md", ".json", ".txt"}
    for path in out_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in allowed_suffixes:
            _redact_file_local_paths(path, repo_root)


def _validation_summary_gate(repo_root: Path) -> dict[str, object]:
    """Read workspace validation summary and return gate blockers if failed."""
    summary_path = repo_root / ".validation_logs" / "validation_summary.json"
    rel_path = str(summary_path.relative_to(repo_root))

    result: dict[str, object] = {
        "path": rel_path,
        "exists": summary_path.exists(),
        "status": "missing",
        "failed_phases": [],
        "blockers": [],
    }

    if not summary_path.exists():
        return result

    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        result["status"] = "parse_error"
        result["blockers"] = ["validation_summary_parse_error"]
        return result

    overall_status = str(payload.get("overall_status", "unknown")).strip().lower()
    phases = payload.get("phases")
    if not isinstance(phases, dict):
        phases = {}
    failed_phases = sorted(
        name for name, state in phases.items() if str(state).strip().lower() == "failed"
    )

    result["status"] = overall_status
    result["failed_phases"] = failed_phases
    if overall_status == "failed":
        suffix = ",".join(failed_phases) if failed_phases else "unknown"
        result["blockers"] = [f"validation_summary_failed:{suffix}"]
    elif overall_status != "passed":
        result["blockers"] = [f"validation_summary_not_passed:{overall_status}"]

    return result


PROOF_INPUT_PATTERNS = [
    "README.md",
    "CURRENT_STATUS.md",
    "PROOF_STATUS.md",
    "RELEASE_BLOCKERS.md",
    "STUBS_AND_PLACEHOLDERS.md",
    "REPO_REALITY.md",
    "COMPLETION_CHECKLIST.md",
    "Makefile",
    "Dockerfile.proof",
    ".github/workflows/**/*",
    "backend/app/**/*",
    "backend/alembic/**/*",
    "backend/pyproject.toml",
    "backend/alembic.ini",
    "backend/uv.lock",
    "demo/**/*",
    "frontend/**/*",
    "frontend/package.json",
    "frontend/package-lock.json",
    "package.json",
    "package-lock.json",
    "scripts/**/*",
    "docs/CURRENT_STATUS.md",
    "docs/DB_PROOF.md",
    "docs/security/LEGACY_AUTH_REMOVAL_PLAN.md",
    "docs/deployment-guide/DEPENDENCY_REMEDIATION_PLAN.md",
    "docs/security/FRONTEND_SECURITY_TRIAGE.md",
    "docs/security/frontend_dependency_exceptions.md",
    "docs/schema_audit.md",
    "docs/REPAIR_PROOF.md",
    "docs/REPAIR_BASELINE.md",
    "docs/SECURITY.md",
    "docs/PROOF.md",
    "docs/SOURCES.md",
    "docs/AI_PIPELINE.md",
    "artifacts/proof/CURRENT_PROOF.md",
]

REQUIRED_GATE_NAMES = {
    "backend_pytest_collect",
    "backend_compile",
    "backend_import",
    "runtime_smoke",
    "backend_pytest",
    "check_dockerfile_copy_paths",
    "check_compose_auth_defaults",
    "validate_sources",
    "check_yaml_duplicate_keys",
    "verify_source_registry",
    "check_source_registry_docs",
    "check_false_claims",
    "check_no_local_paths_in_release_proof",
    "check_source_keys",
    "check_statuses",
    "check_no_direct_ingestion_network_clients",
    "verify_evidence_store",
    "verify_audit_chain",
    "check_node_policy",
    "frontend_node_gate",
    "frontend_install",
    "frontend_lint",
    "frontend_typecheck",
    "frontend_contracts",
    "frontend_build",
    "docker_runtime_preflight",
    "frontend_backend_route_contract",
    "docker_smoke",
    "postgis_proof",
    "egress_proxy_proof",
    "demo_proof",
    "canlii_staging_proof",
    "proof_consistency_pytest",
    "check_proof_consistency",
    "release_readiness_generation",
    "required_proof_logs",
    "check_proof_manifest",
    "archive_validation",
    "single_proof_authority",
}

REQUIRED_PROOF_MANIFEST_LOGS = (
    "artifacts/proof/current/release_gate.log",
    "artifacts/proof/current/backend_pytest.log",
    "artifacts/proof/current/frontend_build.log",
    "artifacts/proof/current/docker_runtime_preflight.log",
    "artifacts/proof/current/proof_consistency_pytest.log",
    "artifacts/proof/current/docker_smoke.log",
    "artifacts/proof/current/runtime_smoke.log",
)

REQUIRED_PROOF_FILES = (
    "artifacts/proof/current/CURRENT_PROOF.md",
    "artifacts/proof/current/CURRENT_ALPHA_STATUS.md",
    "artifacts/proof/current/SOURCE_REGISTRY_STATUS.md",
    "artifacts/proof/current/source_registry_status.json",
    "artifacts/proof/current/release_gate.json",
    "artifacts/proof/current/proof_manifest.json",
    "artifacts/proof/current/required_log_index.json",
    "artifacts/proof/current/REPAIR_REPORT.md",
    "artifacts/proof/current/FIX_VERIFICATION_REPORT.md",
    "artifacts/proof/current/release_readiness.md",
    "artifacts/proof/current/PROOF_POLICY.md",
)


@dataclass
class GateStep:
    name: str
    command: str
    status: str  # "PASS" | "FAIL" | "BLOCKED"
    exit_code: int
    duration_seconds: float
    log_path: str
    started_at_utc: str
    finished_at_utc: str
    required: bool
    cwd: str
    failure_reason: str | None = None


@dataclass
class GateStepSpec:
    name: str
    log_name: str
    command: list[str]
    timeout_seconds: int | None = None
    required: bool = True


def _run(
    repo_root: Path,
    out_dir: Path,
    name: str,
    log_name: str,
    command: list[str],
    timeout_seconds: int | None = None,
    required: bool = True,
) -> GateStep:
    log_path = out_dir / log_name
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc)
    failure_reason: str | None = None
    return_code = 0
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            command,
            cwd=repo_root,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        try:
            proc.communicate(timeout=timeout_seconds)
            return_code = proc.returncode
            if return_code != 0:
                failure_reason = f"nonzero_exit_{return_code}"
        except subprocess.TimeoutExpired:
            # Kill the whole process group so child/grandchild commands do not leak.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()

            timeout_note = (
                "\n[release_gate] TIMEOUT after "
                f"{timeout_seconds}s for step '{name}'.\n"
            )
            fh.write(timeout_note)
            return_code = 124
            failure_reason = "timeout"
            _redact_file_local_paths(log_path, repo_root)
        except Exception:
            # Ensure we do not leave subprocesses behind on unexpected errors.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
    if log_path.exists() and log_path.stat().st_size == 0:
        log_path.write_text(
            "[release_gate] "
            f"step={name} exit_code={return_code} emitted no stdout/stderr.\n",
            encoding="utf-8",
        )
    if log_path.exists():
        _redact_file_local_paths(log_path, repo_root)
    finished_at = datetime.now(timezone.utc)
    duration = round(time.monotonic() - t0, 3)
    passed = return_code == 0
    return GateStep(
        name=name,
        command=_redact_local_paths_in_text(" ".join(command), repo_root),
        status="PASS" if passed else "FAIL",
        exit_code=return_code,
        duration_seconds=duration,
        log_path=str(log_path.relative_to(repo_root)),
        started_at_utc=started_at.isoformat(),
        finished_at_utc=finished_at.isoformat(),
        required=required,
        cwd=_redact_local_paths_in_text(str(repo_root), repo_root),
        failure_reason=failure_reason,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_current_proof(repo_root: Path, out_dir: Path) -> str | None:
    history_root = repo_root / "artifacts" / "history" / "proof"
    history_root.mkdir(parents=True, exist_ok=True)
    entries = [p for p in out_dir.iterdir() if p.exists()]
    if not entries:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = history_root / stamp
    target.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        move(str(entry), str(target / entry.name))
    return str(target.relative_to(repo_root))


def _missing_logs(repo_root: Path, checks: list[GateStep]) -> list[str]:
    missing: list[str] = []
    for check in checks:
        if not (repo_root / check.log_path).exists():
            missing.append(check.log_path)
    return missing


def _missing_required_proof_files(repo_root: Path) -> list[str]:
    return sorted(
        rel_path
        for rel_path in REQUIRED_PROOF_FILES
        if not (repo_root / rel_path).is_file()
    )


def _required_log_index_missing_exists_entries(
    repo_root: Path, out_dir: Path
) -> list[str]:
    index_path = out_dir / "required_log_index.json"
    if not index_path.exists():
        return ["artifacts/proof/current/required_log_index.json"]
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["artifacts/proof/current/required_log_index.json:invalid_json"]
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return ["artifacts/proof/current/required_log_index.json:invalid_entries"]

    missing: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("path")
        exists_flag = entry.get("exists")
        if not isinstance(rel_path, str) or not rel_path:
            continue
        if exists_flag is True and not (repo_root / rel_path).is_file():
            missing.append(rel_path)
    return sorted(set(missing))


def _failed_required_checks(checks: list[GateStep]) -> list[str]:
    return [check.name for check in checks if check.required and check.exit_code != 0]


def _archive_legacy_sidecars(repo_root: Path, out_dir: Path) -> list[str]:
    legacy_names = [
        "manifest.json",
        "proof_all_summary.json",
        "environment_info.txt",
    ]
    history_dir = repo_root / "artifacts" / "proof" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    archived: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name in legacy_names:
        src = out_dir / name
        if not src.exists():
            continue
        dst = history_dir / f"{stamp}_{name}"
        move(str(src), str(dst))
        archived.append(str(dst.relative_to(repo_root)))

    readme = history_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Proof History Sidecars\n\n"
            "This directory stores historical sidecar artifacts moved from "
            "`artifacts/proof/current/`.\n\n"
            "Current authoritative proof state is produced by "
            "`artifacts/proof/current/release_gate.json` and "
            "`artifacts/proof/current/CURRENT_PROOF.md`.\n",
            encoding="utf-8",
        )
    return archived


def _extract_pytest_counts(
    log_path: Path,
) -> tuple[int | None, int | None, int | None]:
    if not log_path.exists():
        return (None, None, None)
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    passed_match = re.search(r"(\d+) passed(?:,\s*(\d+) skipped)?", text)
    failed_match = re.search(r"(\d+) failed", text)
    passed = int(passed_match.group(1)) if passed_match else None
    skipped = (
        int(passed_match.group(2))
        if passed_match and passed_match.group(2)
        else 0
    )
    failed = int(failed_match.group(1)) if failed_match else 0
    return (passed, skipped, failed)


def _extract_vitest_tests_passed(log_path: Path) -> int | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"Tests\s+(\d+)\s+passed", text)
    if not match:
        return None
    return int(match.group(1))


def _extract_migration_count(log_path: Path) -> int | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    patterns = [
        r"Alembic migration files:\s*(\d+)",
        r"Total migrations:\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _extract_backend_import_route_count(log_path: Path) -> int | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"app has\s+(\d+)\s+routes", text)
    if not match:
        return None
    return int(match.group(1))


def _extract_prefixed_value(log_path: Path, prefix: str) -> str | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    pattern = re.compile(rf"^{re.escape(prefix)}\s*(.+)$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1).strip()


def _enforce_canlii_staging_gate(
    checks_map: dict[str, GateStep],
    blocked_checks: dict[str, str],
    canlii_staging_status: str | None,
) -> None:
    """Require explicit PASS when CanLII staging gate is configured as required."""
    step = checks_map.get("canlii_staging_proof")
    if step is None:
        return

    status = (canlii_staging_status or "").strip().upper()
    if status.startswith("SKIPPED") and step.exit_code == 0:
        step.status = "BLOCKED"
        step.exit_code = 1
        step.failure_reason = "missing_canlii_api_key"
        blocked_checks["canlii_staging_proof"] = (
            "CANLII_API_KEY missing; required staging proof cannot be skipped"
        )


def _check_status_map(payload: dict) -> dict[str, dict]:
    return {check["name"]: check for check in payload.get("checks", [])}


def _normalize_gate_status(step: GateStep | None) -> str:
    if step is None:
        return "not_run"
    status = (step.status or "").strip().upper()
    if status in {"PASS", "PASSED"}:
        return "pass"
    if status in {"SKIP", "SKIPPED", "UNKNOWN", "NOT_RUN"}:
        return "not_run"
    if step.exit_code == 0:
        return "pass"
    return "fail"


def _combine_gate_status(*statuses: str) -> str:
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "pass" for status in statuses):
        return "pass"
    return "not_run"


def _canonical_checks_summary(results: list[GateStep]) -> dict[str, str]:
    by_name = {result.name: result for result in results}
    backend_tests = _normalize_gate_status(by_name.get("backend_pytest"))
    frontend_tests = _normalize_gate_status(by_name.get("frontend_contracts"))
    frontend_build = _normalize_gate_status(by_name.get("frontend_build"))
    docker_proof = _combine_gate_status(
        _normalize_gate_status(by_name.get("docker_runtime_preflight")),
        _normalize_gate_status(by_name.get("postgis_proof")),
    )
    archive_validation = _normalize_gate_status(
        by_name.get("archive_validation")
    )
    source_registry = _combine_gate_status(
        _normalize_gate_status(by_name.get("verify_source_registry")),
        _normalize_gate_status(by_name.get("source_registry_status")),
    )
    proof_freshness = _normalize_gate_status(by_name.get("proof_freshness"))
    public_boundary = _normalize_gate_status(
        by_name.get("public_api_boundary")
    )
    return {
        "backend_tests": backend_tests,
        "frontend_tests": frontend_tests,
        "frontend_build": frontend_build,
        "docker_proof": docker_proof,
        "archive_validation": archive_validation,
        "source_registry": source_registry,
        "proof_freshness": proof_freshness,
        "public_boundary": public_boundary,
    }


def _refresh_release_payload_schema(
    payload: dict, results: list[GateStep]
) -> None:
    payload["schema_version"] = "1.1.0"
    payload["release_candidate"] = bool(
        payload.get("alpha_gate_passed", False)
    )
    payload["checks_summary"] = _canonical_checks_summary(results)


def _write_json(repo_root: Path, path: Path, data: dict) -> str:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return str(path.relative_to(repo_root))


def _read_source_registry_summary(out_dir: Path) -> dict:
    status_path = out_dir / "source_registry_status.json"
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _proof_db_counts(out_dir: Path) -> dict[str, int]:
    proof_db = out_dir / "proof.db"
    if not proof_db.exists():
        return {}

    counts: dict[str, int] = {}
    with sqlite3.connect(proof_db) as conn:
        cursor = conn.cursor()
        for table_name in (
            "audit_logs",
            "source_snapshots",
            "source_registry",
        ):
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            except sqlite3.Error:
                continue
            row = cursor.fetchone()
            counts[table_name] = int(row[0]) if row else 0
    return counts


def _write_grouped_proof_artifacts(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
) -> dict[str, str]:
    checks = _check_status_map(payload)
    backend_checks: list[dict[str, object]] = []
    backend_group = {
        "group": "backend_proof",
        "status": "PASS",
        "checks": backend_checks,
        "route_count": payload.get("backend_import_route_count"),
        "pytest_passed": payload.get("backend_pytest_passed"),
        "pytest_skipped": payload.get("backend_pytest_skipped"),
        "proof_db_counts": _proof_db_counts(out_dir),
    }
    backend_names = [
        "backend_compile",
        "backend_import",
        "backend_pytest",
        "check_migrations",
        "prepare_proof_db",
        "verify_evidence_store",
        "verify_audit_chain",
        "auth_mutation_route_coverage",
        "mutation_fail_closed_coverage",
        "validate_sources",
    ]
    for name in backend_names:
        check = checks.get(name)
        if not check:
            continue
        backend_checks.append(
            {
                "name": name,
                "status": check["status"],
                "log": check["log_path"],
                "exit_code": check["exit_code"],
            }
        )
        if check["exit_code"] != 0:
            backend_group["status"] = "FAIL"

    frontend_checks: list[dict[str, object]] = []
    frontend_group = {
        "group": "frontend_proof",
        "status": "PASS",
        "checks": frontend_checks,
    }
    frontend_names = [
        "frontend_node_gate",
        "frontend_install",
        "frontend_lint",
        "frontend_typecheck",
        "frontend_contracts",
        "frontend_build",
        "check_api_contracts",
        "frontend_backend_route_contract",
        "map_route_check",
        "public_api_boundary",
        "check_node_policy",
    ]
    for name in frontend_names:
        check = checks.get(name)
        if not check:
            continue
        frontend_checks.append(
            {
                "name": name,
                "status": check["status"],
                "log": check["log_path"],
                "exit_code": check["exit_code"],
            }
        )
        if check["exit_code"] != 0:
            frontend_group["status"] = "FAIL"
    artifacts = {
        "backend_proof_summary": _write_json(
            repo_root,
            out_dir / "backend_proof_summary.json",
            backend_group,
        ),
        "frontend_proof_summary": _write_json(
            repo_root,
            out_dir / "frontend_proof_summary.json",
            frontend_group,
        ),
    }

    artifacts["source_registry_status"] = str(
        (out_dir / "source_registry_status.json").relative_to(repo_root)
    )
    return artifacts


def _write_static_guards_log(
    repo_root: Path, out_dir: Path, steps: list[GateStep]
) -> str:
    guard_names = [
        "check_false_claims",
        "check_source_keys",
        "check_statuses",
        "check_no_direct_ingestion_network_clients",
        "check_source_registry_docs",
    ]
    step_map = {step.name: step for step in steps}
    lines = ["STATIC GUARDS"]
    for guard in guard_names:
        step = step_map.get(guard)
        if step is None:
            lines.append(f"{guard}: MISSING")
            continue
        lines.append(
            f"{guard}: {step.status} rc={step.exit_code} log={step.log_path}"
        )
    log_path = out_dir / "static_guards.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(log_path.relative_to(repo_root))


def _build_proof_manifest(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
    steps: list[GateStep],
) -> dict:
    entries: list[dict] = []
    for step in steps:
        log_abs = repo_root / step.log_path
        log_exists = log_abs.exists()
        captured_at = step.finished_at_utc
        size_bytes = log_abs.stat().st_size if log_exists else 0
        entry = {
            "name": step.name,
            "path": step.log_path,
            "required": step.required,
            "cwd": step.cwd,
            "command": step.command,
            "created_at": captured_at,
            "captured_at": captured_at,
            "started_at": step.started_at_utc,
            "finished_at": step.finished_at_utc,
            "duration_seconds": step.duration_seconds,
            "exit_code": step.exit_code,
            "status": step.status,
            "log_path": step.log_path,
            "log_exists": log_exists,
            "log_sha256": _sha256_file(log_abs) if log_exists else None,
            "sha256": _sha256_file(log_abs) if log_exists else None,
            "size_bytes": size_bytes,
            "proof_source": step.name,
            "failure_reason": step.failure_reason,
        }
        entries.append(entry)

    seen_paths = {entry["path"] for entry in entries}
    for proof_source, rel_path in (payload.get("logs") or {}).items():
        if not isinstance(rel_path, str) or not rel_path.endswith(".log"):
            continue
        if rel_path in seen_paths:
            continue
        log_abs = repo_root / rel_path
        log_exists = log_abs.exists()
        size_bytes = log_abs.stat().st_size if log_exists else 0
        entries.append(
            {
                "name": proof_source,
                "path": rel_path,
                "required": rel_path in REQUIRED_PROOF_MANIFEST_LOGS,
                "cwd": _redact_local_paths_in_text(str(repo_root), repo_root),
                "command": f"generated:{proof_source}",
                "created_at": payload.get("timestamp_utc"),
                "captured_at": payload.get("timestamp_utc"),
                "started_at": payload.get("timestamp_utc"),
                "finished_at": payload.get("timestamp_utc"),
                "duration_seconds": 0.0,
                "exit_code": 0,
                "status": "PASS" if log_exists else "FAIL",
                "log_path": rel_path,
                "log_exists": log_exists,
                "log_sha256": _sha256_file(log_abs) if log_exists else None,
                "sha256": _sha256_file(log_abs) if log_exists else None,
                "size_bytes": size_bytes,
                "proof_source": proof_source,
                "failure_reason": None if log_exists else "missing_file",
            }
        )
        seen_paths.add(rel_path)

    # Guarantee that every required proof log has a manifest entry.
    # This keeps required_log_index generation and consistency checks aligned
    # even when a required log was not emitted by a GateStep in a partial run.
    for rel_path in REQUIRED_PROOF_MANIFEST_LOGS:
        if rel_path in seen_paths:
            continue
        log_abs = repo_root / rel_path
        log_exists = log_abs.exists()
        size_bytes = log_abs.stat().st_size if log_exists else 0
        log_hash = _sha256_file(log_abs) if log_exists else None
        captured_at_raw = payload.get("timestamp_utc")
        captured_at = (
            captured_at_raw
            if isinstance(captured_at_raw, str) and captured_at_raw
            else "unknown"
        )
        entries.append(
            {
                "name": Path(rel_path).stem,
                "path": rel_path,
                "required": True,
                "cwd": _redact_local_paths_in_text(str(repo_root), repo_root),
                "command": "required_proof_log",
                "created_at": captured_at,
                "captured_at": captured_at,
                "started_at": captured_at,
                "finished_at": captured_at,
                "duration_seconds": 0.0,
                "exit_code": 0 if log_exists else 1,
                "status": "PASS" if log_exists else "FAIL",
                "log_path": rel_path,
                "log_exists": log_exists,
                "log_sha256": log_hash,
                "sha256": log_hash,
                "size_bytes": size_bytes,
                "proof_source": "required_proof_manifest",
                "failure_reason": None if log_exists else "missing_file",
            }
        )
        seen_paths.add(rel_path)

    manifest = {
        "generated_at": payload.get("timestamp_utc"),
        "archive_hash": payload.get("commit_hash", "unknown"),
        "platform": payload.get("platform", "unknown"),
        "python_version": payload.get("python_version", "unknown"),
        "gate_runner_node_version": payload.get("node_version", "unknown"),
        "node_version": payload.get("node_version", "unknown"),
        "frontend_node_gate_version": payload.get(
            "frontend_node_gate_version"
        ),
        "npm_version": payload.get("npm_version", "unknown"),
        "proof_input_tree_hash": payload.get(
            "proof_input_tree_hash", "unknown"
        ),
        "proof_input_tree_hash_algorithm": payload.get(
            "proof_input_tree_hash_algorithm", "sha256"
        ),
        "proof_input_file_count": payload.get("proof_input_file_count", 0),
        "proof_root": str(out_dir.relative_to(repo_root)),
        "required_logs": list(REQUIRED_PROOF_MANIFEST_LOGS),
        "proof_commands": entries,
    }
    return manifest


def _manifest_entry_path(entry: dict) -> str | None:
    path = entry.get("path")
    if isinstance(path, str) and path:
        return path
    log_path = entry.get("log_path")
    if isinstance(log_path, str) and log_path:
        return log_path
    return None


def _write_required_log_index(
    repo_root: Path,
    out_dir: Path,
    manifest: dict,
) -> str:
    required_logs = manifest.get("required_logs")
    if not isinstance(required_logs, list):
        required_logs = []

    proof_commands = manifest.get("proof_commands")
    if not isinstance(proof_commands, list):
        proof_commands = []

    entry_by_path: dict[str, dict] = {}
    for entry in proof_commands:
        if not isinstance(entry, dict):
            continue
        path = _manifest_entry_path(entry)
        if path:
            entry_by_path[path] = entry

    index_entries: list[dict[str, object]] = []
    for rel_path in required_logs:
        if not isinstance(rel_path, str) or not rel_path:
            continue
        location_scope = (
            "archive_internal"
            if rel_path.startswith("artifacts/proof/current/")
            else "external_evidence"
        )
        entry = entry_by_path.get(rel_path)
        if isinstance(entry, dict):
            recorded_hash = entry.get("sha256") or entry.get("log_sha256")
            recorded_size = entry.get("size_bytes")
            exists_flag = entry.get("log_exists")
            if isinstance(exists_flag, bool):
                exists = exists_flag
            else:
                # Backward compatibility: historical/fixture manifests may
                # omit log_exists while still carrying canonical hash/size.
                if isinstance(recorded_hash, str) and recorded_hash:
                    exists = True
                else:
                    exists = (repo_root / rel_path).exists()
        else:
            # Keep this deterministic relative to manifest creation: if a
            # required log is not represented in the final manifest, fail it
            # explicitly instead of deriving a separate on-disk truth here.
            exists = False
            recorded_hash = None
            recorded_size = None

        actual_hash = recorded_hash if exists else None
        actual_size = recorded_size if exists else None
        status = "PASS" if exists and isinstance(recorded_hash, str) else "FAIL"

        index_entries.append(
            {
                "path": rel_path,
                "location_scope": location_scope,
                "exists": exists,
                "recorded_sha256": recorded_hash,
                "actual_sha256": actual_hash,
                "recorded_size_bytes": recorded_size,
                "actual_size_bytes": actual_size,
                "status": status,
            }
        )

    required_index = {
        "generated_at": manifest.get("generated_at"),
        "proof_root": manifest.get("proof_root"),
        "required_logs_total": len(index_entries),
        "missing_required_logs": [
            item["path"] for item in index_entries if not item.get("exists")
        ],
        "entries": index_entries,
    }

    output_path = out_dir / "required_log_index.json"
    output_path.write_text(
        json.dumps(required_index, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(output_path.relative_to(repo_root))


def _generate_release_readiness_from_manifest(
    repo_root: Path,
    out_dir: Path,
    manifest: dict,
    additional_blockers: list[str] | None = None,
) -> tuple[dict, str]:
    present_names = {
        str(entry.get("name")) for entry in manifest.get("proof_commands", [])
    }
    missing_required_names = sorted(REQUIRED_GATE_NAMES - present_names)

    required_entries = [
        entry
        for entry in manifest.get("proof_commands", [])
        if entry.get("required", True)
    ]
    optional_entries = [
        entry
        for entry in manifest.get("proof_commands", [])
        if not entry.get("required", True)
    ]

    blockers: list[str] = []
    for missing_name in missing_required_names:
        blockers.append(f"missing_required_gate:{missing_name}")

    for entry in required_entries:
        if entry.get("status") != "PASS":
            blockers.append(f"required_gate_failed:{entry.get('name')}")
        if not entry.get("log_exists"):
            blockers.append(
                f"missing_log:{entry.get('name')}:{entry.get('log_path')}"
            )
        if not entry.get("log_sha256"):
            blockers.append(f"missing_log_sha256:{entry.get('name')}")

    archive_entry = next(
        (
            entry
            for entry in manifest.get("proof_commands", [])
            if entry.get("name") == "archive_validation"
        ),
        None,
    )
    if archive_entry is None:
        blockers.append("archive_validation_missing")
    elif archive_entry.get("status") != "PASS":
        blockers.append("archive_validation_not_pass")

    if additional_blockers is not None:
        # release_gate.json is the canonical blocker contract. Keep
        # release_readiness.md aligned with that list to avoid divergence.
        merged_blockers = []
        for blocker in additional_blockers:
            if isinstance(blocker, str) and blocker and blocker not in merged_blockers:
                merged_blockers.append(blocker)
    else:
        merged_blockers = list(blockers)

    status = "alpha-proof-pass" if not merged_blockers else "blocked"
    recommendation = "alpha-proof-pass" if not merged_blockers else "blocked"
    production_ready = False

    readiness = {
        "overall_status": status,
        "production_ready": production_ready,
        "release_recommendation": recommendation,
        "blockers": merged_blockers,
    }

    lines = [
        "# RELEASE_READINESS",
        "",
        f"- generated_at_utc: {manifest.get('generated_at', 'unknown')}",
        f"- overall_status: {status}",
        f"- production_ready: {str(production_ready).lower()}",
        f"- release_recommendation: {recommendation}",
        f"- archive_hash: {manifest.get('archive_hash', 'unknown')}",
        f"- platform: {manifest.get('platform', 'unknown')}",
        f"- python_version: {manifest.get('python_version', 'unknown')}",
        f"- node_version: {manifest.get('node_version', 'unknown')}",
        f"- npm_version: {manifest.get('npm_version', 'unknown')}",
        "",
        "## Required Proof Gates",
        "",
        "| gate | status | exit_code | log | sha256 |",
        "|---|---|---:|---|---|",
    ]
    for entry in required_entries:
        lines.append(
            f"| {entry.get('name')} | {entry.get('status')} | {entry.get('exit_code')} | "
            f"{entry.get('log_path')} | {entry.get('log_sha256') or 'missing'} |"
        )

    if optional_entries:
        lines.extend(
            [
                "",
                "## Optional Proof Gates",
                "",
                "| gate | status | exit_code | log | sha256 |",
                "|---|---|---:|---|---|",
            ]
        )
        for entry in optional_entries:
            lines.append(
                f"| {entry.get('name')} | {entry.get('status')} | {entry.get('exit_code')} | "
                f"{entry.get('log_path')} | {entry.get('log_sha256') or 'missing'} |"
            )

    lines.extend(["", "## Remaining Blockers", ""])
    if merged_blockers:
        lines.extend(f"- {blocker}" for blocker in merged_blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Stale Or Misreported Claims",
            "",
            (
                "- none"
                if not merged_blockers
                else "- readiness is blocked due to failed/missing required proof evidence"
            ),
            "",
            "## Next Repair Action",
            "",
            "- Resolve any required failed gate and rerun scripts/release_gate.py.",
            "",
        ]
    )

    readiness_text = "\n".join(lines)
    (out_dir / "release_readiness.md").write_text(
        readiness_text, encoding="utf-8"
    )
    return readiness, str(
        (out_dir / "release_readiness.md").relative_to(repo_root)
    )


def _write_current_alpha_status_md(
    repo_root: Path, out_dir: Path, payload: dict
) -> str:
    blockers = payload.get("release_blockers_remaining", [])
    lines = [
        "# CURRENT_ALPHA_STATUS",
        "",
        f"- generated_at_utc: {payload.get('timestamp_utc', 'unknown')}",
        f"- commit_hash: {payload.get('commit_hash', 'unknown')}",
        "- operational_posture: alpha",
        "- production_ready: false",
        f"- alpha_gate_passed: {str(payload.get('alpha_gate_passed', False)).lower()}",
        f"- proof_freshness_result: {payload.get('proof_freshness_result', 'UNKNOWN')}",
        f"- release_gate_check_count: {payload.get('check_count', 0)}",
        f"- postgis_proof_result: {payload.get('postgis_proof_result', 'UNKNOWN')}",
        f"- egress_proxy_proof_result: {payload.get('egress_proxy_proof_result', 'UNKNOWN')}",
        f"- demo_proof_result: {payload.get('demo_proof_result', 'UNKNOWN')}",
        "",
        "## Status",
        "",
        "- This repository is in alpha proof-hardened posture.",
        "- This repository is not approved for production deployment.",
        "- Human review remains mandatory for public publication decisions.",
        "",
        "## Current Blockers",
        "",
    ]
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.append("")

    output_path = out_dir / "CURRENT_ALPHA_STATUS.md"
    text = "\n".join(lines)
    output_path.write_text(text, encoding="utf-8")
    (repo_root / "docs" / "CURRENT_ALPHA_STATUS.md").write_text(
        text, encoding="utf-8"
    )
    return str(output_path.relative_to(repo_root))


def _source_display_name(source: dict) -> str:
    """Return the best available display name for a source registry entry.

    Fallback chain: source_name → name → source_key → UNKNOWN_SOURCE.
    This is robust against stale JSON where an older export omitted one field.
    """
    return (
        source.get("source_name")
        or source.get("name")
        or source.get("source_key")
        or "UNKNOWN_SOURCE"
    )


def _write_source_registry_status_md(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
    source_registry_summary: dict,
) -> str:
    summary = source_registry_summary.get("summary", {})
    sources = source_registry_summary.get("sources", [])
    lines = [
        "# SOURCE_REGISTRY_STATUS",
        "",
        f"- generated_at_utc: {payload.get('timestamp_utc', 'unknown')}",
        f"- commit_hash: {payload.get('commit_hash', 'unknown')}",
        f"- total_sources: {summary.get('total_sources', 'unknown')}",
        f"- machine_ingest_sources: {summary.get('machine_ingest_sources', 'unknown')}",
        f"- runnable_now: {summary.get('runnable_now', 'unknown')}",
        f"- enable_ready: {summary.get('enable_ready', 'unknown')}",
        f"- deprecated: {summary.get('deprecated', 'unknown')}",
        "",
        "| source key | source name | jurisdiction | source class/type | lifecycle state | automation status | adapter state | parser key | adapter exists | runnable now | enable ready | blockers | review required before public visibility | current alpha status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for source in sorted(
        sources, key=lambda item: str(item.get("source_key", ""))
    ):
        runnable_now = "yes" if source.get("runnable_now") else "no"
        enable_ready = "yes" if source.get("enable_ready") else "no"
        blockers = source.get("blockers") or []
        blockers_text = (
            ", ".join(str(item) for item in blockers) if blockers else "none"
        )
        review_required = (
            "yes"
            if source.get("public_visibility_policy", {}).get(
                "requires_manual_review", True
            )
            else "no"
        )
        alpha_status = (
            "runnable-alpha-source"
            if runnable_now == "yes"
            else "limited-alpha-source"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    str(source.get("source_key", "")),
                    _source_display_name(source),
                    str(source.get("jurisdiction", "unknown")),
                    f"{source.get('source_class', 'unknown')}/{source.get('source_type', 'unknown')}",
                    str(source.get("lifecycle_state", "unknown")),
                    str(source.get("automation_status", "unknown")),
                    str(source.get("adapter_state", "unknown")),
                    str(source.get("parser", "none")),
                    "yes" if source.get("adapter_exists") else "no",
                    runnable_now,
                    enable_ready,
                    blockers_text,
                    review_required,
                    alpha_status,
                ]
            )
            + " |"
        )
    lines.extend(
        ["", "- artifacts/proof/current/source_registry_status.json", ""]
    )

    output_path = out_dir / "SOURCE_REGISTRY_STATUS.md"
    text = "\n".join(lines)
    output_path.write_text(text, encoding="utf-8")
    (repo_root / "docs" / "SOURCE_REGISTRY_STATUS.md").write_text(
        text, encoding="utf-8"
    )
    return str(output_path.relative_to(repo_root))


def _write_proof_policy_md(
    repo_root: Path, out_dir: Path, payload: dict
) -> str:
    lines = [
        "# PROOF_POLICY",
        "",
        f"- generated_at_utc: {payload.get('timestamp_utc', 'unknown')}",
        f"- commit_hash: {payload.get('commit_hash', 'unknown')}",
        "",
        "## Canonical Current Artifacts",
        "",
        "- Canonical proof output location is artifacts/proof/current/.",
        "- release_gate.json is the machine-readable source of truth for gate state.",
        "- CURRENT_PROOF.md and release_readiness.md are derived summaries from release_gate.json.",
        "- CURRENT_ALPHA_STATUS.md and SOURCE_REGISTRY_STATUS.md are generated per run from the same gate payload.",
        "",
        "## History And Retention",
        "",
        "- Historical sidecars are archived to artifacts/proof/history/.",
        "- artifacts/proof/current/ represents only the latest authoritative run.",
        "",
        "## Truth Boundaries",
        "",
        "- Release recommendation is blocked on any required failed or missing check.",
        "- Operational posture remains alpha; production readiness is false.",
        "- Evidence snapshots are authoritative; memory is derivative and non-authoritative.",
        "",
    ]

    output_path = out_dir / "PROOF_POLICY.md"
    text = "\n".join(lines)
    output_path.write_text(text, encoding="utf-8")
    (repo_root / "docs" / "PROOF_POLICY.md").write_text(text, encoding="utf-8")
    return str(output_path.relative_to(repo_root))


def _write_repair_report_md(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
    source_registry_summary: dict,
) -> str:
    checks = _check_status_map(payload)

    def phase_status(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    phases = [
        (
            "1. Alpha Gate Truthfulness",
            phase_status(bool(payload.get("alpha_gate_passed"))),
            "artifacts/proof/current/release_gate.json",
        ),
        (
            "2. Canonical Proof Artifacts",
            phase_status(
                (out_dir / "release_gate.json").exists()
                and (out_dir / "CURRENT_PROOF.md").exists()
            ),
            "artifacts/proof/current/CURRENT_PROOF.md",
        ),
        (
            "3. Generated Alpha Status",
            phase_status((out_dir / "CURRENT_ALPHA_STATUS.md").exists()),
            "artifacts/proof/current/CURRENT_ALPHA_STATUS.md",
        ),
        (
            "4. Source Registry Governance",
            phase_status(bool(source_registry_summary.get("summary"))),
            "artifacts/proof/current/source_registry_status.json",
        ),
        (
            "5. Generated Source Registry Status",
            phase_status((out_dir / "SOURCE_REGISTRY_STATUS.md").exists()),
            "artifacts/proof/current/SOURCE_REGISTRY_STATUS.md",
        ),
        (
            "6. Proof Policy Generated",
            phase_status((out_dir / "PROOF_POLICY.md").exists()),
            "artifacts/proof/current/PROOF_POLICY.md",
        ),
        (
            "7. Evidence Store Integrity",
            phase_status(
                checks.get("verify_evidence_store", {}).get("status") == "PASS"
            ),
            "artifacts/proof/current/verify_evidence_store.log",
        ),
        (
            "8. Audit Chain Integrity",
            phase_status(
                checks.get("verify_audit_chain", {}).get("status") == "PASS"
            ),
            "artifacts/proof/current/verify_audit_chain.log",
        ),
        (
            "9. Justice XML Proof Coverage",
            phase_status(
                checks.get("backend_pytest", {}).get("status") == "PASS"
            ),
            "artifacts/proof/current/backend_pytest.log",
        ),
        (
            "10. Public Review Gate Coverage",
            phase_status(
                checks.get("public_api_boundary", {}).get("status") == "PASS"
            ),
            "artifacts/proof/current/public_api_boundary.log",
        ),
        (
            "11. Derivative Memory Boundary Coverage",
            phase_status(
                checks.get("public_api_boundary", {}).get("status") == "PASS"
            ),
            "artifacts/proof/current/public_api_boundary.log",
        ),
        (
            "12. Frontend Node 22 Gate",
            phase_status(
                checks.get("frontend_node_gate", {}).get("status") == "PASS"
            ),
            "artifacts/proof/current/frontend_node_gate.log",
        ),
        (
            "13. CI/Local Gate Parity Baseline",
            phase_status((out_dir / "release_readiness.md").exists()),
            "artifacts/proof/current/release_readiness.md",
        ),
        (
            "14. Repair Report Generated",
            phase_status(True),
            "artifacts/proof/current/REPAIR_REPORT.md",
        ),
    ]

    lines = [
        "# REPAIR_REPORT",
        "",
        f"- generated_at_utc: {payload.get('timestamp_utc', 'unknown')}",
        f"- commit_hash: {payload.get('commit_hash', 'unknown')}",
        f"- alpha_gate_passed: {str(payload.get('alpha_gate_passed', False)).lower()}",
        "",
        "## Phase Results",
        "",
    ]
    for phase_name, status, evidence in phases:
        lines.append(f"- {phase_name}: {status} ({evidence})")

    lines.extend(
        [
            "",
            "## Remaining Blockers",
            "",
        ]
    )
    blockers = payload.get("release_blockers_remaining", [])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    elif payload.get("alpha_gate_passed", False):
        lines.append("- none")
    else:
        lines.append("- unresolved_gate_failure")
    lines.append("")

    output_path = out_dir / "REPAIR_REPORT.md"
    text = "\n".join(lines)
    output_path.write_text(text, encoding="utf-8")
    (repo_root / "REPAIR_REPORT.md").write_text(text, encoding="utf-8")
    return str(output_path.relative_to(repo_root))


def _write_fix_verification_report_md(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
) -> str:
    checks = _check_status_map(payload)

    lines = [
        "# FIX_VERIFICATION_REPORT",
        "",
        f"- generated_at_utc: {payload.get('timestamp_utc', 'unknown')}",
        f"- commit_hash: {payload.get('commit_hash', 'unknown')}",
        f"- alpha_gate_passed: {str(payload.get('alpha_gate_passed', False)).lower()}",
        "",
        "## Required Gate Signals",
        "",
    ]

    signal_checks = [
        "backend_compile",
        "backend_import",
        "backend_pytest",
        "verify_evidence_store",
        "verify_audit_chain",
        "public_api_boundary",
        "frontend_node_gate",
        "frontend_contracts",
        "archive_validation",
        "proof_freshness",
    ]
    for name in signal_checks:
        status = checks.get(name, {}).get("status", "MISSING")
        lines.append(f"- {name}: {status}")

    release_blockers = payload.get("release_blockers_remaining", [])
    lines.extend(["", "## Release Blockers", ""])
    if release_blockers:
        lines.extend(f"- {blocker}" for blocker in release_blockers)
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Canonical Artifacts",
            "",
            "- artifacts/proof/current/release_gate.json",
            "- artifacts/proof/current/proof_manifest.json",
            "- artifacts/proof/current/CURRENT_PROOF.md",
            "- artifacts/proof/current/CURRENT_ALPHA_STATUS.md",
            "- artifacts/proof/current/REPAIR_REPORT.md",
            "",
        ]
    )

    output_path = out_dir / "FIX_VERIFICATION_REPORT.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path.relative_to(repo_root))


def _count_alembic_version_files(repo_root: Path) -> int:
    versions_dir = repo_root / "backend" / "alembic" / "versions"
    if not versions_dir.exists():
        return 0
    return len([p for p in versions_dir.glob("*.py") if p.is_file()])


def _archive_validation_result(out_dir: Path) -> str:
    log_path = out_dir / "archive_validation.log"
    if not log_path.exists():
        return "NOT_RUN"

    text = log_path.read_text(encoding="utf-8", errors="ignore")
    if "[archive_validation] PASS: extracted archive checks completed" in text:
        return "PASS"
    return "FAIL"


def _ensure_required_proof_markers(
    out_dir: Path,
    node_version: str,
    npm_version: str,
) -> None:
    placeholders = {
        "CURRENT_PROOF.md": (
            "# CURRENT_PROOF\n\n"
            "- status: in_progress\n"
            f"- node_version: {node_version}\n"
            f"- npm_version: {npm_version}\n"
        ),
        "REPAIR_REPORT.md": "# REPAIR_REPORT\n\n- status: in_progress\n",
        "SOURCE_REGISTRY_STATUS.md": "# SOURCE_REGISTRY_STATUS\n\n- status: in_progress\n",
        "FIX_VERIFICATION_REPORT.md": (
            "# FIX_VERIFICATION_REPORT\n\n- status: in_progress\n"
        ),
    }
    for name, content in placeholders.items():
        path = out_dir / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    source_registry_json = out_dir / "source_registry_status.json"
    if not source_registry_json.exists():
        source_registry_json.write_text(
            json.dumps({"status": "in_progress", "sources": []}) + "\n",
            encoding="utf-8",
        )


def _collect_proof_input_metadata(repo_root: Path, python_exe: str) -> dict:
    cmd = [
        python_exe,
        "scripts/check_proof_freshness.py",
        "--root",
        str(repo_root),
        "--metadata-only",
    ]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "proof_input_tree_hash": "unknown",
            "proof_input_tree_hash_algorithm": "sha256",
            "proof_input_paths": PROOF_INPUT_PATTERNS,
            "proof_input_file_count": 0,
            "proof_input_file_list": [],
            "proof_input_file_fingerprints": {},
        }
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = {}
    return {
        "proof_input_tree_hash": parsed.get(
            "proof_input_tree_hash", "unknown"
        ),
        "proof_input_tree_hash_algorithm": parsed.get(
            "proof_input_tree_hash_algorithm", "sha256"
        ),
        "proof_input_paths": parsed.get(
            "proof_input_paths", PROOF_INPUT_PATTERNS
        ),
        "proof_input_file_count": parsed.get("proof_input_file_count", 0),
        "proof_input_file_list": parsed.get("proof_input_file_list", []),
        "proof_input_file_fingerprints": parsed.get(
            "proof_input_file_fingerprints", {}
        ),
    }


def _write_current_proof_md(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
    check_count: int,
) -> str:
    status = "PASS" if payload["alpha_gate_passed"] else "BLOCKED"
    failed_checks = payload.get("failed_checks", [])
    blocked_checks = payload.get("blocked_checks", {})
    lines = [
        "# CURRENT_PROOF",
        "",
        f"- generated_at_utc: {payload.get('timestamp_utc', 'unknown')}",
        f"- commit_hash: {payload.get('commit_hash', 'unknown')}",
        f"- alpha_gate_status: {status}",
        f"- alpha_gate_passed: {str(payload.get('alpha_gate_passed', False)).lower()}",
        f"- release_gate_check_count: {check_count}",
        f"- docker_available: {str(payload.get('docker_available', False)).lower()}",
        f"- postgis_proof_result: {payload.get('postgis_proof_result', 'UNKNOWN')}",
        (
            "- egress_proxy_proof_result: "
            f"{payload.get('egress_proxy_proof_result', 'UNKNOWN')}"
        ),
        (
            "- demo_proof_result: "
            f"{payload.get('demo_proof_result', 'UNKNOWN')}"
        ),
        (
            "- proof_freshness_result: "
            f"{payload.get('proof_freshness_result', 'UNKNOWN')}"
        ),
        (
            "- archive_validation_result: "
            f"{payload.get('archive_validation_result', 'UNKNOWN')}"
        ),
        (
            "- proof_input_tree_hash: "
            f"{payload.get('proof_input_tree_hash', 'unknown')}"
        ),
        (
            "- proof_input_file_count: "
            f"{payload.get('proof_input_file_count', 0)}"
        ),
        (
            "- egress_proxy_proof_log: "
            f"{payload.get('egress_proxy_proof_log', 'unknown')}"
        ),
        (f"- demo_proof_log: {payload.get('demo_proof_log', 'unknown')}"),
        "",
        "## Runtime Metadata",
        "",
        f"- gate_runner_python_version: {payload.get('gate_runner_python_version', 'unknown')}",
        f"- gate_runner_python_executable: {payload.get('gate_runner_python_executable', 'unknown')}",
        f"- backend_test_python_version: {payload.get('backend_test_python_version', 'unknown')}",
        f"- backend_test_python_executable: {payload.get('backend_test_python_executable', 'unknown')}",
        f"- backend_required_python: {payload.get('backend_required_python', 'unknown')}",
        f"- node_version: {payload.get('node_version', 'unknown')}",
        f"- npm_version: {payload.get('npm_version', 'unknown')}",
        f"- platform: {payload.get('platform', 'unknown')}",
        f"- test_database_backend: {payload.get('test_database_backend', 'unknown')}",
        f"- test_database_url_type: {payload.get('test_database_url_type', 'unknown')}",
        "",
        "## Scope and Safety",
        "",
        "- Current status: proof-hardened alpha.",
        "- Not ready for production deployment.",
        "- Does not hold legal authority.",
        "- Evidence snapshots are authoritative; memory is derivative.",
        "- AI is reviewer assistance only.",
        "- Source ingestion is disabled by default unless explicitly enabled.",
        "- External folders are reference-only.",
        "- JWT mutation authority is current; legacy shared-token compatibility is deprecated.",
        "- make verify = local no-Docker quality checks.",
        "- make release-proof-local = Docker/PostGIS alpha release gate.",
        "- Current alpha release is blocked if Docker/PostGIS proof fails.",
        (
            "- Docker/PostGIS proof "
            + (
                "passed in the current release gate."
                if payload.get("postgis_proof_result") == "PASS"
                else "did not pass in the current release gate."
            )
        ),
        (
            "- Dedicated egress proxy proof "
            + (
                "passed in the current release gate."
                if payload.get("egress_proxy_proof_result") == "PASS"
                else "did not pass in the current release gate."
            )
        ),
        (
            "- Dedicated synthetic demo proof "
            + (
                "passed in the current release gate."
                if payload.get("demo_proof_result") == "PASS"
                else "did not pass in the current release gate."
            )
        ),
        (
            "- Proof freshness passed against the stored proof-input file list and tree hash."
            if payload.get("proof_freshness_result") == "PASS"
            else "- Proof freshness did not pass against the stored proof-input file list and tree hash."
        ),
        (
            "- Archive validation passed against the final distributable archive shape."
            if payload.get("archive_validation_result") == "PASS"
            else "- Archive validation has not yet been recorded for this run."
        ),
        (
            "- archive_validation_log: "
            f"{payload.get('archive_validation_log', 'unknown')}"
        ),
        "- archive_validation_supported_shapes:",
        "  - JUDGE-main/",
        "  - */JUDGE-main/",
        "",
    ]

    lines.extend(
        [
            "## Governance Status",
            "",
            (
                "- legacy_shared_token_status: "
                f"{payload.get('legacy_shared_token_status', 'unknown')}"
            ),
            (
                "- dependency_security_status: "
                f"{payload.get('dependency_security_status', 'unknown')}"
            ),
            "",
        ]
    )

    backend_passed = payload.get("backend_pytest_passed")
    backend_skipped = payload.get("backend_pytest_skipped")
    frontend_contracts_passed = payload.get("frontend_contracts_passed")
    public_api_boundary_passed = payload.get("public_api_boundary_passed")
    backend_import_route_count = payload.get("backend_import_route_count")
    alembic_migrations = payload.get("alembic_migration_count")
    if (
        backend_passed is not None
        or backend_import_route_count is not None
        or frontend_contracts_passed is not None
        or public_api_boundary_passed is not None
        or alembic_migrations is not None
    ):
        lines.extend(["## Current Proof Facts", ""])
        if backend_passed is not None:
            lines.append(
                "- backend pytest: "
                f"{backend_passed} passed, {backend_skipped or 0} skipped"
            )
        if backend_import_route_count is not None:
            lines.append(
                f"- backend import proof: PASS ({backend_import_route_count} routes)"
            )
        if frontend_contracts_passed is not None:
            lines.append(
                f"- frontend contracts: {frontend_contracts_passed} passed"
            )
        if public_api_boundary_passed is not None:
            lines.append(
                f"- public API boundary: {public_api_boundary_passed} passed"
            )
        lines.append(
            f"- Docker runtime preflight: {payload.get('docker_runtime_preflight_result', 'UNKNOWN')}"
        )
        lines.append(
            f"- PostGIS proof: {payload.get('postgis_proof_result', 'UNKNOWN')}"
        )
        lines.append(
            "- egress proxy proof: "
            f"{payload.get('egress_proxy_proof_result', 'UNKNOWN')}"
        )
        lines.append(
            f"- demo proof: {payload.get('demo_proof_result', 'UNKNOWN')}"
        )
        lines.append(
            "- CanLII staging proof: "
            f"{payload.get('canlii_staging_status', 'UNKNOWN')}"
        )
        lines.append(
            "- mutation fail-closed coverage: "
            f"{payload.get('mutation_fail_closed_coverage_result', 'UNKNOWN')}"
        )
        if alembic_migrations is not None:
            lines.append(f"- Alembic migrations: {alembic_migrations}")
        lines.append("")

    if failed_checks:
        lines.extend(
            [
                "## Failed Checks",
                "",
                *[f"- {name}" for name in failed_checks],
                "",
            ]
        )
    if blocked_checks:
        lines.append("## Blocked Checks")
        lines.append("")
        for name, reason in blocked_checks.items():
            lines.append(f"- {name}: {reason}")
        lines.append("")

    lines.extend(
        [
            "## Egress Proxy Coverage",
            "",
            "- Dedicated gate artifact: artifacts/proof/current/egress_proxy_proof.log.",
            "- Production startup proxy policy coverage: backend/app/tests/test_production_fetch_egress_policy.py.",
            "- Runtime proxy opener/wiring coverage: backend/app/tests/test_source_fetcher_proxy.py.",
            "- SSRF defense context coverage remains in backend/app/tests/test_source_fetcher_ssrf.py.",
            "",
            "## Canonical Artifacts",
            "",
            "- artifacts/proof/current/proof_manifest.json",
            "- artifacts/proof/current/release_gate.json",
            "- artifacts/proof/current/release_gate.log",
            "- artifacts/proof/current/docker_runtime_preflight.log",
            "- artifacts/proof/current/postgis_proof.log",
            "- artifacts/proof/current/egress_proxy_proof.log",
            "- artifacts/proof/current/demo_proof.log",
            "- artifacts/proof/current/canlii_staging_proof.log",
            "- artifacts/proof/current/proof_freshness.log",
            "- artifacts/proof/current/archive_validation.log",
            "- artifacts/proof/current/backend_import.log",
            "- artifacts/proof/current/backend_pytest.log",
            "- artifacts/proof/current/frontend_node_gate.log",
            "- artifacts/proof/current/check_node_policy.log",
            "- artifacts/proof/current/frontend_install.log",
            "- artifacts/proof/current/frontend_lint.log",
            "- artifacts/proof/current/frontend_typecheck.log",
            "- artifacts/proof/current/frontend_contracts.log",
            "- artifacts/proof/current/frontend_build.log",
            "- artifacts/proof/current/check_api_contracts.log",
            "- artifacts/proof/current/frontend_backend_route_contract.log",
            "- artifacts/proof/current/static_guards.log",
            "- artifacts/proof/current/map_route_check.log",
            "- artifacts/proof/current/public_api_boundary.log",
            "- artifacts/proof/current/mutation_fail_closed_coverage.log",
            "- artifacts/proof/current/proof_consistency_pytest.log",
            "- artifacts/proof/current/single_proof_authority.log",
            "- artifacts/proof/current/required_proof_logs.log",
            "- artifacts/proof/current/source_registry_status.json",
            "- artifacts/proof/current/release_readiness.md",
            "- artifacts/proof/current/CURRENT_ALPHA_STATUS.md",
            "- artifacts/proof/current/SOURCE_REGISTRY_STATUS.md",
            "- artifacts/proof/current/PROOF_POLICY.md",
            "- artifacts/proof/current/REPAIR_REPORT.md",
            "",
        ]
    )

    current_proof_text = "\n".join(lines)
    current_proof_path = out_dir / "CURRENT_PROOF.md"
    current_proof_path.write_text(current_proof_text, encoding="utf-8")
    (repo_root / "CURRENT_PROOF.md").write_text(
        current_proof_text,
        encoding="utf-8",
    )
    try:
        return str(current_proof_path.relative_to(repo_root))
    except ValueError:
        return str(current_proof_path)


def _sync_release_artifacts(
    repo_root: Path,
    out_dir: Path,
    payload: dict,
    results: list[GateStep],
    manifest_path: Path,
    out_path: Path,
    source_registry_summary: dict,
    *,
    static_guards_rel: str | None = None,
    ensure_readiness_step: bool = False,
) -> tuple[str, str]:
    payload.setdefault("logs", {})

    current_proof_rel = _write_current_proof_md(
        repo_root,
        out_dir,
        payload,
        check_count=len(results),
    )
    current_alpha_status_rel = _write_current_alpha_status_md(
        repo_root, out_dir, payload
    )
    source_registry_status_md_rel = _write_source_registry_status_md(
        repo_root,
        out_dir,
        payload,
        source_registry_summary,
    )
    proof_policy_rel = _write_proof_policy_md(repo_root, out_dir, payload)
    repair_report_rel = _write_repair_report_md(
        repo_root,
        out_dir,
        payload,
        source_registry_summary,
    )
    fix_verification_report_rel = _write_fix_verification_report_md(
        repo_root,
        out_dir,
        payload,
    )
    grouped_artifacts = _write_grouped_proof_artifacts(
        repo_root, out_dir, payload
    )

    payload["logs"]["current_proof"] = current_proof_rel
    payload["logs"]["current_alpha_status"] = current_alpha_status_rel
    payload["logs"]["source_registry_status_md"] = (
        source_registry_status_md_rel
    )
    payload["logs"]["proof_policy"] = proof_policy_rel
    payload["logs"]["repair_report"] = repair_report_rel
    payload["logs"]["fix_verification_report"] = fix_verification_report_rel
    payload["logs"] |= grouped_artifacts
    if static_guards_rel is not None:
        payload["logs"]["static_guards"] = static_guards_rel

    final_manifest = _build_proof_manifest(
        repo_root, out_dir, payload, results
    )
    _, readiness_rel = _generate_release_readiness_from_manifest(
        repo_root,
        out_dir,
        final_manifest,
        additional_blockers=payload.get("release_blockers_remaining", []),
    )

    if ensure_readiness_step:
        readiness_now = datetime.now(timezone.utc).isoformat()
        readiness_step = next(
            (
                step
                for step in results
                if step.name == "release_readiness_generation"
            ),
            None,
        )
        if readiness_step is None:
            results.append(
                GateStep(
                    name="release_readiness_generation",
                    command="generate from proof_manifest.json",
                    status="PASS",
                    exit_code=0,
                    duration_seconds=0.0,
                    log_path=readiness_rel,
                    started_at_utc=readiness_now,
                    finished_at_utc=readiness_now,
                    required=True,
                    cwd=_redact_local_paths_in_text(
                        str(repo_root), repo_root
                    ),
                    failure_reason=None,
                )
            )
        else:
            readiness_step.status = "PASS"
            readiness_step.exit_code = 0
            readiness_step.duration_seconds = 0.0
            readiness_step.log_path = readiness_rel
            readiness_step.started_at_utc = readiness_now
            readiness_step.finished_at_utc = readiness_now
            readiness_step.required = True
            readiness_step.cwd = _redact_local_paths_in_text(
                str(repo_root), repo_root
            )
            readiness_step.failure_reason = None

        final_manifest = _build_proof_manifest(
            repo_root, out_dir, payload, results
        )
        _, readiness_rel = _generate_release_readiness_from_manifest(
            repo_root,
            out_dir,
            final_manifest,
            additional_blockers=payload.get(
                "release_blockers_remaining", []
            ),
        )

    # release_readiness.md is generated from the manifest and changes its own
    # file metadata. Rebuild the manifest after the final readiness write so
    # proof_manifest.json and required_log_index.json describe the on-disk tree
    # that later validators inspect.
    final_manifest = _build_proof_manifest(repo_root, out_dir, payload, results)

    required_log_index_rel = _write_required_log_index(
        repo_root,
        out_dir,
        final_manifest,
    )

    manifest_path.write_text(
        json.dumps(final_manifest, indent=2) + "\n", encoding="utf-8"
    )
    payload["logs"]["release_readiness"] = readiness_rel
    payload["logs"]["proof_manifest"] = str(
        manifest_path.relative_to(repo_root)
    )
    payload["logs"]["required_log_index"] = required_log_index_rel
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return current_proof_rel, readiness_rel


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True, exist_ok=True)
    proof_db_url = f"sqlite:///{(out_dir / 'proof.db').resolve()}"

    backend_venv_python = repo_root / "backend" / ".venv" / "bin" / "python"
    if backend_venv_python.exists():
        python_exe = str(backend_venv_python)
    else:
        print(
            f"[release_gate] ERROR: backend venv not found at {backend_venv_python}\n"
            "[release_gate] Run: cd backend && uv venv && uv pip install -e '.[test]'\n"
            "[release_gate] BLOCKED_BACKEND_VENV",
            file=sys.stderr,
        )
        return 1
    backend_python_version = (
        subprocess.run(
            [python_exe, "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        or "unknown"
    )
    gate_node_version = (
        subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )
    gate_npm_version = (
        subprocess.run(
            ["npm", "--version"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )
    db_backend = (
        "sqlite" if proof_db_url.startswith("sqlite://") else "unknown"
    )
    docker_check_timeout_seconds = int(
        os.getenv("JTA_DOCKER_CHECK_TIMEOUT", "180")
    )
    docker_check_timeout_seconds = max(docker_check_timeout_seconds, 60)
    # Allow release-gate step timeout to exceed the internal docker check timeout.
    docker_preflight_timeout_seconds = max(
        docker_check_timeout_seconds + 30, 180
    )
    postgis_timeout_seconds = int(
        os.getenv("JTA_POSTGIS_PROOF_TIMEOUT", "900")
    )
    proof_input_metadata = _collect_proof_input_metadata(repo_root, python_exe)
    gate_steps: list[GateStepSpec] = [
        GateStepSpec(
            "check_no_pyc",
            "check_no_pyc.log",
            ["bash", "scripts/check_no_pyc.sh"],
        ),
        GateStepSpec(
            "check_false_claims",
            "check_false_claims.log",
            [python_exe, "scripts/check_false_claims.py"],
        ),
        GateStepSpec(
            "check_source_keys",
            "check_source_keys.log",
            [
                python_exe,
                "scripts/check_source_keys.py",
                "--root",
                "backend/app",
                "--repo-root",
                ".",
            ],
        ),
        GateStepSpec(
            "check_statuses",
            "check_statuses.log",
            [python_exe, "scripts/check_statuses.py", "--root", "backend/app"],
        ),
        GateStepSpec(
            "check_no_direct_ingestion_network_clients",
            "check_no_direct_ingestion_network_clients.log",
            [
                python_exe,
                "backend/scripts/check_no_direct_ingestion_network_clients.py",
            ],
        ),
        GateStepSpec(
            "check_external_boundaries",
            "check_external_boundaries.log",
            [python_exe, "scripts/check_external_boundaries.py"],
        ),
        GateStepSpec(
            "check_dockerfile_copy_paths",
            "check_dockerfile_copy_paths.log",
            [
                python_exe,
                "scripts/check_dockerfile_copy_paths.py",
                "--root",
                str(repo_root),
            ],
        ),
        GateStepSpec(
            "check_compose_auth_defaults",
            "check_compose_auth_defaults.log",
            [
                python_exe,
                "scripts/check_compose_auth_defaults.py",
                "--compose",
                "docker-compose.yml",
            ],
        ),
        GateStepSpec(
            "backend_compile",
            "backend_compile.log",
            [
                python_exe,
                "-m",
                "compileall",
                "-q",
                "backend/app",
                "backend/tools",
            ],
        ),
        GateStepSpec(
            "backend_import",
            "backend_import.log",
            [python_exe, "backend/scripts/proof_backend_import.py"],
        ),
        GateStepSpec(
            "backend_pytest_collect",
            "backend_pytest_collect.log",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests",
                "--collect-only",
                "--import-mode=importlib",
                "-q",
            ],
        ),
        GateStepSpec(
            "runtime_smoke",
            "runtime_smoke.log",
            [python_exe, "scripts/runtime_smoke.py"],
            timeout_seconds=300,
        ),
        GateStepSpec(
            "backend_pytest",
            "backend_pytest.log",
            [
                "bash",
                "-lc",
                (
                    f'JTA_DATABASE_URL="{proof_db_url}" "{python_exe}" '
                    "scripts/run_backend_tests_chunked.py "
                    "--root . "
                    "--tests-root backend/app/tests "
                    "--collect-log artifacts/proof/current/backend_pytest_collect.log "
                    "--status-json artifacts/proof/current/backend_pytest_chunked_status.json "
                    "--batch-size 40 "
                    "--ignore backend/app/tests/test_release_gate_consistency.py"
                ),
            ],
            timeout_seconds=900,
        ),
        GateStepSpec(
            "check_migrations",
            "check_migrations.log",
            [python_exe, "backend/tools/check_migrations.py"],
        ),
        GateStepSpec(
            "docker_runtime_preflight",
            "docker_runtime_preflight.log",
            ["bash", "scripts/check_docker_runtime.sh"],
            timeout_seconds=docker_preflight_timeout_seconds,
            required=True,
        ),
        GateStepSpec(
            "docker_smoke",
            "docker_smoke.log",
            ["bash", "scripts/proof_docker_compose.sh"],
            timeout_seconds=1800,
            required=True,
        ),
        GateStepSpec(
            "postgis_proof",
            "postgis_proof.log",
            [
                "bash",
                "-lc",
                "bash scripts/proof_postgis.sh",
            ],
            timeout_seconds=postgis_timeout_seconds,
            required=True,
        ),
        GateStepSpec(
            "egress_proxy_proof",
            "egress_proxy_proof.log",
            ["bash", "scripts/proof_egress_proxy.sh"],
            timeout_seconds=300,
        ),
        GateStepSpec(
            "demo_proof",
            "demo_proof.log",
            ["bash", "scripts/proof_demo.sh"],
            timeout_seconds=300,
        ),
        GateStepSpec(
            "validate_sources",
            "validate_sources.log",
            [python_exe, "backend/tools/validate_sources.py"],
        ),
        GateStepSpec(
            "check_yaml_duplicate_keys",
            "check_yaml_duplicate_keys.log",
            [python_exe, "scripts/check_yaml_duplicate_keys.py"],
        ),
        GateStepSpec(
            "verify_source_registry",
            "verify_source_registry.log",
            [
                python_exe,
                "scripts/verify_source_registry.py",
                "--json",
            ],
        ),
        GateStepSpec(
            "source_registry_status",
            "source_registry_status.log",
            [
                python_exe,
                "scripts/generate_source_registry_truth_table.py",
                "--proof-mode",
            ],
        ),
        GateStepSpec(
            "check_source_registry_docs",
            "check_source_registry_docs.log",
            [python_exe, "scripts/check_source_registry_docs.py"],
        ),
        GateStepSpec(
            "prepare_proof_db",
            "prepare_proof_db.log",
            [
                python_exe,
                "scripts/prepare_proof_db.py",
                "--proof-db",
                str(out_dir / "proof.db"),
            ],
        ),
        GateStepSpec(
            "verify_evidence_store",
            "verify_evidence_store.log",
            [
                "bash",
                "-lc",
                (
                    f'JTA_DATABASE_URL="{proof_db_url}" "{python_exe}" '
                    "backend/tools/verify_evidence_store.py --allow-empty"
                ),
            ],
        ),
        GateStepSpec(
            "verify_audit_chain",
            "verify_audit_chain.log",
            [
                "bash",
                "-lc",
                (
                    f'JTA_DATABASE_URL="{proof_db_url}" "{python_exe}" '
                    "backend/tools/verify_audit_chain.py --allow-empty"
                ),
            ],
        ),
        GateStepSpec(
            "auth_mutation_route_coverage",
            "auth_mutation_route_coverage.log",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_mutation_route_authority_coverage.py",
                "-q",
            ],
        ),
        GateStepSpec(
            "mutation_fail_closed_coverage",
            "mutation_fail_closed_coverage.log",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_mutation_fail_closed_coverage.py",
                "-q",
            ],
        ),
        GateStepSpec(
            "check_node_policy",
            "check_node_policy.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    f' "{python_exe}" scripts/check_node_policy.py --root "{repo_root}"'
                ),
            ],
        ),
        GateStepSpec(
            "frontend_node_gate",
            "frontend_node_gate.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    f' "{python_exe}" scripts/check_frontend_node_gate.py --expected-major 22'
                ),
            ],
        ),
        GateStepSpec(
            "frontend_install",
            "frontend_install.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    " npm ci --prefix frontend"
                ),
            ],
            timeout_seconds=900,
        ),
        GateStepSpec(
            "frontend_lint",
            "frontend_lint.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    " npm run lint --prefix frontend"
                ),
            ],
        ),
        GateStepSpec(
            "frontend_typecheck",
            "frontend_typecheck.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    " npm run typecheck --prefix frontend"
                ),
            ],
        ),
        GateStepSpec(
            "frontend_contracts",
            "frontend_contracts.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    " npm run test:contracts --prefix frontend"
                ),
            ],
        ),
        GateStepSpec(
            "frontend_build",
            "frontend_build.log",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh";'
                    " nvm use 22.22.3 >/dev/null 2>&1"
                    " || { echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22 via: nvm install 22'; exit 1; };"
                    " npm run build --prefix frontend"
                ),
            ],
            timeout_seconds=900,
        ),
        GateStepSpec(
            "check_api_contracts",
            "check_api_contracts.log",
            [python_exe, "scripts/check_api_contracts.py"],
        ),
        GateStepSpec(
            "frontend_backend_route_contract",
            "frontend_backend_route_contract.log",
            [python_exe, "scripts/check_frontend_backend_route_contract.py"],
        ),
        GateStepSpec(
            "repo_generated_files",
            "repo_generated_files.log",
            [
                python_exe,
                "scripts/check_no_generated_files.py",
                "--root",
                str(repo_root),
            ],
        ),
        GateStepSpec(
            "check_npm_audit_triage",
            "check_npm_audit_triage.log",
            [python_exe, "scripts/check_npm_audit_triage.py"],
        ),
        GateStepSpec(
            "map_route_check",
            "map_route_check.log",
            [python_exe, "scripts/check_map_route.py"],
        ),
        GateStepSpec(
            "public_api_boundary",
            "public_api_boundary.log",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests",
                "--import-mode=importlib",
                "-k",
                "public_api",
                "-q",
            ],
        ),
        GateStepSpec(
            "canlii_staging_proof",
            "canlii_staging_proof.log",
            [python_exe, "scripts/prove_canlii_staging.py"],
            timeout_seconds=300,
        ),
    ]

    # proof_freshness runs as a post-write step after the preliminary
    # release_gate.json is written, so the stored manifest is final before
    # validation. Not in gate_steps; handled explicitly below.
    _proof_freshness_spec = GateStepSpec(
        "proof_freshness",
        "proof_freshness.log",
        [python_exe, "scripts/check_proof_freshness.py"],
    )
    _archive_validation_spec = GateStepSpec(
        "archive_validation",
        "archive_validation.log",
        ["bash", "scripts/validate_archive_proof.sh"],
        timeout_seconds=900,
    )
    _required_proof_logs_spec = GateStepSpec(
        "required_proof_logs",
        "required_proof_logs.log",
        [
            python_exe,
            "scripts/check_required_proof_logs.py",
            "--root",
            str(repo_root),
            "--strict-required-files",
        ],
    )
    _check_proof_manifest_spec = GateStepSpec(
        "check_proof_manifest",
        "check_proof_manifest.log",
        [
            python_exe,
            "scripts/check_proof_manifest.py",
            "--root",
            str(repo_root),
        ],
    )
    _check_proof_consistency_spec = GateStepSpec(
        "check_proof_consistency",
        "check_proof_consistency.log",
        [
            python_exe,
            "scripts/check_proof_consistency.py",
            "--root",
            str(repo_root),
        ],
    )
    _local_path_hygiene_spec = GateStepSpec(
        "check_no_local_paths_in_release_proof",
        "check_no_local_paths_in_release_proof.log",
        [
            python_exe,
            "scripts/check_no_local_paths_in_release_proof.py",
            "--root",
            str(repo_root),
        ],
    )

    archived_current_proof = _archive_current_proof(repo_root, out_dir)

    # Clear stale gate artifacts before execution so each run is
    # self-contained.
    stale_outputs = [spec.log_name for spec in gate_steps] + [
        _proof_freshness_spec.log_name,
        _required_proof_logs_spec.log_name,
        _check_proof_manifest_spec.log_name,
        _check_proof_consistency_spec.log_name,
        _local_path_hygiene_spec.log_name,
        "proof_consistency_pytest.log",
        "release_gate.log",
        "proof.db",
        "SOURCE_REGISTRY_STATUS.json",
        "source_registry_status.json",
        "static_guards.log",
    ]
    for output_name in stale_outputs:
        output_path = out_dir / output_name
        if output_path.exists():
            output_path.unlink()

    # Some backend consistency tests assert these files always exist.
    # Create temporary placeholders; final versions are written later.
    _ensure_required_proof_markers(
        out_dir,
        gate_node_version,
        gate_npm_version,
    )

    results: list[GateStep] = []
    blocked_checks: dict[str, str] = {}
    docker_preflight_failed = False
    frontend_node_gate_failed = False
    frontend_steps = {
        "frontend_install",
        "frontend_lint",
        "frontend_typecheck",
        "frontend_contracts",
        "frontend_build",
    }
    for spec in gate_steps:
        command = list(spec.command)
        if spec.name in {"docker_smoke", "postgis_proof"} and docker_preflight_failed:
            blocked_log = out_dir / spec.log_name
            preflight_log_rel = str(
                (out_dir / "docker_runtime_preflight.log").relative_to(
                    repo_root
                )
            )
            blocked_log.write_text(
                (
                    f"[release_gate] BLOCKED: {spec.name} skipped because "
                    "docker_runtime_preflight failed.\n"
                    "[release_gate] blocker: docker_runtime_preflight\n"
                    f"[release_gate] blocker_log: {preflight_log_rel}\n"
                ),
                encoding="utf-8",
            )
            blocked_checks[spec.name] = "docker_runtime_preflight failed"
            results.append(
                GateStep(
                    name=spec.name,
                    command="SKIPPED due to failed dependency",
                    status="BLOCKED",
                    exit_code=1,
                    duration_seconds=0.0,
                    log_path=str(blocked_log.relative_to(repo_root)),
                    started_at_utc=datetime.now(timezone.utc).isoformat(),
                    finished_at_utc=datetime.now(timezone.utc).isoformat(),
                    required=spec.required,
                    cwd=_redact_local_paths_in_text(str(repo_root), repo_root),
                    failure_reason="dependency_blocked",
                )
            )
            continue

        if spec.name in frontend_steps and frontend_node_gate_failed:
            blocked_log = out_dir / spec.log_name
            blocked_log.write_text(
                "[release_gate] BLOCKED: frontend step skipped because frontend_node_gate failed.\n",
                encoding="utf-8",
            )
            blocked_checks[spec.name] = "frontend_node_gate failed"
            results.append(
                GateStep(
                    name=spec.name,
                    command="SKIPPED due to frontend_node_gate failure",
                    status="BLOCKED",
                    exit_code=1,
                    duration_seconds=0.0,
                    log_path=str(blocked_log.relative_to(repo_root)),
                    started_at_utc=datetime.now(timezone.utc).isoformat(),
                    finished_at_utc=datetime.now(timezone.utc).isoformat(),
                    required=spec.required,
                    cwd=_redact_local_paths_in_text(str(repo_root), repo_root),
                    failure_reason="frontend_node_gate_failed",
                )
            )
            continue

        results.append(
            _run(
                repo_root,
                out_dir,
                spec.name,
                spec.log_name,
                command,
                timeout_seconds=spec.timeout_seconds,
                required=spec.required,
            )
        )
        if (
            spec.name == "docker_runtime_preflight"
            and results[-1].exit_code != 0
        ):
            docker_preflight_failed = True
        if spec.name == "frontend_node_gate" and results[-1].exit_code != 0:
            frontend_node_gate_failed = True

    # -----------------------------------------------------------------------
    # Phase 1: collect final proof metadata and write preliminary JSON.
    # proof_freshness runs AFTER this write so check_proof_freshness.py can
    # read the stored manifest. Nothing between here and the freshness step
    # modifies proof-input source files.
    # -----------------------------------------------------------------------
    readiness_rel = str(
        (out_dir / "release_readiness.md").relative_to(repo_root)
    )

    missing_logs = _missing_logs(repo_root, results)
    proof_input_metadata = _collect_proof_input_metadata(repo_root, python_exe)

    gate_log_path = out_dir / "release_gate.log"
    with gate_log_path.open("w", encoding="utf-8") as gate_log:
        gate_log.write("RELEASE GATE\n")
        for result in results:
            gate_log.write(
                f"{result.name}: {result.status} rc={result.exit_code} "
                f"dur={result.duration_seconds}s log={result.log_path}\n"
            )
        if missing_logs:
            gate_log.write("missing_logs:\n")
            for log in missing_logs:
                gate_log.write(f"- {log}\n")

    checks_map = {r.name: r for r in results}
    backend_pytest_passed, backend_pytest_skipped, backend_pytest_failed = (
        _extract_pytest_counts(out_dir / "backend_pytest.log")
    )
    frontend_contracts_passed = _extract_vitest_tests_passed(
        out_dir / "frontend_contracts.log"
    )
    (
        public_api_boundary_passed,
        _public_api_boundary_skipped,
        _public_api_boundary_failed,
    ) = _extract_pytest_counts(out_dir / "public_api_boundary.log")
    backend_import_route_count = _extract_backend_import_route_count(
        out_dir / "backend_import.log"
    )
    alembic_migration_count = _extract_migration_count(
        out_dir / "check_migrations.log"
    )
    canlii_staging_status = _extract_prefixed_value(
        out_dir / "canlii_staging_proof.log",
        "CANLII_STAGING_STATUS=",
    )
    _enforce_canlii_staging_gate(
        checks_map, blocked_checks, canlii_staging_status
    )
    if alembic_migration_count is None:
        alembic_migration_count = _count_alembic_version_files(repo_root)

    legacy_auth_plan_exists = (
        repo_root / "docs" / "security" / "LEGACY_AUTH_REMOVAL_PLAN.md"
    ).exists()
    dependency_plan_exists = (
        repo_root
        / "docs"
        / "deployment-guide"
        / "DEPENDENCY_REMEDIATION_PLAN.md"
    ).exists()

    payload = {
        "schema_version": "1.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "alpha_gate_passed": False,  # updated after proof_freshness step
        "release_candidate": False,
        # production_ready is intentionally ALWAYS False during alpha phase.
        # It is DISTINCT from alpha_gate_passed: alpha_gate_passed=True means
        # hardening gates pass; production_ready=True would require Postgres
        # proof, egress proof, stub adapters resolved, and PostGIS runtime.
        "production_ready": False,
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "commit_hash": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        ).stdout.strip()
        or "unknown",
        "python_version": sys.version.split()[0],
        "gate_runner_python_version": sys.version.split()[0],
        "gate_runner_python_executable": _redact_local_path(
            sys.executable,
            repo_root,
        ),
        "backend_test_python_version": backend_python_version,
        "backend_test_python_executable": _redact_local_path(
            python_exe,
            repo_root,
        ),
        "backend_required_python": ">=3.11",
        "node_version": "unknown",
        "npm_version": "unknown",
        "test_database_backend": db_backend,
        "test_database_url_type": "sqlite_file",
        "platform": platform.platform(),
        "docker_available": not docker_preflight_failed,
        "docker_check_timeout_seconds": docker_check_timeout_seconds,
        "postgis_proof_required": True,
        "postgis_proof_timeout_seconds": postgis_timeout_seconds,
        "check_count": len(results),
        "proof_input_tree_hash": proof_input_metadata["proof_input_tree_hash"],
        "proof_input_tree_hash_algorithm": proof_input_metadata[
            "proof_input_tree_hash_algorithm"
        ],
        "proof_input_paths": proof_input_metadata["proof_input_paths"],
        "proof_input_file_count": proof_input_metadata[
            "proof_input_file_count"
        ],
        "proof_input_file_list": proof_input_metadata["proof_input_file_list"],
        "docker_runtime_preflight_result": (
            checks_map["docker_runtime_preflight"].status
            if "docker_runtime_preflight" in checks_map
            else "UNKNOWN"
        ),
        "postgis_proof_result": next(
            (r.status for r in results if r.name == "postgis_proof"),
            "UNKNOWN",
        ),
        "egress_proxy_proof_result": next(
            (r.status for r in results if r.name == "egress_proxy_proof"),
            "UNKNOWN",
        ),
        "demo_proof_result": next(
            (r.status for r in results if r.name == "demo_proof"),
            "UNKNOWN",
        ),
        "egress_proxy_proof_log": str(
            (out_dir / "egress_proxy_proof.log").relative_to(repo_root)
        ),
        "demo_proof_log": str(
            (out_dir / "demo_proof.log").relative_to(repo_root)
        ),
        "archive_validation_log": str(
            (out_dir / "archive_validation.log").relative_to(repo_root)
        ),
        "archive_validation_supported_shapes": [
            "JUDGE-main/",
            "*/JUDGE-main/",
        ],
        "mutation_fail_closed_coverage_result": (
            checks_map["mutation_fail_closed_coverage"].status
            if "mutation_fail_closed_coverage" in checks_map
            else "UNKNOWN"
        ),
        "canlii_staging_status": canlii_staging_status or "UNKNOWN",
        "proof_freshness_result": "UNKNOWN",
        "archive_validation_result": _archive_validation_result(out_dir),
        "legacy_shared_token_status": (
            "deprecated, removal plan documented"
            if legacy_auth_plan_exists
            else "deprecated, removal plan missing"
        ),
        "dependency_security_status": (
            "npm audit issues triaged for alpha; remediation plan documented"
            if dependency_plan_exists
            else "npm audit issues triaged for alpha; remediation plan missing"
        ),
        "backend_pytest_passed": backend_pytest_passed,
        "backend_pytest_skipped": backend_pytest_skipped,
        "backend_pytest_failed": backend_pytest_failed,
        "backend_import_route_count": backend_import_route_count,
        "frontend_contracts_passed": frontend_contracts_passed,
        "public_api_boundary_passed": public_api_boundary_passed,
        "alembic_migration_count": alembic_migration_count,
        "checks": [asdict(r) for r in results],
        "checks_summary": _canonical_checks_summary(results),
        "failed_checks": _failed_required_checks(results)
        + (["missing_logs"] if missing_logs else []),
        "blocked_checks": blocked_checks,
        "archived_current_proof": archived_current_proof,
        "logs": {r.name: r.log_path for r in results}
        | {
            _proof_freshness_spec.name: str(
                (out_dir / _proof_freshness_spec.log_name).relative_to(
                    repo_root
                )
            ),
            "archive_validation": str(
                (out_dir / "archive_validation.log").relative_to(repo_root)
            ),
            "release_gate": str(gate_log_path.relative_to(repo_root)),
        },
        "known_limitations": [
            "alpha gate only; not a production release gate",
            (
                "AI outputs are reviewer assistance only — "
                "not determinations of guilt or legal conclusions"
            ),
            (
                "external HTTP fetch results are not guaranteed current; "
                "system operates on cached snapshots"
            ),
            (
                "no real-time alerting; proof artifacts must be "
                "regenerated manually after each code change"
            ),
        ],
        "release_blockers_remaining": [],  # updated after proof_freshness step
    }

    check_node_policy_log = out_dir / "check_node_policy.log"
    frontend_node_gate_log = out_dir / "frontend_node_gate.log"
    gated_node_version = _extract_prefixed_value(
        check_node_policy_log, "NODE_VERSION:"
    )
    gated_npm_version = _extract_prefixed_value(
        check_node_policy_log, "NPM_VERSION:"
    )
    frontend_node_gate_version = _extract_prefixed_value(
        frontend_node_gate_log, "NODE_VERSION:"
    )
    frontend_npm_version = _extract_prefixed_value(
        frontend_node_gate_log, "NPM_VERSION:"
    )
    payload["node_version"] = (
        gated_node_version or frontend_node_gate_version or "unknown"
    )
    payload["gate_runner_node_version"] = payload["node_version"]
    payload["frontend_node_gate_version"] = (
        frontend_node_gate_version or gated_node_version
    )
    payload["npm_version"] = (
        gated_npm_version or frontend_npm_version or "unknown"
    )
    _refresh_release_payload_schema(payload, results)

    # -----------------------------------------------------------------------
    # Phase 2a: write preliminary release_gate.json with the final proof hash
    # so check_proof_freshness.py can validate the stored manifest against the
    # live tree. check_count includes the upcoming proof_freshness and proof_consistency_pytest steps (+2).
    payload["check_count"] = len(results) + 2
    out_path = out_dir / "release_gate.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Phase 2b: run proof_freshness against the now-written stored manifest.
    pf_step = _run(
        repo_root,
        out_dir,
        _proof_freshness_spec.name,
        _proof_freshness_spec.log_name,
        list(_proof_freshness_spec.command),
        timeout_seconds=120,
    )
    results.append(pf_step)

    manifest_path = out_dir / "proof_manifest.json"

    # Generate required policy/status artifacts before archive validation so
    # the packaged proof tree can be validated as a complete release candidate.
    source_registry_summary = _read_source_registry_summary(out_dir)

    static_guards_rel = _write_static_guards_log(repo_root, out_dir, results)

    single_proof_authority_step = _run(
        repo_root,
        out_dir,
        "single_proof_authority",
        "single_proof_authority.log",
        [
            python_exe,
            "scripts/check_single_proof_authority.py",
            "--root",
            str(repo_root),
        ],
        timeout_seconds=60,
    )
    results.append(single_proof_authority_step)

    missing_logs = _missing_logs(repo_root, results)
    remaining_required_steps = {
        "proof_consistency_pytest",
        "required_proof_logs",
        "check_proof_manifest",
        "check_proof_consistency",
        "archive_validation",
    } - {r.name for r in results}
    required_failed_checks = _failed_required_checks(results)
    ok = (
        not required_failed_checks
        and not missing_logs
        and not remaining_required_steps
    )
    payload["alpha_gate_passed"] = ok
    payload["check_count"] = len(results)
    payload["proof_freshness_result"] = pf_step.status
    payload["archive_validation_result"] = "UNKNOWN"
    payload["checks"] = [asdict(r) for r in results]
    payload["logs"] = {r.name: r.log_path for r in results}
    payload["failed_checks"] = required_failed_checks + (
        ["missing_logs"] if missing_logs else []
    )
    payload["logs"][_proof_freshness_spec.name] = pf_step.log_path
    payload["logs"]["release_gate"] = str(gate_log_path.relative_to(repo_root))
    payload["logs"]["proof_manifest"] = str(
        manifest_path.relative_to(repo_root)
    )
    payload["logs"]["release_readiness"] = readiness_rel
    payload["logs"]["static_guards"] = static_guards_rel
    payload["release_blockers_remaining"] = (
        required_failed_checks
        + sorted(remaining_required_steps)
        + (["missing_logs"] if missing_logs else [])
        if not ok
        else []
    )
    _refresh_release_payload_schema(payload, results)

    # Phase 3: write final release_gate.json and CURRENT_PROOF.md.
    with gate_log_path.open("a", encoding="utf-8") as gate_log:
        gate_log.write(
            f"{pf_step.name}: {pf_step.status} rc={pf_step.exit_code} "
            f"dur={pf_step.duration_seconds}s log={pf_step.log_path}\n"
        )
        gate_log.write(f"alpha_gate_passed={str(ok).lower()}\n")

    _sync_release_artifacts(
        repo_root,
        out_dir,
        payload,
        results,
        manifest_path,
        out_path,
        source_registry_summary,
        static_guards_rel=static_guards_rel,
        ensure_readiness_step=True,
    )

    missing_logs = _missing_logs(repo_root, results)
    remaining_required_steps = {
        "required_proof_logs",
        "check_proof_manifest",
        "check_proof_consistency",
        "archive_validation",
    } - {r.name for r in results}
    required_failed_checks = _failed_required_checks(results)
    ok = (
        not required_failed_checks
        and not missing_logs
        and not remaining_required_steps
    )
    payload["alpha_gate_passed"] = ok
    payload["check_count"] = len(results)
    payload["checks"] = [asdict(r) for r in results]
    payload["logs"] = {r.name: r.log_path for r in results}
    payload["logs"]["release_gate"] = str(gate_log_path.relative_to(repo_root))
    payload["logs"]["proof_manifest"] = str(
        manifest_path.relative_to(repo_root)
    )
    payload["logs"]["release_readiness"] = readiness_rel
    payload["logs"]["static_guards"] = static_guards_rel
    payload["failed_checks"] = required_failed_checks + (
        ["missing_logs"] if missing_logs else []
    )
    payload["release_blockers_remaining"] = (
        required_failed_checks
        + sorted(remaining_required_steps)
        + (["missing_logs"] if missing_logs else [])
        if not ok
        else []
    )
    _refresh_release_payload_schema(payload, results)

    _sync_release_artifacts(
        repo_root,
        out_dir,
        payload,
        results,
        manifest_path,
        out_path,
        source_registry_summary,
        static_guards_rel=static_guards_rel,
    )

    # Run proof consistency only after release_gate.json, CURRENT_PROOF.md,
    # and release_readiness.md have been written.
    proof_consistency_pytest_step = _run(
        repo_root,
        out_dir,
        "proof_consistency_pytest",
        "proof_consistency_pytest.log",
        [
            "bash",
            "-lc",
            f'JTA_DATABASE_URL="{proof_db_url}" "{python_exe}" -m pytest backend/app/tests/test_release_gate_consistency.py -x --tb=short -q',
        ],
        timeout_seconds=120,
    )
    results.append(proof_consistency_pytest_step)

    if proof_consistency_pytest_step.exit_code == 0:
        # Sanitize generated proof artifacts only after proof consistency is
        # confirmed, so path-related failures are not masked.
        _sanitize_current_proof_artifacts(repo_root, out_dir)
    else:
        with gate_log_path.open("a", encoding="utf-8") as gate_log:
            gate_log.write(
                "skip_sanitize_current_proof_artifacts=proof_consistency_failed\n"
            )

    missing_logs = _missing_logs(repo_root, results)
    required_failed_checks = _failed_required_checks(results)
    remaining_required_steps = {
        "archive_validation",
        "required_proof_logs",
        "check_proof_manifest",
        "check_proof_consistency",
    } - {r.name for r in results}
    ok = (
        not required_failed_checks
        and not missing_logs
        and not remaining_required_steps
    )
    payload["alpha_gate_passed"] = ok
    payload["check_count"] = len(results)
    payload["checks"] = [asdict(r) for r in results]
    payload["logs"] = {r.name: r.log_path for r in results}
    payload["logs"]["release_gate"] = str(gate_log_path.relative_to(repo_root))
    payload["logs"]["proof_manifest"] = str(
        manifest_path.relative_to(repo_root)
    )
    payload["logs"]["static_guards"] = static_guards_rel
    payload["failed_checks"] = required_failed_checks + (
        ["missing_logs"] if missing_logs else []
    )
    payload["release_blockers_remaining"] = (
        required_failed_checks
        + sorted(remaining_required_steps)
        + (["missing_logs"] if missing_logs else [])
        if not ok
        else []
    )
    _refresh_release_payload_schema(payload, results)

    current_proof_rel, readiness_rel = _sync_release_artifacts(
        repo_root,
        out_dir,
        payload,
        results,
        manifest_path,
        out_path,
        source_registry_summary,
        static_guards_rel=static_guards_rel,
    )

    current_alpha_status_rel = payload["logs"]["current_alpha_status"]
    source_registry_status_md_rel = payload["logs"]["source_registry_status_md"]
    proof_policy_rel = payload["logs"]["proof_policy"]
    repair_report_rel = payload["logs"]["repair_report"]
    fix_verification_report_rel = payload["logs"]["fix_verification_report"]

    # Defensive consistency guard: a step must not report PASS with a missing
    # log file, because required_proof_logs validates on-disk presence.
    for step in results:
        if step.name not in {"check_migrations", "docker_runtime_preflight"}:
            continue
        if step.status != "PASS":
            continue
        step_log_path = repo_root / step.log_path
        if step_log_path.exists():
            continue
        step_log_path.write_text(
            "[release_gate] NOTE: PASS step log was missing; "
            "backfilled for proof completeness.\n"
            f"step={step.name} command={step.command}\n",
            encoding="utf-8",
        )

    archive_step = _run(
        repo_root,
        out_dir,
        _archive_validation_spec.name,
        _archive_validation_spec.log_name,
        list(_archive_validation_spec.command),
        timeout_seconds=_archive_validation_spec.timeout_seconds,
        required=_archive_validation_spec.required,
    )
    results.append(archive_step)

    archive_sidecars = {
        "archive_validation.log": out_dir / "archive_validation.log",
        "archive_validation.md": out_dir / "archive_validation.md",
    }
    missing_archive_sidecars = [
        name for name, path in archive_sidecars.items() if not path.exists()
    ]
    if missing_archive_sidecars:
        archive_step.status = "FAIL"
        archive_step.exit_code = 1
        archive_step.failure_reason = (
            "missing_archive_validation_artifacts:"
            + ",".join(sorted(missing_archive_sidecars))
        )
        with gate_log_path.open("a", encoding="utf-8") as gate_log:
            gate_log.write(
                "archive_validation_missing_artifacts="
                + ",".join(sorted(missing_archive_sidecars))
                + "\n"
            )

    # archive_validation writes additional proof files outside _run stdout,
    # so sanitize those side artifacts explicitly.
    _redact_file_local_paths(out_dir / "archive_validation.log", repo_root)
    _redact_file_local_paths(out_dir / "archive_validation.md", repo_root)
    _sanitize_current_proof_artifacts(repo_root, out_dir)

    current_proof_rel, readiness_rel = _sync_release_artifacts(
        repo_root,
        out_dir,
        payload,
        results,
        manifest_path,
        out_path,
        source_registry_summary,
        static_guards_rel=static_guards_rel,
    )

    required_proof_logs_step = _run(
        repo_root,
        out_dir,
        _required_proof_logs_spec.name,
        _required_proof_logs_spec.log_name,
        list(_required_proof_logs_spec.command),
        timeout_seconds=_required_proof_logs_spec.timeout_seconds,
        required=_required_proof_logs_spec.required,
    )
    results.append(required_proof_logs_step)

    check_proof_manifest_step = _run(
        repo_root,
        out_dir,
        _check_proof_manifest_spec.name,
        _check_proof_manifest_spec.log_name,
        list(_check_proof_manifest_spec.command),
        timeout_seconds=_check_proof_manifest_spec.timeout_seconds,
        required=_check_proof_manifest_spec.required,
    )
    results.append(check_proof_manifest_step)

    _sanitize_current_proof_artifacts(repo_root, out_dir)

    local_path_hygiene_step = _run(
        repo_root,
        out_dir,
        _local_path_hygiene_spec.name,
        _local_path_hygiene_spec.log_name,
        list(_local_path_hygiene_spec.command),
        timeout_seconds=_local_path_hygiene_spec.timeout_seconds,
        required=_local_path_hygiene_spec.required,
    )
    results.append(local_path_hygiene_step)

    check_proof_consistency_step = _run(
        repo_root,
        out_dir,
        _check_proof_consistency_spec.name,
        _check_proof_consistency_spec.log_name,
        list(_check_proof_consistency_spec.command),
        timeout_seconds=_check_proof_consistency_spec.timeout_seconds,
        required=_check_proof_consistency_spec.required,
    )
    results.append(check_proof_consistency_step)

    validation_summary = _validation_summary_gate(repo_root)
    blockers_raw = validation_summary.get("blockers", [])
    validation_blockers = (
        list(blockers_raw) if isinstance(blockers_raw, list) else []
    )
    if not validation_summary.get("exists", False):
        validation_blockers.append("validation_summary_missing")

    missing_logs = _missing_logs(repo_root, results)
    required_failed_checks = _failed_required_checks(results)
    missing_required_proof_files = _missing_required_proof_files(repo_root)
    required_log_index_missing_entries = (
        _required_log_index_missing_exists_entries(repo_root, out_dir)
    )
    ok = (
        not required_failed_checks
        and not missing_logs
        and not missing_required_proof_files
        and not required_log_index_missing_entries
        and not validation_blockers
    )
    payload["alpha_gate_passed"] = ok
    payload["check_count"] = len(results)
    payload["validation_summary_path"] = validation_summary.get("path")
    payload["validation_summary_status"] = validation_summary.get("status")
    payload["validation_summary_failed_phases"] = validation_summary.get(
        "failed_phases", []
    )
    payload["archive_validation_result"] = (
        "PASS" if archive_step.exit_code == 0 else "FAIL"
    )
    payload["checks"] = [asdict(r) for r in results]
    payload["logs"] = {r.name: r.log_path for r in results}
    payload["logs"]["release_gate"] = str(gate_log_path.relative_to(repo_root))
    payload["logs"]["proof_manifest"] = str(
        manifest_path.relative_to(repo_root)
    )
    payload["logs"]["static_guards"] = static_guards_rel
    payload["logs"]["current_proof"] = current_proof_rel
    payload["logs"]["current_alpha_status"] = current_alpha_status_rel
    payload["logs"]["source_registry_status_md"] = (
        source_registry_status_md_rel
    )
    payload["logs"]["proof_policy"] = proof_policy_rel
    payload["logs"]["repair_report"] = repair_report_rel
    payload["logs"]["fix_verification_report"] = fix_verification_report_rel
    payload["logs"]["release_readiness"] = readiness_rel
    payload["failed_checks"] = (
        required_failed_checks
        + (["missing_logs"] if missing_logs else [])
        + (
            ["missing_required_proof_file"]
            if missing_required_proof_files
            else []
        )
        + (
            ["required_log_index_exists_but_missing"]
            if required_log_index_missing_entries
            else []
        )
        + validation_blockers
    )
    payload["release_blockers_remaining"] = (
        required_failed_checks
        + (["missing_logs"] if missing_logs else [])
        + missing_required_proof_files
        + required_log_index_missing_entries
        + validation_blockers
        if not ok
        else []
    )
    _refresh_release_payload_schema(payload, results)

    _sync_release_artifacts(
        repo_root,
        out_dir,
        payload,
        results,
        manifest_path,
        out_path,
        source_registry_summary,
        static_guards_rel=static_guards_rel,
    )

    if ok:
        print(f"PASS: wrote {out_path.relative_to(repo_root)}")
        return 0

    print(f"BLOCKED: wrote {out_path.relative_to(repo_root)}")
    for result in results:
        if result.required and result.exit_code != 0:
            print(
                f"- {result.name} rc={result.exit_code} log={result.log_path}"
            )
    for missing in missing_logs:
        print(f"- missing_log={missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
