#!/usr/bin/env python3
"""Verify proof freshness using a deterministic proof-input manifest.

Default validation reads the stored manifest from
``artifacts/proof/current/release_gate.json`` and verifies:
1) listed files are present,
2) listed-file hash matches stored hash,
3) newly discovered proof-relevant files are reported.

On mismatches, this checker reports per-file diagnostics when stored
fingerprints are available, plus added/removed file-path deltas.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

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
    "docs/security/FRONTEND_SECURITY_TRIAGE.md",
    "docs/security/frontend_dependency_exceptions.md",
    "docs/schema_audit.md",
    "docs/security/LEGACY_AUTH_REMOVAL_PLAN.md",
    "docs/deployment-guide/DEPENDENCY_REMEDIATION_PLAN.md",
    "docs/REPAIR_PROOF.md",
    "docs/REPAIR_BASELINE.md",
    "docs/SECURITY.md",
    "docs/PROOF.md",
    "docs/SOURCES.md",
    "docs/AI_PIPELINE.md",
    "artifacts/proof/CURRENT_PROOF.md",
]

IGNORE_PATH_PREFIXES = {
    ".git/",
    ".venv/",
    "backend/.venv/",
    "frontend/node_modules/",
    "node_modules/",
    "artifacts/proof/current/",
    "artifacts/proof/history/",
    "scripts/.pytest_cache/",
}

IGNORE_GLOB_PATTERNS = {
    "artifacts/proof/v*/**",
    "artifacts/proof/**/*.log",
    "**/dist/**",
    "**/build/**",
    "**/*.tsbuildinfo",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.log",
    "**/*.tmp",
    "**/*.pid",
    # Database and SQLite volatile files
    "**/*.db",
    "**/*.db-shm",
    "**/*.db-wal",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*.sqlite-shm",
    "**/*.sqlite-wal",
    "demo/**/*.db",
    "demo/**/*.sqlite",
    "demo/**/*.sqlite3",
    "demo/demo.sqlite3",
    "backend/app/tests/*.db",
    "backend/app/tests/*.sqlite",
    "backend/app/tests/*.sqlite3",
    "**/.env",
    "**/.env.*",
    "**/.DS_Store",
}


def _normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_ignored(rel_path: str) -> bool:
    norm = _normalize_rel_path(rel_path)
    if any(norm.startswith(prefix) for prefix in IGNORE_PATH_PREFIXES):
        return True
    if "/.next/" in f"/{norm}" or norm.startswith(".next/"):
        return True
    if norm.startswith("artifacts/proof/v"):
        return True
    # Use fnmatch for proper glob-style pattern matching
    if any(fnmatch.fnmatch(norm, pattern) for pattern in IGNORE_GLOB_PATTERNS):
        return True
    return False


def _load_truth_claim_scanned_paths(repo_root: Path) -> list[str]:
    """Load truth-sensitive docs selected by the false-claim scanner module."""
    module_path = repo_root / "scripts" / "check_truth_claims.py"
    if not module_path.is_file():
        return []

    spec = importlib.util.spec_from_file_location("check_truth_claims_module", str(module_path))
    if spec is None or spec.loader is None:
        return []
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    get_truth_sensitive_paths = getattr(module, "get_truth_sensitive_paths", None)
    if get_truth_sensitive_paths is None:
        return []

    scanned: list[str] = []
    for path in get_truth_sensitive_paths(repo_root):
        if not isinstance(path, Path) or not path.is_file():
            continue
        rel = _normalize_rel_path(str(path.relative_to(repo_root)))
        if _is_ignored(rel):
            continue
        scanned.append(rel)
    return sorted(set(scanned))


def discover_proof_input_files(repo_root: Path) -> list[str]:
    files: set[str] = set()
    for pattern in PROOF_INPUT_PATTERNS:
        for candidate in repo_root.glob(pattern):
            if not candidate.is_file():
                continue
            rel = _normalize_rel_path(str(candidate.relative_to(repo_root)))
            if _is_ignored(rel):
                continue
            files.add(rel)

    # Keep proof freshness aligned with the same text files checked for truth claims.
    for rel in _load_truth_claim_scanned_paths(repo_root):
        if not _is_ignored(rel):
            files.add(rel)
    return sorted(files)


def _hash_files_with_fingerprints(
    repo_root: Path,
    rel_files: list[str],
) -> tuple[str, list[str], dict[str, dict[str, int | str]]]:
    hasher = hashlib.sha256()
    missing: list[str] = []
    fingerprints: dict[str, dict[str, int | str]] = {}
    for rel in rel_files:
        file_path = repo_root / rel
        if not file_path.is_file():
            missing.append(rel)
            continue
        size_bytes = file_path.stat().st_size
        file_hasher = hashlib.sha256()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\n")
        hasher.update(str(size_bytes).encode("utf-8"))
        hasher.update(b"\n")
        with file_path.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                file_hasher.update(chunk)
        hasher.update(b"\n")
        fingerprints[rel] = {
            "size_bytes": size_bytes,
            "sha256": file_hasher.hexdigest(),
        }
    return hasher.hexdigest(), missing, fingerprints


def _hash_files(repo_root: Path, rel_files: list[str]) -> tuple[str, list[str]]:
    digest, missing, _fingerprints = _hash_files_with_fingerprints(repo_root, rel_files)
    return digest, missing


def compute_proof_input_tree_hash(repo_root: Path) -> tuple[str, list[str]]:
    rel_files = discover_proof_input_files(repo_root)
    digest, _missing = _hash_files(repo_root, rel_files)
    return digest, rel_files


def _release_gate_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "proof" / "current" / "release_gate.json"


def _current_proof_path(repo_root: Path) -> Path:
    return repo_root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md"


def _release_gate_payload(repo_root: Path) -> dict:
    release_gate_path = _release_gate_path(repo_root)
    if not release_gate_path.exists():
        raise FileNotFoundError(str(release_gate_path.relative_to(repo_root)))
    return json.loads(release_gate_path.read_text(encoding="utf-8"))


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


def _check_referenced_logs_fresh(repo_root: Path, payload: dict) -> tuple[list[str], list[str]]:
    stale_logs: list[str] = []
    empty_logs: list[str] = []

    checks = payload.get("checks", [])
    if not isinstance(checks, list):
        return stale_logs, empty_logs

    for entry in checks:
        if not isinstance(entry, dict):
            continue
        log_path = entry.get("log_path")
        if not isinstance(log_path, str) or not log_path:
            continue
        if not log_path.startswith("artifacts/proof/current/"):
            continue

        abs_path = repo_root / log_path
        if not abs_path.is_file():
            continue
        size = abs_path.stat().st_size
        if size <= 0:
            empty_logs.append(log_path)
            continue

        started_epoch = _parse_iso8601_to_epoch(entry.get("started_at_utc"))
        if started_epoch is None:
            continue
        if abs_path.stat().st_mtime + 1.0 < started_epoch:
            stale_logs.append(log_path)

    return sorted(set(stale_logs)), sorted(set(empty_logs))


def validate_stored_manifest(
    repo_root: Path,
    strict_extra_files: bool = False,
) -> dict:
    payload = _release_gate_payload(repo_root)
    expected_hash = payload.get("proof_input_tree_hash")
    algorithm = payload.get("proof_input_tree_hash_algorithm")
    if "proof_input_file_list" not in payload:
        return {
            "status": "FAIL",
            "expected_hash": expected_hash,
            "actual_hash": None,
            "proof_input_tree_hash_algorithm": algorithm,
            "file_count": 0,
            "missing_files": [],
            "extra_files": [],
            "stored_file_count": 0,
            "discovered_file_count": len(discover_proof_input_files(repo_root)),
            "stored_file_list": [],
            "discovered_file_list": discover_proof_input_files(repo_root),
            "message": "release_gate.json missing/invalid proof_input_file_list",
        }

    stored_file_list = payload.get("proof_input_file_list")
    stored_fingerprints = payload.get("proof_input_file_fingerprints")
    discovered_file_list = discover_proof_input_files(repo_root)
    extra_files = sorted(set(discovered_file_list) - set(stored_file_list))

    result = {
        "status": "PASS",
        "expected_hash": expected_hash,
        "actual_hash": None,
        "proof_input_tree_hash_algorithm": algorithm,
        "file_count": len(stored_file_list),
        "missing_files": [],
        "removed_files": [],
        "extra_files": extra_files,
        "added_files": extra_files,
        "stored_file_count": len(stored_file_list),
        "discovered_file_count": len(discovered_file_list),
        "stored_file_list": stored_file_list,
        "discovered_file_list": discovered_file_list,
        "changed_files": [],
        "changed_file_count": 0,
        "stale_logs": [],
        "empty_logs": [],
        "message": "proof artifacts are fresh",
    }

    if not expected_hash:
        result["status"] = "FAIL"
        result["message"] = "release_gate.json missing proof_input_tree_hash"
        return result

    if algorithm != "sha256":
        result["status"] = "FAIL"
        result["message"] = (
            "release_gate.json missing/invalid proof_input_tree_hash_algorithm"
        )
        return result

    if not isinstance(stored_file_list, list) or not all(
        isinstance(path, str) for path in stored_file_list
    ):
        result["status"] = "FAIL"
        result["message"] = "release_gate.json missing/invalid proof_input_file_list"
        return result

    actual_hash, missing_files, runtime_fingerprints = _hash_files_with_fingerprints(
        repo_root,
        sorted(stored_file_list),
    )
    result["actual_hash"] = actual_hash
    result["missing_files"] = missing_files
    result["removed_files"] = missing_files

    if missing_files:
        result["status"] = "FAIL"
        result["message"] = (
            "missing listed proof input files: "
            + ", ".join(missing_files)
        )
        return result

    if actual_hash != expected_hash:
        changed_files: list[str] = []
        if isinstance(stored_fingerprints, dict):
            for rel in sorted(stored_file_list):
                if rel in missing_files:
                    continue
                expected_fp = stored_fingerprints.get(rel)
                runtime_fp = runtime_fingerprints.get(rel)
                if not isinstance(expected_fp, dict) or not isinstance(runtime_fp, dict):
                    continue
                if (
                    expected_fp.get("size_bytes") != runtime_fp.get("size_bytes")
                    or expected_fp.get("sha256") != runtime_fp.get("sha256")
                ):
                    changed_files.append(rel)
        result["changed_files"] = changed_files
        result["changed_file_count"] = len(changed_files)
        result["status"] = "FAIL"
        mismatch_msg = (
            "proof input tree hash mismatch: "
            f"expected={expected_hash} actual={actual_hash}"
        )
        if changed_files:
            mismatch_msg += (
                "; changed_files_detected="
                + ", ".join(changed_files[:10])
                + (" ..." if len(changed_files) > 10 else "")
            )
        result["message"] = mismatch_msg
        return result

    if extra_files and strict_extra_files:
        result["status"] = "FAIL"
        result["message"] = (
            "new proof-relevant files outside stored list: "
            + ", ".join(extra_files)
        )
        return result

    if extra_files:
        result["message"] = (
            "proof artifacts are fresh, but new proof-relevant files were discovered"
        )

    stale_logs, empty_logs = _check_referenced_logs_fresh(repo_root, payload)
    if stale_logs or empty_logs:
        result["status"] = "FAIL"
        result["stale_logs"] = stale_logs
        result["empty_logs"] = empty_logs
        parts: list[str] = []
        if stale_logs:
            parts.append("stale_referenced_logs=" + ",".join(stale_logs))
        if empty_logs:
            parts.append("empty_referenced_logs=" + ",".join(empty_logs))
        result["message"] = "proof log freshness failed: " + "|".join(parts)

    return result


def check_against_expected(repo_root: Path, expected_hash: str) -> dict:
    actual_hash, rel_files = compute_proof_input_tree_hash(repo_root)
    result = {
        "status": "PASS",
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "proof_input_tree_hash_algorithm": "sha256",
        "file_count": len(rel_files),
        "missing_files": [],
        "extra_files": [],
        "stored_file_count": len(rel_files),
        "discovered_file_count": len(rel_files),
        "stored_file_list": rel_files,
        "discovered_file_list": rel_files,
        "message": "proof input tree hash matches expected value",
    }
    if actual_hash != expected_hash:
        result["status"] = "FAIL"
        result["message"] = (
            f"proof input tree hash mismatch: expected={expected_hash} actual={actual_hash}"
        )
    return result


def metadata_payload(repo_root: Path) -> dict:
    rel_files = discover_proof_input_files(repo_root)
    digest, _missing, fingerprints = _hash_files_with_fingerprints(repo_root, rel_files)
    return {
        "status": "OK",
        "proof_input_tree_hash": digest,
        "proof_input_tree_hash_algorithm": "sha256",
        "proof_input_paths": PROOF_INPUT_PATTERNS,
        "proof_input_file_count": len(rel_files),
        "proof_input_file_list": rel_files,
        "proof_input_file_fingerprints": fingerprints,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--expected-hash",
        help="If provided, compare the computed proof-input hash against this value",
    )
    parser.add_argument(
        "--strict-extra-files",
        action="store_true",
        help="Fail if newly discovered proof-relevant files are outside the stored list",
    )
    parser.add_argument(
        "--print-inputs",
        action="store_true",
        help="Print discovered and stored proof-input file lists",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable validation output",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Emit deterministic proof-input metadata without reading release_gate.json",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    if not repo_root.is_dir():
        print(f"ERROR: root is not a directory: {repo_root}")
        return 2

    if args.metadata_only:
        print(json.dumps(metadata_payload(repo_root), indent=2))
        return 0

    if args.expected_hash:
        result = check_against_expected(repo_root, args.expected_hash)
    else:
        try:
            result = validate_stored_manifest(
                repo_root,
                strict_extra_files=args.strict_extra_files,
            )
        except FileNotFoundError as exc:
            result = {
                "status": "FAIL",
                "expected_hash": None,
                "actual_hash": None,
                "proof_input_tree_hash_algorithm": "sha256",
                "file_count": 0,
                "missing_files": [str(exc)],
                "extra_files": [],
                "stored_file_count": 0,
                "discovered_file_count": len(discover_proof_input_files(repo_root)),
                "stored_file_list": [],
                "discovered_file_list": discover_proof_input_files(repo_root),
                "message": f"missing {exc}",
            }

    if args.print_inputs:
        print("=== discovered proof inputs ===")
        for rel in result["discovered_file_list"]:
            print(rel)
        print("=== stored proof inputs ===")
        for rel in result["stored_file_list"]:
            print(rel)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1

    if result["status"] == "PASS":
        print(f"PASS: {result['message']}")
        print(f"proof_input_tree_hash={result['actual_hash']}")
        if result["extra_files"] and not args.strict_extra_files:
            print(
                "WARN: discovered proof-relevant files outside stored list: "
                + ", ".join(result["extra_files"])
            )
        return 0

    print(f"FAIL: {result['message']}")
    if result["actual_hash"]:
        print(f"proof_input_tree_hash={result['actual_hash']}")
    if result.get("changed_files"):
        print("changed_files=" + ",".join(result["changed_files"]))
    if result.get("removed_files"):
        print("removed_files=" + ",".join(result["removed_files"]))
    if result.get("added_files"):
        print("added_files=" + ",".join(result["added_files"]))
    if result.get("stale_logs"):
        print("stale_referenced_logs=" + ",".join(result["stale_logs"]))
    if result.get("empty_logs"):
        print("empty_referenced_logs=" + ",".join(result["empty_logs"]))
    if result["extra_files"]:
        print("extra_discovered_files=" + ",".join(result["extra_files"]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
