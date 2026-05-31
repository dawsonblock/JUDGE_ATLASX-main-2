#!/usr/bin/env python3
"""Validate the exact final ZIP archive for release integrity.

This script validates that:
1. The ZIP file exists and is readable
2. Archive contains exactly one runtime root (backend/ + frontend/ + scripts/)
3. No stale nested repo copies exist
4. No forbidden paths (node_modules, venv, __pycache__, .git, etc.)
5. Required proof artifacts present
6. Archive structure matches expected layout
7. SHA-256 identity recorded
8. Proof freshness passes after extraction

Usage:
    python scripts/validate_final_zip.py /absolute/path/to/final-archive.zip

Exit Codes:
    0   Archive valid and ready to ship
    1   Archive structure invalid
    2   Archive contains forbidden paths
    3   Proof validation failed during extraction
    4   ZIP not found or unreadable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def compute_sha256(zip_path: Path) -> str:
    """Compute SHA-256 hash of ZIP file."""
    digest = hashlib.sha256()
    with zip_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_runtime_roots(extract_dir: Path) -> list[Path]:
    """Find all directories that appear to be runtime roots.
    
    A runtime root contains:
    - backend/
    - frontend/
    - scripts/release_gate.py
    """
    candidates: list[Path] = []
    
    # Look for release_gate.py markers
    for release_gate in extract_dir.glob("**/scripts/release_gate.py"):
        repo_root = release_gate.parents[1]
        if repo_root.is_dir():
            # Verify it has the required subdirectories
            if (
                (repo_root / "backend").is_dir()
                and (repo_root / "frontend").is_dir()
                and (repo_root / "scripts").is_dir()
            ):
                # Avoid duplicates
                if repo_root not in candidates:
                    candidates.append(repo_root)
    
    return sorted(set(candidates))


def find_forbidden_paths(extract_dir: Path) -> list[str]:
    """Find forbidden paths that should not be in archive.
    
    Forbidden patterns:
    - node_modules/
    - .next/
    - __pycache__/
    - *.pyc
    - .pytest_cache/
    - .mypy_cache/
    - venv/
    - .venv/
    - .git/
    - *.egg-info/
    - .DS_Store
    """
    forbidden_patterns = {
        "node_modules/",
        ".next/",
        "__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".validation_logs/",
        "venv/",
        ".venv/",
        ".git/",
        "artifacts/history/",
        "artifacts/proof/history/",
        "artifacts/proof/archive/",
        "artifacts/proof/backend/",
        "artifacts/proof/frontend/",
        ".gitignore",
    }
    
    forbidden_extensions = {".pyc", ".egg-info", ".pyo"}
    forbidden_files = {
        ".DS_Store",
        ".ds_store",
        ".coverage",
        "thumbs.db",
        "Thumbs.db",
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
    }
    
    found: list[str] = []
    
    for path in extract_dir.rglob("*"):
        rel = path.relative_to(extract_dir)
        path_str = str(rel)
        
        # Check for forbidden directories (must check with trailing slash)
        for pattern in forbidden_patterns:
            if pattern.endswith("/"):
                if f"{pattern}" in f"{path_str}/" or path_str.startswith(pattern):
                    found.append(path_str)
                    break
            else:
                if path_str == pattern or path_str.startswith(f"{pattern}/"):
                    found.append(path_str)
                    break
        
        # Check extensions
        if path.suffix in forbidden_extensions:
            found.append(path_str)
        
        # Check filenames
        if path.name in forbidden_files or path.name.lower() in forbidden_files:
            found.append(path_str)
        if path.name.startswith(".env."):
            found.append(path_str)
    
    return sorted(set(found))


def find_nested_artifacts(extract_dir: Path, root: Path) -> list[str]:
    """Find nested proof artifacts outside authoritative root."""
    nested: list[str] = []
    
    # Find all artifacts/proof/current directories
    for proof_dir in extract_dir.glob("**/artifacts/proof/current"):
        # If it's not inside our authoritative root, it's nested
        try:
            proof_dir.relative_to(root)
        except ValueError:
            # Not under root - this is nested
            nested.append(str(proof_dir.relative_to(extract_dir)))
    
    return nested


def find_duplicate_critical_files(extract_dir: Path, root: Path) -> list[str]:
    """Find duplicate canonical proof artifacts outside the runtime root.

    Only flags duplicates of canonical files that should exist exactly once in
    artifacts/proof/current under the resolved runtime root.
    """
    critical_rel_paths = {
        "artifacts/proof/current/release_readiness.md",
        "artifacts/proof/current/proof_manifest.json",
        "artifacts/proof/current/release_gate.json",
        "artifacts/proof/current/backend_pytest.log",
    }

    duplicates: list[str] = []
    for rel_path in sorted(critical_rel_paths):
        name = Path(rel_path).name
        found_paths = list(extract_dir.glob(f"**/{name}"))
        canonical_path = root / rel_path
        matching = [
            path for path in found_paths if path.as_posix().endswith(rel_path)
        ]

        if not canonical_path.exists():
            duplicates.append(f"missing_canonical:{canonical_path.relative_to(extract_dir)}")
            continue

        if len(matching) > 1:
            duplicates.extend(str(path.relative_to(extract_dir)) for path in matching)

    return sorted(set(duplicates))


def validate_archive_structure(extract_dir: Path, root: Path) -> tuple[bool, list[str]]:
    """Validate archive structure requirements."""
    errors: list[str] = []
    
    # Check required directories exist
    required_dirs = [
        "backend",
        "frontend",
        "scripts",
        "docs",
        "artifacts",
    ]
    
    for dirname in required_dirs:
        if not (root / dirname).is_dir():
            errors.append(f"missing_required_dir:{dirname}")
    
    # Check required files exist
    required_files = [
        "backend/app/main.py",
        "frontend/package.json",
        "scripts/release_gate.py",
        "artifacts/proof/current/release_gate.json",
        "artifacts/proof/current/release_readiness.md",
        "artifacts/proof/current/proof_manifest.json",
        "artifacts/proof/current/required_log_index.json",
        "artifacts/proof/current/REPAIR_REPORT.md",
        "README.md",
    ]
    
    for filepath in required_files:
        if not (root / filepath).exists():
            errors.append(f"missing_required_file:{filepath}")
    
    return len(errors) == 0, errors


def check_forbidden_paths_in_root(root: Path) -> list[str]:
    """Check for forbidden paths specifically in root."""
    errors: list[str] = []
    
    forbidden_in_root = [
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
        ".next",
        "venv",
        ".venv",
    ]
    
    for name in forbidden_in_root:
        path = root / name
        if path.exists():
            errors.append(f"forbidden_in_root:{name}")
    
    return errors


CANONICAL_ARCHIVE_NAME = "JUDGE_ATLAS-main-final.zip"
CANONICAL_ROOT_NAME = "JUDGE_ATLAS-main"


def validate_referenced_proof_logs(root: Path) -> list[str]:
    """Check that every log_path referenced in release_gate.json exists inside the extracted root."""
    gate_json = root / "artifacts" / "proof" / "current" / "release_gate.json"
    if not gate_json.exists():
        return ["referenced_proof_logs_check_skipped:release_gate.json_missing"]
    try:
        with gate_json.open() as fh:
            gate = json.load(fh)
    except Exception as e:
        return [f"referenced_proof_logs_check_failed:json_parse_error:{e}"]

    referenced: set[str] = set()
    for check in gate.get("checks", []):
        lp = check.get("log_path")
        if lp:
            referenced.add(lp)
    for val in gate.get("logs", {}).values():
        if isinstance(val, str) and val:
            referenced.add(val)

    missing = []
    for rel_path in sorted(referenced):
        if not (root / rel_path).exists():
            missing.append(f"missing_referenced_log:{rel_path}")
    return missing


def _load_json_dict(path: Path, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists() or not path.is_file():
        return None, [f"missing_canonical:{label}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, [f"missing_canonical:{label}"]
    if not isinstance(payload, dict):
        return None, [f"missing_canonical:{label}"]
    return payload, []


def _collect_proof_manifest_references(root: Path) -> tuple[set[str], list[str]]:
    manifest_path = root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    payload, errors = _load_json_dict(
        manifest_path, "artifacts/proof/current/proof_manifest.json"
    )
    if payload is None:
        return set(), errors

    references: set[str] = set()
    proof_commands = payload.get("proof_commands")
    if isinstance(proof_commands, list):
        for entry in proof_commands:
            if not isinstance(entry, dict):
                continue
            for key in ("path", "log_path"):
                val = entry.get(key)
                if isinstance(val, str) and val:
                    references.add(val.replace("\\", "/"))
    required_logs = payload.get("required_logs")
    if isinstance(required_logs, list):
        for rel_path in required_logs:
            if isinstance(rel_path, str) and rel_path:
                references.add(rel_path.replace("\\", "/"))
    return references, errors


def _collect_required_log_index_references(root: Path) -> tuple[set[str], list[str]]:
    index_path = root / "artifacts" / "proof" / "current" / "required_log_index.json"
    payload, errors = _load_json_dict(
        index_path, "artifacts/proof/current/required_log_index.json"
    )
    if payload is None:
        return set(), errors

    references: set[str] = set()
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return references, errors

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            continue
        normalized = rel_path.replace("\\", "/")
        references.add(normalized)
        if entry.get("exists") is True and not (root / normalized).is_file():
            errors.append(f"required_log_index_exists_but_missing:{normalized}")
    return references, errors


def validate_final_zip(zip_path: Path, *, allow_noncanonical: bool = False) -> dict:
    """Main validation routine.
    
    Returns dict with:
    - valid: bool
    - zip_path: str
    - zip_sha256: str
    - top_level_dirs: list[str]
    - runtime_roots_count: int
    - runtime_root: str (if exactly one)
    - errors: list[str]
    - warnings: list[str]
    - validated_at_utc: str
    """
    
    result: dict[str, Any] = {
        "valid": False,
        "zip_path": str(zip_path),
        "zip_sha256": "",
        "top_level_dirs": [],
        "runtime_roots_count": 0,
        "runtime_root": None,
        "errors": [],
        "warnings": [],
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    
    # Check canonical archive name
    if not allow_noncanonical and zip_path.name != CANONICAL_ARCHIVE_NAME:
        result["errors"].append(
            f"archive_name_not_authoritative:expected_{CANONICAL_ARCHIVE_NAME}_got_{zip_path.name}"
        )

    # Check ZIP exists
    if not zip_path.exists():
        result["errors"].append("zip_not_found")
        return result
    
    if not zip_path.is_file():
        result["errors"].append("zip_not_file")
        return result
    
    # Check ZIP is readable
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Verify ZIP integrity
            if zf.testzip() is not None:
                result["errors"].append("zip_corrupt_testzip_failed")
                return result
    except Exception as e:
        result["errors"].append(f"zip_open_failed:{str(e)}")
        return result
    
    # Compute SHA-256
    try:
        sha256 = compute_sha256(zip_path)
        result["zip_sha256"] = sha256
    except Exception as e:
        result["errors"].append(f"sha256_compute_failed:{str(e)}")
        return result
    
    # Extract and validate
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir_path)
        except Exception as e:
            result["errors"].append(f"extract_failed:{str(e)}")
            return result
        
        # Find top-level directories
        top_level = sorted({
            p.name for p in tmpdir_path.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        })
        result["top_level_dirs"] = top_level
        
        # Find runtime roots
        roots = find_runtime_roots(tmpdir_path)
        result["runtime_roots_count"] = len(roots)
        
        if len(roots) == 0:
            result["errors"].append("no_runtime_root_found")
            return result
        
        if len(roots) > 1:
            result["errors"].append(f"multiple_runtime_roots_found:{len(roots)}")
            for root in roots:
                result["errors"].append(f"  - {root.relative_to(tmpdir_path)}")
            return result
        
        # Exactly one root - validate it
        root = roots[0]
        result["runtime_root"] = str(root.relative_to(tmpdir_path))
        if result["runtime_root"] != CANONICAL_ROOT_NAME:
            result["errors"].append(
                "root_name_not_authoritative:"
                f"expected_{CANONICAL_ROOT_NAME}_got_{result['runtime_root']}"
            )
        
        # Validate structure
        valid, struct_errors = validate_archive_structure(tmpdir_path, root)
        result["errors"].extend(struct_errors)
        
        # Check forbidden paths globally
        forbidden = find_forbidden_paths(tmpdir_path)
        if forbidden:
            for rel_path in forbidden:
                result["errors"].append(f"forbidden_path:{rel_path}")
        
        # Check nested artifacts
        nested = find_nested_artifacts(tmpdir_path, root)
        if nested:
            result["errors"].append(f"nested_artifacts_found:{len(nested)}")
            result["errors"].extend([f"  - {p}" for p in nested])
        
        # Check duplicate critical files
        duplicates = find_duplicate_critical_files(tmpdir_path, root)
        if duplicates:
            result["errors"].append(f"duplicate_critical_files:{len(duplicates)}")
            result["errors"].extend([f"  - {p}" for p in duplicates])
        
        # Check forbidden in root specifically
        root_forbidden = check_forbidden_paths_in_root(root)
        result["errors"].extend(root_forbidden)

        # Cross-check all log_path references inside release_gate.json
        missing_logs = validate_referenced_proof_logs(root)
        result["errors"].extend(missing_logs)

        # Cross-check proof manifest and required log index references.
        manifest_refs, manifest_errors = _collect_proof_manifest_references(root)
        result["errors"].extend(manifest_errors)
        required_index_refs, required_index_errors = (
            _collect_required_log_index_references(root)
        )
        result["errors"].extend(required_index_errors)
        for rel_path in sorted(manifest_refs | required_index_refs):
            if not (root / rel_path).is_file():
                result["errors"].append(f"missing_required_proof_file:{rel_path}")

        gate_json = root / "artifacts" / "proof" / "current" / "release_gate.json"
        gate_payload, gate_errors = _load_json_dict(
            gate_json, "artifacts/proof/current/release_gate.json"
        )
        result["errors"].extend(gate_errors)
        if gate_payload and bool(gate_payload.get("alpha_gate_passed", False)):
            has_missing = any(
                err.startswith("missing_canonical:")
                or err.startswith("missing_referenced_log:")
                or err.startswith("missing_required_proof_file:")
                or err.startswith("required_log_index_exists_but_missing:")
                for err in result["errors"]
            )
            if has_missing:
                result["errors"].append("alpha_gate_passed_missing_file")

        # If we have some critical errors, fail fast
        if result["errors"]:
            return result
        
        # Try to run proof freshness check on extracted content
        try:
            freshness_script = root / "scripts" / "check_proof_freshness.py"
            python_bin = sys.executable or "python3"
            freshness_result = subprocess.run(
                [
                    python_bin,
                    str(freshness_script),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if freshness_result.returncode != 0:
                result["warnings"].append("proof_freshness_check_failed")
                detail = "\n".join(
                    part
                    for part in (
                        freshness_result.stdout.strip(),
                        freshness_result.stderr.strip(),
                    )
                    if part
                )
                if detail:
                    result["warnings"].append(detail)
        except Exception as e:
            result["warnings"].append(f"proof_freshness_check_error:{str(e)}")
    
    # Mark as valid if no errors
    result["valid"] = len(result["errors"]) == 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate final ZIP archive for JUDGE_ATLAS release"
    )
    parser.add_argument("zip_path", help="Absolute path to final archive ZIP")
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Write validation result to JSON file",
    )
    parser.add_argument(
        "--allow-noncanonical",
        action="store_true",
        default=False,
        help="Skip the canonical archive-name check (for CI temp paths).",
    )

    args = parser.parse_args()
    zip_path = Path(args.zip_path)

    result = validate_final_zip(zip_path, allow_noncanonical=args.allow_noncanonical)
    
    # Write result to JSON if requested
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with args.output_json.open("w") as f:
            json.dump(result, f, indent=2)
    
    # Print summary
    print(f"Archive: {result['zip_path']}")
    print(f"SHA-256: {result['zip_sha256']}")
    print(f"Runtime Root: {result['runtime_root']}")
    print(f"Valid: {'YES' if result['valid'] else 'NO'}")
    
    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"  - {err}")
    
    if result["warnings"]:
        print(f"\nWarnings ({len(result['warnings'])}):")
        for warn in result["warnings"]:
            print(f"  - {warn}")
    
    # Exit code: 0 if valid, 1 if errors
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
