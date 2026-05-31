#!/usr/bin/env python3
"""Verify that every log_path referenced in release_gate.json exists on disk.

This script reads ``artifacts/proof/current/release_gate.json`` and checks
that every log file recorded in ``checks[*].log_path`` is present on the
filesystem.  It exits 1 with a clear list of missing paths so the gate
cannot be marked PASS while evidence is absent.

Usage::

    python3 scripts/check_required_proof_logs.py
    python3 scripts/check_required_proof_logs.py --root /path/to/repo
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIRED_PROOF_FILES = (
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
DEFAULT_REQUIRED_PROOF_LOGS = (
    "artifacts/proof/current/release_gate.log",
    "artifacts/proof/current/runtime_smoke.log",
    "artifacts/proof/current/docker_smoke.log",
    "artifacts/proof/current/check_proof_manifest.log",
    "artifacts/proof/current/check_proof_consistency.log",
    "artifacts/proof/current/check_no_local_paths_in_release_proof.log",
    "artifacts/proof/current/backend_pytest.log",
    "artifacts/proof/current/backend_pytest_collect.log",
    "artifacts/proof/current/backend_compile.log",
    "artifacts/proof/current/backend_import.log",
    "artifacts/proof/current/frontend_install.log",
    "artifacts/proof/current/frontend_lint.log",
    "artifacts/proof/current/frontend_typecheck.log",
    "artifacts/proof/current/frontend_contracts.log",
    "artifacts/proof/current/frontend_build.log",
    "artifacts/proof/current/frontend_node_gate.log",
    "artifacts/proof/current/check_api_contracts.log",
    "artifacts/proof/current/public_api_boundary.log",
    "artifacts/proof/current/mutation_fail_closed_coverage.log",
    "artifacts/proof/current/docker_runtime_preflight.log",
    "artifacts/proof/current/postgis_proof.log",
    "artifacts/proof/current/egress_proxy_proof.log",
    "artifacts/proof/current/demo_proof.log",
    "artifacts/proof/current/verify_evidence_store.log",
    "artifacts/proof/current/verify_source_registry.log",
    "artifacts/proof/current/check_false_claims.log",
    "artifacts/proof/current/check_no_pyc.log",
    "artifacts/proof/current/repo_generated_files.log",
    "artifacts/proof/current/proof_freshness.log",
    "artifacts/proof/current/proof_consistency_pytest.log",
    "artifacts/proof/current/required_proof_logs.log",
    "artifacts/proof/current/single_proof_authority.log",
    "artifacts/proof/current/archive_validation.log",
)
PACKAGED_ARCHIVE_OPTIONAL_REQUIRED_LOGS = {
    "artifacts/proof/current/archive_validation.log",
    "artifacts/proof/current/required_proof_logs.log",
}
PROOF_INCOMPLETE_PREFIX = "PROOF_INCOMPLETE:"


def _parse_iso8601_to_epoch(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _check_required_proof_logs_detailed(
    repo_root: Path,
    *,
    packaged_archive: bool = False,
) -> tuple[list[str], list[str], list[str], int, int]:
    """Return missing log paths plus referenced/present totals.

    Reads ``artifacts/proof/current/release_gate.json`` and inspects every
    entry in the ``checks`` array for a ``log_path`` field.  Also checks the
    top-level ``logs`` map as a secondary source.

    Args:
        repo_root: Repository root directory.

    Returns:
        Tuple of ``(missing_paths, referenced_total, present_total)``.
    """
    gate_json = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    if not gate_json.exists():
        print(f"ERROR: release_gate.json not found at {gate_json}", file=sys.stderr)
        missing_paths = [str(gate_json.relative_to(repo_root))]
        return missing_paths, [], [], len(missing_paths), 0

    try:
        payload = json.loads(gate_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: failed to parse release_gate.json: {exc}", file=sys.stderr)
        return ["release_gate.json:parse_error"], [], [], 1, 0

    missing: list[str] = []
    empty_logs: list[str] = []
    stale_logs: list[str] = []
    seen: set[str] = set()
    manifest_missing: list[str] = []
    hash_mismatches: list[str] = []
    size_mismatches: list[str] = []

    manifest_path = repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    manifest: dict | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = None
    proof_entry_map = _proof_entry_map(manifest or {}) if manifest else {}
    started_at_by_log: dict[str, float] = {}
    checks = payload.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            rel = check.get("log_path")
            if not isinstance(rel, str) or not rel:
                continue
            started_epoch = _parse_iso8601_to_epoch(check.get("started_at_utc"))
            if started_epoch is not None:
                started_at_by_log[rel] = started_epoch

    # Primary source: checks array (each entry has a log_path field)
    for entry in payload.get("checks", []):
        log_path = entry.get("log_path")
        if not log_path or not isinstance(log_path, str):
            continue
        if log_path in seen:
            continue
        seen.add(log_path)
        abs_path = repo_root / log_path
        if not abs_path.exists():
            missing.append(log_path)
            continue
        if abs_path.stat().st_size <= 0:
            empty_logs.append(log_path)
            continue
        if not packaged_archive:
            started_epoch = started_at_by_log.get(log_path)
            if started_epoch is not None and abs_path.stat().st_mtime + 1.0 < started_epoch:
                stale_logs.append(log_path)
                continue
        entry = proof_entry_map.get(log_path)
        if entry is None:
            manifest_missing.append(log_path)
            continue
        expected_size = entry.get("size_bytes")
        if isinstance(expected_size, int) and expected_size != abs_path.stat().st_size:
            size_mismatches.append(log_path)
        expected_hash = entry.get("sha256") or entry.get("log_sha256")
        if isinstance(expected_hash, str) and expected_hash:
            actual_hash = _sha256_path(abs_path)
            if actual_hash != expected_hash:
                hash_mismatches.append(log_path)

    # Secondary source: top-level logs map
    for _check_name, log_path in payload.get("logs", {}).items():
        if not log_path or not isinstance(log_path, str):
            continue
        if not log_path.endswith(".log"):
            continue
        if log_path in seen:
            continue
        # Only enforce logs inside artifacts/proof/current/ — other paths
        # (docs, root files) are non-log artifacts and may vary per run.
        if not log_path.startswith("artifacts/proof/current/"):
            continue
        seen.add(log_path)
        abs_path = repo_root / log_path
        if not abs_path.exists():
            missing.append(log_path)
            continue
        if abs_path.stat().st_size <= 0:
            empty_logs.append(log_path)
            continue
        if not packaged_archive:
            started_epoch = started_at_by_log.get(log_path)
            if started_epoch is not None and abs_path.stat().st_mtime + 1.0 < started_epoch:
                stale_logs.append(log_path)
                continue
        entry = proof_entry_map.get(log_path)
        if entry is None:
            manifest_missing.append(log_path)
            continue
        expected_size = entry.get("size_bytes")
        if isinstance(expected_size, int) and expected_size != abs_path.stat().st_size:
            size_mismatches.append(log_path)
        expected_hash = entry.get("sha256") or entry.get("log_sha256")
        if isinstance(expected_hash, str) and expected_hash:
            actual_hash = _sha256_path(abs_path)
            if actual_hash != expected_hash:
                hash_mismatches.append(log_path)

    if manifest_missing or hash_mismatches or size_mismatches:
        missing.extend(manifest_missing)
        missing.extend(size_mismatches)
        missing.extend(hash_mismatches)

    referenced_total = len(seen)
    missing_unique = sorted(set(missing))
    present_total = max(referenced_total - len(missing_unique), 0)
    return (
        missing_unique,
        sorted(set(empty_logs)),
        sorted(set(stale_logs)),
        referenced_total,
        present_total,
    )


def check_required_proof_logs(
    repo_root: Path,
    *,
    packaged_archive: bool = False,
) -> tuple[list[str], int, int]:
    """Backward-compatible wrapper returning missing/referenced/present totals."""
    result = _check_required_proof_logs_detailed(
        repo_root,
        packaged_archive=packaged_archive,
    )
    missing, _empty_logs, _stale_logs, referenced_total, present_total = result
    false_exists_required_index = _required_log_index_false_exists(repo_root)
    # When there are no referenced logs at all, the proof is incomplete:
    # return all known required logs as missing.
    if referenced_total == 0:
        missing = list(DEFAULT_REQUIRED_PROOF_LOGS)
    # Add any entries from required_log_index.json that falsely claim to exist.
    missing.extend(false_exists_required_index)
    return missing, referenced_total, present_total


def _missing_required_proof_files(repo_root: Path) -> list[str]:
    missing: list[str] = []
    for rel_path in DEFAULT_REQUIRED_PROOF_FILES:
        if not (repo_root / rel_path).exists():
            missing.append(rel_path)
    return sorted(missing)


def _missing_required_proof_logs(
    repo_root: Path, *, packaged_archive: bool = False
) -> list[str]:
    missing: list[str] = []
    for rel_path in DEFAULT_REQUIRED_PROOF_LOGS:
        if packaged_archive and rel_path in PACKAGED_ARCHIVE_OPTIONAL_REQUIRED_LOGS:
            continue
        if not (repo_root / rel_path).exists():
            missing.append(rel_path)
    return sorted(missing)


def _required_log_index_false_exists(repo_root: Path) -> list[str]:
    index_path = repo_root / "artifacts/proof/current/required_log_index.json"
    if not index_path.exists():
        return ["artifacts/proof/current/required_log_index.json"]
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["artifacts/proof/current/required_log_index.json:invalid_json"]
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return ["artifacts/proof/current/required_log_index.json:invalid_entries"]
    bad: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel:
            continue
        if entry.get("exists") is True and not (repo_root / rel).is_file():
            bad.append(rel)
    return sorted(set(bad))


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_path(entry: dict) -> str | None:
    path = entry.get("path")
    if isinstance(path, str) and path:
        return path
    log_path = entry.get("log_path")
    if isinstance(log_path, str) and log_path:
        return log_path
    return None


def _proof_entry_map(manifest: dict) -> dict[str, dict]:
    entry_map: dict[str, dict] = {}
    proof_commands = manifest.get("proof_commands")
    if not isinstance(proof_commands, list):
        return entry_map
    for entry in proof_commands:
        if not isinstance(entry, dict):
            continue
        entry_path = _entry_path(entry)
        if entry_path:
            entry_map[entry_path] = entry
    return entry_map


def _format_proof_incomplete_message(
    *,
    missing_logs: list[str],
    empty_logs: list[str],
    stale_logs: list[str],
    missing_required_logs: list[str],
    missing_required_files: list[str],
    false_exists_required_index: list[str] | None = None,
) -> str:
    parts: list[str] = []
    if missing_logs:
        parts.append("missing_referenced_logs=" + ",".join(missing_logs))
    if empty_logs:
        parts.append("empty_referenced_logs=" + ",".join(empty_logs))
    if stale_logs:
        parts.append("stale_referenced_logs=" + ",".join(stale_logs))
    if missing_required_logs:
        parts.append(
            "missing_required_proof_logs=" + ",".join(missing_required_logs)
        )
    if missing_required_files:
        parts.append(
            "missing_required_proof_files=" + ",".join(missing_required_files)
        )
    if false_exists_required_index:
        parts.append(
            "required_log_index_false_exists=" + ",".join(false_exists_required_index)
        )
    return PROOF_INCOMPLETE_PREFIX + "|".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root")
    parser.add_argument(
        "--strict-required-files",
        action="store_true",
        help=(
            "Also fail if canonical proof files required by archive packaging are missing"
        ),
    )
    parser.add_argument(
        "--packaged-archive",
        action="store_true",
        help=(
            "Validate a packaged archive/extracted tree where self-referential archive"
            " validation logs are intentionally omitted"
        ),
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    (
        missing,
        empty_logs,
        stale_logs,
        referenced_total,
        present_total,
    ) = _check_required_proof_logs_detailed(
        repo_root,
        packaged_archive=args.packaged_archive,
    )

    # Hard failure: no referenced logs means proof is incomplete
    if referenced_total == 0:
        print("REQUIRED_PROOF_LOGS: FAIL (0 referenced logs)", file=sys.stderr)
        print(
            "PROOF_INCOMPLETE:no referenced proof logs were found in release_gate.json",
            file=sys.stderr,
        )
        return 1

    missing_required_files: list[str] = []
    missing_required_logs: list[str] = []
    false_exists_required_index: list[str] = []
    if args.strict_required_files:
        missing_required_files = _missing_required_proof_files(repo_root)
        missing_required_logs = _missing_required_proof_logs(
            repo_root,
            packaged_archive=args.packaged_archive,
        )
        false_exists_required_index = _required_log_index_false_exists(repo_root)

    if (
        missing
        or empty_logs
        or stale_logs
        or missing_required_logs
        or missing_required_files
        or false_exists_required_index
    ):
        print(
            "REQUIRED_PROOF_LOGS: FAIL "
            f"({len(missing)} missing of {referenced_total} referenced)"
        )
        print(
            _format_proof_incomplete_message(
                missing_logs=missing,
                empty_logs=empty_logs,
                stale_logs=stale_logs,
                missing_required_logs=missing_required_logs,
                missing_required_files=missing_required_files,
                false_exists_required_index=false_exists_required_index,
            )
        )
        print(
            "REQUIRED_PROOF_LOGS: DEBUG "
            "present="
            f"{present_total} missing={len(missing)} referenced={referenced_total}"
        )
        if referenced_total > 0:
            percentage = (present_total / referenced_total) * 100.0
            print(f"REQUIRED_PROOF_LOGS: DEBUG present_ratio={percentage:.1f}%")
        for path in missing:
            abs_path = repo_root / path
            if abs_path.exists():
                size = abs_path.stat().st_size
                print(f"  MISSING: {path} (exists_on_disk size={size} bytes)")
            else:
                print(f"  MISSING: {path}")

        if empty_logs:
            print(
                "REQUIRED_PROOF_LOGS: DEBUG "
                f"empty_logs={len(empty_logs)}"
            )
            for path in empty_logs:
                print(f"  EMPTY_LOG: {path}")

        if stale_logs:
            print(
                "REQUIRED_PROOF_LOGS: DEBUG "
                f"stale_logs={len(stale_logs)}"
            )
            for path in stale_logs:
                print(f"  STALE_LOG: {path}")

        if missing_required_files:
            print(
                "REQUIRED_PROOF_LOGS: DEBUG "
                f"missing_required_files={len(missing_required_files)}"
            )
            for path in missing_required_files:
                print(f"  MISSING_REQUIRED_FILE: {path}")
        if missing_required_logs:
            print(
                "REQUIRED_PROOF_LOGS: DEBUG "
                f"missing_required_logs={len(missing_required_logs)}"
            )
            for path in missing_required_logs:
                print(f"  MISSING_REQUIRED_LOG: {path}")
        if false_exists_required_index:
            print(
                "REQUIRED_PROOF_LOGS: DEBUG "
                f"required_log_index_false_exists={len(false_exists_required_index)}"
            )
            for path in false_exists_required_index:
                print(f"  REQUIRED_INDEX_FALSE_EXISTS: {path}")
        return 1

    print(
        "REQUIRED_PROOF_LOGS: PASS "
        f"({present_total} referenced logs present)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
