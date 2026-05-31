#!/usr/bin/env python3
"""Build a clean release archive for distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "JUDGE_ATLAS-main-final.zip"
DEFAULT_ROOT_NAME = "JUDGE_ATLAS-main"
CANONICAL_ARCHIVE_NAME = "JUDGE_ATLAS-main-final.zip"
CANONICAL_ROOT_NAME = "JUDGE_ATLAS-main"

DEFAULT_INCLUDE_TOP_LEVEL = (
    ".github",
    "backend",
    "frontend",
    "demo",
    "deploy",
    "docs",
    "scripts",
    "infra",
)
DEFAULT_INCLUDE_PROOF_FILES = (
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
DEFAULT_INCLUDE_FILES = (
    "README.md",
    "STATUS.md",
    "CURRENT_STATUS.md",
    "PROOF_STATUS.md",
    "RELEASE_BLOCKERS.md",
    "STUBS_AND_PLACEHOLDERS.md",
    "REPO_REALITY.md",
    "COMPLETION_CHECKLIST.md",
    "Makefile",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "Dockerfile.proof",
    "docker-compose.yml",
    "docker-compose.yaml",
)

EXCLUDED_PREFIXES = (
    "__MACOSX/",
    "research/",
    "external/",
    "external_reference/",
    "docs/archive/",
    "node_modules/",
    "frontend/node_modules/",
    "frontend/.next/",
    ".venv/",
    "backend/.venv/",
    "venv/",
    ".git/",
    ".trunk/",
    "artifacts/proof/archive/",
    "artifacts/proof/backend/",
    "artifacts/proof/frontend/",
    "artifacts/proof/history/",
    "artifacts/proof/latest/",
    "artifacts/history/",
    ".validation_logs/",
    "proof/latest/",
    "logs/",
    "tmp/",
    "temp/",
    "data/evidence_store/",
    "evidence_store/",
)
EXCLUDED_SEGMENTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
EXCLUDED_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".tmp",
    ".swp",
    ".pem",
    ".key",
    ".tsbuildinfo",
)
EXCLUDED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".DS_Store",
    "Thumbs.db",
    "id_rsa",
    "id_ed25519",
    "archive_validation.md",
    "archive_validation.log",
    ".coverage",
}
TEXT_REDACT_SUFFIXES = {".md", ".json", ".txt", ".yml", ".yaml", ".toml"}
PACKAGED_PROOF_EXCLUDED_PATHS = {
    "artifacts/proof/current/archive_validation.log",
    "artifacts/proof/current/archive_validation.md",
}
LOCAL_PATH_PATTERNS = (
    re.compile(r"/Users/[^\s\"'`]+"),
    re.compile(r"/home/[^\s\"'`]+"),
    re.compile(r"/private/[^\s\"'`]+"),
    re.compile(r"[A-Za-z]:\\[^\s\"'`]+"),
)


def _is_macos_sidecar(name: str) -> bool:
    return name.startswith("._")


def _redact_local_paths_in_string(text: str) -> str:
    for pattern in LOCAL_PATH_PATTERNS:
        text = pattern.sub("[REDACTED_LOCAL_PATH]", text)
    return text


def _redact_json_value(value):
    if isinstance(value, str):
        return _redact_local_paths_in_string(value)
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_json_value(item) for key, item in value.items()}
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(repo_root: Path) -> str | None:
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return cp.stdout.strip() or None


def _normalize(path: Path) -> str:
    return path.as_posix()


def _is_excluded(rel_path: str, include_external: bool, include_proof_archive: bool) -> bool:
    # Normalise first path component (strip + casefold) so case/whitespace
    # variants like "Research /" or "External/" are caught by EXCLUDED_PREFIXES.
    _parts = Path(rel_path).parts
    if _parts:
        _norm_first = _parts[0].strip().casefold()
        _rest = "/".join(_parts[1:]) if len(_parts) > 1 else ""
        _norm_rel = (_norm_first + "/" + _rest) if _rest else _norm_first
    else:
        _norm_rel = rel_path

    if not include_external and _norm_rel.startswith("external/"):
        return True
    if not include_proof_archive and rel_path.startswith("artifacts/proof/archive/"):
        return True
    if any(_norm_rel.startswith(prefix) or rel_path.startswith(prefix) for prefix in EXCLUDED_PREFIXES):
        if include_external and _norm_rel.startswith("external/"):
            return False
        if include_proof_archive and rel_path.startswith("artifacts/proof/archive/"):
            return False
        return True

    parts = Path(rel_path).parts
    if "__MACOSX" in parts:
        return True
    if any(part in EXCLUDED_SEGMENTS for part in parts):
        return True
    if any(_is_macos_sidecar(part) for part in parts):
        return True
    if any(part.lower().endswith(".egg-info") for part in parts):
        return True

    name = Path(rel_path).name
    lower_name = name.lower()
    if _is_macos_sidecar(name):
        return True
    if lower_name in EXCLUDED_FILE_NAMES:
        return True
    if lower_name.startswith(".env."):
        return True
    if lower_name.endswith(EXCLUDED_SUFFIXES):
        return True
    return False


def _load_packaged_proof_paths(repo_root: Path) -> set[str]:
    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    packaged: set[str] = set()
    if not release_gate_path.exists():
        proof_logs_dir = repo_root / "artifacts" / "proof" / "current"
        if proof_logs_dir.exists():
            for log_path in proof_logs_dir.glob("*.log"):
                packaged.add(_normalize(log_path.relative_to(repo_root)))
        return packaged
    try:
        payload = json.loads(release_gate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return packaged

    logs = payload.get("logs", {})
    if isinstance(logs, dict):
        for path in logs.values():
            if not isinstance(path, str):
                continue
            normalized = path.replace("\\", "/")
            if normalized.startswith("artifacts/proof/current/"):
                if normalized in PACKAGED_PROOF_EXCLUDED_PATHS:
                    continue
                packaged.add(normalized)

    checks = payload.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            check_log_path = check.get("log_path")
            if not isinstance(check_log_path, str):
                continue
            normalized = check_log_path.replace("\\", "/")
            if normalized.startswith("artifacts/proof/current/"):
                if normalized in PACKAGED_PROOF_EXCLUDED_PATHS:
                    continue
                packaged.add(normalized)

    proof_logs_dir = repo_root / "artifacts" / "proof" / "current"
    if proof_logs_dir.exists():
        for log_file in proof_logs_dir.glob("*.log"):
            normalized = _normalize(log_file.relative_to(repo_root))
            if normalized in PACKAGED_PROOF_EXCLUDED_PATHS:
                continue
            packaged.add(normalized)
    return packaged


def _load_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid payload type at {path}: {type(payload).__name__}")
    return payload


def _collect_proof_manifest_paths(repo_root: Path) -> set[str]:
    manifest_path = repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing canonical proof manifest: {manifest_path}")
    payload = _load_json_object(manifest_path)
    proof_commands = payload.get("proof_commands")
    if not isinstance(proof_commands, list):
        raise SystemExit("Invalid proof_manifest.json: proof_commands must be a list")

    referenced: set[str] = set()
    for entry in proof_commands:
        if not isinstance(entry, dict):
            continue
        for key in ("path", "log_path"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                normalized = value.replace("\\", "/")
                if normalized in PACKAGED_PROOF_EXCLUDED_PATHS:
                    continue
                referenced.add(normalized)
    return referenced


def _collect_required_log_index_paths(repo_root: Path) -> tuple[set[str], list[str]]:
    index_path = repo_root / "artifacts" / "proof" / "current" / "required_log_index.json"
    if not index_path.is_file():
        raise SystemExit(f"Missing canonical required log index: {index_path}")
    payload = _load_json_object(index_path)
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise SystemExit("Invalid required_log_index.json: entries must be a list")

    referenced: set[str] = set()
    exists_true_missing: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("path")
        if not isinstance(rel_path, str) or not rel_path:
            continue
        normalized = rel_path.replace("\\", "/")
        if normalized in PACKAGED_PROOF_EXCLUDED_PATHS:
            continue
        referenced.add(normalized)
        if entry.get("exists") is True and not (repo_root / normalized).is_file():
            exists_true_missing.append(normalized)
    return referenced, sorted(set(exists_true_missing))


def _collect_proof_preconditions(repo_root: Path) -> dict[str, object]:
    packaged_proof_paths = _load_packaged_proof_paths(repo_root)
    proof_manifest_paths = _collect_proof_manifest_paths(repo_root)
    required_log_index_paths, required_index_exists_true_missing = (
        _collect_required_log_index_paths(repo_root)
    )

    missing_required_proof_files = sorted(
        rel_path
        for rel_path in DEFAULT_INCLUDE_PROOF_FILES
        if not (repo_root / rel_path).is_file()
    )
    all_referenced_proof_paths = (
        packaged_proof_paths | proof_manifest_paths | required_log_index_paths
    )
    missing_referenced_proof_paths = sorted(
        rel_path
        for rel_path in all_referenced_proof_paths
        if not (repo_root / rel_path).is_file()
    )

    return {
        "packaged_proof_paths": packaged_proof_paths,
        "proof_manifest_paths": proof_manifest_paths,
        "required_log_index_paths": required_log_index_paths,
        "required_index_exists_true_missing": required_index_exists_true_missing,
        "missing_required_proof_files": missing_required_proof_files,
        "missing_referenced_proof_paths": missing_referenced_proof_paths,
        "all_referenced_proof_paths": all_referenced_proof_paths,
    }


def _enforce_proof_preconditions(preconditions: dict[str, object]) -> None:
    missing_required_proof_files = preconditions["missing_required_proof_files"]
    missing_referenced_proof_paths = preconditions["missing_referenced_proof_paths"]
    required_index_exists_true_missing = preconditions["required_index_exists_true_missing"]

    if missing_required_proof_files:
        raise SystemExit(
            "Missing required proof files for archive packaging: "
            + ", ".join(missing_required_proof_files)
        )

    if missing_referenced_proof_paths:
        raise SystemExit(
            "Missing packaged proof files required by release metadata: "
            + ", ".join(missing_referenced_proof_paths)
        )
    if required_index_exists_true_missing:
        raise SystemExit(
            "required_log_index_exists_but_missing:"
            + ",".join(required_index_exists_true_missing)
        )


def _strip_packaged_archive_validation_metadata(rel: str, payload):
    if rel.endswith("artifacts/proof/current/release_gate.json") and isinstance(payload, dict):
        logs = payload.get("logs")
        if isinstance(logs, dict):
            payload["logs"] = {
                key: value
                for key, value in logs.items()
                if value not in PACKAGED_PROOF_EXCLUDED_PATHS and key != "archive_validation"
            }

        checks = payload.get("checks")
        if isinstance(checks, list):
            payload["checks"] = [
                entry
                for entry in checks
                if not (
                    isinstance(entry, dict)
                    and (
                        entry.get("name") == "archive_validation"
                        or entry.get("log_path") in PACKAGED_PROOF_EXCLUDED_PATHS
                    )
                )
            ]

    if rel.endswith("artifacts/proof/current/proof_manifest.json") and isinstance(payload, dict):
        proof_commands = payload.get("proof_commands")
        if isinstance(proof_commands, list):
            payload["proof_commands"] = [
                entry
                for entry in proof_commands
                if not (
                    isinstance(entry, dict)
                    and (
                        entry.get("name") == "archive_validation"
                        or entry.get("path") in PACKAGED_PROOF_EXCLUDED_PATHS
                        or entry.get("log_path") in PACKAGED_PROOF_EXCLUDED_PATHS
                    )
                )
            ]

    return payload


def _load_release_gate(repo_root: Path) -> dict:
    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    if not release_gate_path.is_file():
        raise SystemExit(f"Missing canonical release gate: {release_gate_path}")
    try:
        payload = json.loads(release_gate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid release_gate.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid release_gate.json payload type: {type(payload).__name__}")
    return payload


def _collect_files(
    repo_root: Path,
    include_external: bool,
    include_proof_archive: bool,
    packaged_proof_paths: set[str],
) -> tuple[list[Path], set[str], set[str]]:
    included: set[Path] = set()
    included_top_level: set[str] = set()
    excluded_top_level: set[str] = set()

    for rel in DEFAULT_INCLUDE_TOP_LEVEL:
        path = repo_root / rel
        if path.is_file():
            included.add(path)
            included_top_level.add(rel.split("/", 1)[0])
        elif path.is_dir():
            try:
                iterator = path.rglob("*")
            except FileNotFoundError:
                continue
            for file_path in iterator:
                try:
                    if not file_path.is_file():
                        continue
                    rel_path = _normalize(file_path.relative_to(repo_root))
                except FileNotFoundError:
                    continue
                if _is_excluded(rel_path, include_external, include_proof_archive):
                    excluded_top_level.add(rel_path.split("/", 1)[0])
                    continue
                included.add(file_path)
                included_top_level.add(rel_path.split("/", 1)[0])

    for rel in DEFAULT_INCLUDE_FILES:
        path = repo_root / rel
        if path.is_file():
            rel_path = _normalize(path.relative_to(repo_root))
            if _is_excluded(rel_path, include_external, include_proof_archive):
                excluded_top_level.add(rel_path.split("/", 1)[0])
                continue
            included.add(path)
            included_top_level.add(rel_path.split("/", 1)[0])

    for rel in DEFAULT_INCLUDE_PROOF_FILES:
        path = repo_root / rel
        if path.is_file():
            rel_path = _normalize(path.relative_to(repo_root))
            if _is_excluded(rel_path, include_external, include_proof_archive):
                excluded_top_level.add(rel_path.split("/", 1)[0])
                continue
            included.add(path)
            included_top_level.add(rel_path.split("/", 1)[0])

    for rel in sorted(packaged_proof_paths):
        path = repo_root / rel
        if path.is_file():
            rel_path = _normalize(path.relative_to(repo_root))
            included.add(path)
            included_top_level.add(rel_path.split("/", 1)[0])

    for compose_file in repo_root.glob("docker-compose*.yml"):
        if compose_file.is_file():
            rel_path = _normalize(compose_file.relative_to(repo_root))
            if _is_excluded(rel_path, include_external, include_proof_archive):
                excluded_top_level.add(rel_path.split("/", 1)[0])
                continue
            included.add(compose_file)
            included_top_level.add(rel_path.split("/", 1)[0])

    for compose_file in repo_root.glob("docker-compose*.yaml"):
        if compose_file.is_file():
            rel_path = _normalize(compose_file.relative_to(repo_root))
            if _is_excluded(rel_path, include_external, include_proof_archive):
                excluded_top_level.add(rel_path.split("/", 1)[0])
                continue
            included.add(compose_file)
            included_top_level.add(rel_path.split("/", 1)[0])

    for candidate in repo_root.iterdir():
        if not candidate.exists():
            continue
        if _is_excluded(candidate.name + ("/" if candidate.is_dir() else ""), include_external, include_proof_archive):
            excluded_top_level.add(candidate.name)

    return sorted(included), included_top_level, excluded_top_level


def _load_proof_input_exempt_paths(repo_root: Path) -> set[str]:
    try:
        payload = _load_release_gate(repo_root)
    except SystemExit:
        return set()

    listed = payload.get("proof_input_file_list", [])
    if not isinstance(listed, list):
        return set()

    result: set[str] = set()
    for entry in listed:
        if isinstance(entry, str) and entry:
            result.add(entry)
    return result


def _write_archive(
    output: Path,
    root_name: str,
    files: list[Path],
    manifest: dict,
    proof_input_exempt_paths: set[str],
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            rel = _normalize(file_path.relative_to(REPO_ROOT))
            arcname = f"{root_name}/{rel}"
            if file_path.suffix.lower() in TEXT_REDACT_SUFFIXES:
                if rel in proof_input_exempt_paths:
                    zf.write(file_path, arcname)
                    continue
                raw = file_path.read_bytes()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    zf.write(file_path, arcname)
                    continue
                if file_path.suffix.lower() == ".json":
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        redacted_text = _redact_local_paths_in_string(text)
                    else:
                        payload = _strip_packaged_archive_validation_metadata(rel, payload)
                        redacted_payload = _redact_json_value(payload)
                        redacted_text = json.dumps(redacted_payload, indent=2, sort_keys=True) + "\n"
                else:
                    redacted_text = _redact_local_paths_in_string(text)
                zf.writestr(arcname, redacted_text.encode("utf-8"))
            else:
                zf.write(file_path, arcname)
        zf.writestr(
            f"{root_name}/RELEASE_MANIFEST.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )


def build_archive(
    output: Path,
    root_name: str,
    include_external: bool,
    include_proof_archive: bool,
    require_release_candidate: bool = False,
    allow_noncanonical: bool = False,
    allow_noncanonical_root: bool = False,
) -> dict:
    output_display = (
        _normalize(output.relative_to(REPO_ROOT))
        if output.is_absolute() and output.is_relative_to(REPO_ROOT)
        else output.name
    )

    release_gate = _load_release_gate(REPO_ROOT)

    if not allow_noncanonical and output.name != CANONICAL_ARCHIVE_NAME:
        raise SystemExit(
            "archive_name_not_authoritative:"
            f"expected_{CANONICAL_ARCHIVE_NAME}_got_{output.name}"
        )
    if not allow_noncanonical_root and root_name != CANONICAL_ROOT_NAME:
        raise SystemExit(
            "root_name_not_authoritative:"
            f"expected_{CANONICAL_ROOT_NAME}_got_{root_name}"
        )
    alpha_gate_passed = bool(release_gate.get("alpha_gate_passed", False))
    release_candidate = bool(release_gate.get("release_candidate", False))
    production_ready = bool(release_gate.get("production_ready", False))

    if require_release_candidate and not release_candidate:
        raise SystemExit(
            "Refusing archive build: release_candidate is false in canonical release gate "
            "(use without --require-release-candidate only for blocked proof snapshots)."
        )

    preconditions = _collect_proof_preconditions(REPO_ROOT)
    _enforce_proof_preconditions(preconditions)
    packaged_proof_paths = preconditions["packaged_proof_paths"]
    proof_manifest_paths = preconditions["proof_manifest_paths"]
    required_log_index_paths = preconditions["required_log_index_paths"]

    files, included_top_level, excluded_top_level = _collect_files(
        REPO_ROOT,
        include_external=include_external,
        include_proof_archive=include_proof_archive,
        packaged_proof_paths=(
            packaged_proof_paths | proof_manifest_paths | required_log_index_paths
        ),
    )

    included_rel_paths = {_normalize(path.relative_to(REPO_ROOT)) for path in files}
    missing_packaged_proof = sorted(packaged_proof_paths - included_rel_paths)
    if missing_packaged_proof:
        raise SystemExit(
            "Missing packaged proof files required by release_gate.json: "
            + ", ".join(missing_packaged_proof)
        )

    command_parts = [
        "python3",
        "scripts/build_release_archive.py",
        "--output",
        output_display,
        "--root-name",
        root_name,
    ]
    if include_external:
        command_parts.append("--include-external")
    if include_proof_archive:
        command_parts.append("--include-proof-archive")
    if require_release_candidate:
        command_parts.append("--require-release-candidate")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _git_commit(REPO_ROOT),
        "root_name": root_name,
        "included_top_level_paths": sorted(included_top_level),
        "excluded_top_level_paths": sorted(excluded_top_level),
        "proof_path": "artifacts/proof/current",
        "alpha_status": "PASS" if alpha_gate_passed else "BLOCKED",
        "alpha_gate_passed": alpha_gate_passed,
        "release_candidate": release_candidate,
        "production_ready": production_ready,
        "release_blockers_remaining": release_gate.get("release_blockers_remaining", []),
        "failed_checks": release_gate.get("failed_checks", []),
        "archive_sha256": "computed_after_build",
        "validator_command": (
            f"python3 scripts/validate_release_archive.py --archive {output_display} --expected-root {root_name}"
        ),
        "build_command": " ".join(command_parts),
    }

    proof_input_exempt_paths = _load_proof_input_exempt_paths(REPO_ROOT)

    _write_archive(output, root_name, files, manifest, proof_input_exempt_paths)
    first_hash = _sha256(output)
    manifest["archive_sha256"] = first_hash
    _write_archive(output, root_name, files, manifest, proof_input_exempt_paths)

    final_hash = _sha256(output)
    return {
        "output": str(output),
        "root_name": root_name,
        "archive_sha256": final_hash,
        "file_count": len(files) + 1,
        "included_top_level_paths": sorted(included_top_level),
        "excluded_top_level_paths": sorted(excluded_top_level),
        "packaged_proof_path_count": len(packaged_proof_paths),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output zip path")
    parser.add_argument("--root-name", default=DEFAULT_ROOT_NAME, help="Top-level directory name")
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Include external/ tree in archive",
    )
    parser.add_argument(
        "--include-proof-archive",
        action="store_true",
        help="Include artifacts/proof/archive/ in archive",
    )
    parser.add_argument("--dry-run", action="store_true", help="List files that would be archived without writing")
    parser.add_argument(
        "--strict-dry-run",
        action="store_true",
        help="Return non-zero when dry-run detects non-canonical output or missing proof preconditions.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--require-release-candidate",
        action="store_true",
        help="Fail unless artifacts/proof/current/release_gate.json has release_candidate=true",
    )
    parser.add_argument(
        "--allow-noncanonical",
        action="store_true",
        help="Allow archive names other than JUDGE_ATLAS-main-final.zip.",
    )
    parser.add_argument(
        "--allow-noncanonical-root",
        action="store_true",
        help="Allow archive root names other than JUDGE_ATLAS-main.",
    )
    args = parser.parse_args()

    if args.dry_run:
        dry_run_errors: list[str] = []
        if not args.allow_noncanonical and Path(args.output).name != CANONICAL_ARCHIVE_NAME:
            dry_run_errors.append(
                f"archive_name_not_authoritative:expected_{CANONICAL_ARCHIVE_NAME}_got_{Path(args.output).name}"
            )
        if not args.allow_noncanonical_root and args.root_name != CANONICAL_ROOT_NAME:
            dry_run_errors.append(
                f"root_name_not_authoritative:expected_{CANONICAL_ROOT_NAME}_got_{args.root_name}"
            )

        preconditions: dict[str, object] | None = None
        try:
            preconditions = _collect_proof_preconditions(REPO_ROOT)
        except SystemExit as exc:
            dry_run_errors.append(str(exc))

        packaged_paths_for_collection = _load_packaged_proof_paths(REPO_ROOT)
        missing_required_proof_files: list[str] = []
        missing_referenced_proof_paths: list[str] = []
        required_index_exists_true_missing: list[str] = []
        if preconditions is not None:
            packaged_paths_for_collection = preconditions["all_referenced_proof_paths"]
            missing_required_proof_files = preconditions["missing_required_proof_files"]
            missing_referenced_proof_paths = preconditions["missing_referenced_proof_paths"]
            required_index_exists_true_missing = preconditions["required_index_exists_true_missing"]

        files, included_top_level, excluded_top_level = _collect_files(
            REPO_ROOT,
            include_external=args.include_external,
            include_proof_archive=args.include_proof_archive,
            packaged_proof_paths=packaged_paths_for_collection,
        )
        dry_run_valid = (
            not dry_run_errors
            and not missing_required_proof_files
            and not missing_referenced_proof_paths
            and not required_index_exists_true_missing
        )
        result = {
            "dry_run": True,
            "dry_run_valid": dry_run_valid,
            "root_name": args.root_name,
            "file_count": len(files),
            "missing_required_proof_files": missing_required_proof_files,
            "missing_referenced_proof_files": missing_referenced_proof_paths,
            "required_log_index_exists_but_missing": required_index_exists_true_missing,
            "errors": dry_run_errors,
            "included_top_level_paths": sorted(included_top_level),
            "excluded_top_level_paths": sorted(excluded_top_level),
            "files": [_normalize(f.relative_to(REPO_ROOT)) for f in files],
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"[dry-run] Would archive {result['file_count']} files under root '{args.root_name}'")
            print(f"[dry-run] valid={dry_run_valid}")
            if dry_run_errors:
                print("[dry-run] errors:")
                for error in dry_run_errors:
                    print(f"  {error}")
            if missing_required_proof_files:
                print("[dry-run] missing required proof files:")
                for path in missing_required_proof_files:
                    print(f"  {path}")
            if missing_referenced_proof_paths:
                print("[dry-run] missing referenced proof files:")
                for path in missing_referenced_proof_paths:
                    print(f"  {path}")
            if required_index_exists_true_missing:
                print("[dry-run] required_log_index exists=true but missing on disk:")
                for path in required_index_exists_true_missing:
                    print(f"  {path}")
            for f in result["files"]:
                print(f"  {f}")
        if args.strict_dry_run and not dry_run_valid:
            return 1
        return 0

    output = Path(args.output).resolve()
    result = build_archive(
        output=output,
        root_name=args.root_name,
        include_external=args.include_external,
        include_proof_archive=args.include_proof_archive,
        require_release_candidate=args.require_release_candidate,
        allow_noncanonical=args.allow_noncanonical,
        allow_noncanonical_root=args.allow_noncanonical_root,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Built clean release archive: {result['output']}")
        print(f"archive_sha256={result['archive_sha256']}")
        print(f"file_count={result['file_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
