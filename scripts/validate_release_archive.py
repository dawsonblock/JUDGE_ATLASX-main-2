#!/usr/bin/env python3
"""Validate a release archive against the current alpha release boundary."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "proof" / "current" / "archive_validation.md"
ARCHIVED_HEADER = "ARCHIVED / NOT CURRENT"
REQUIRED_DIRECTORIES = (
    ".github/",
    "backend/",
    "frontend/",
    "demo/",
    "docs/",
    "infra/",
    "scripts/",
    "artifacts/proof/current/",
)
REQUIRED_PROOF_FILES = (
    "artifacts/proof/current/CURRENT_PROOF.md",
    "artifacts/proof/current/CURRENT_ALPHA_STATUS.md",
    "artifacts/proof/current/SOURCE_REGISTRY_STATUS.md",
    "artifacts/proof/current/REPAIR_REPORT.md",
    "artifacts/proof/current/FIX_VERIFICATION_REPORT.md",
    "artifacts/proof/current/release_readiness.md",
    "artifacts/proof/current/release_gate.json",
    "artifacts/proof/current/proof_manifest.json",
    "artifacts/proof/current/required_log_index.json",
    "artifacts/proof/current/source_registry_status.json",
)
REQUIRED_ROOT_FILES = (
    "README.md",
)
FORBIDDEN_SEGMENTS = (
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".validation_logs",
    ".git",
)
FORBIDDEN_RELATIVE_PREFIXES = (
    "artifacts/proof/archive/",
    "artifacts/proof/backend/",
    "artifacts/proof/frontend/",
    "artifacts/proof/history/",
    "artifacts/proof/latest/",
    "artifacts/history/",
    "artifacts/proof/v",
    "proof/latest/",
    "external/",
    "external_reference/",
    "research/",
    "logs/",
    "tmp/",
    "temp/",
    "data/evidence_store/",
    "evidence_store/",
)
FORBIDDEN_FILE_NAMES = (
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".coverage",
    ".ds_store",
    "thumbs.db",
    "id_rsa",
    "id_ed25519",
    "archive_validation.md",
)
FORBIDDEN_FILE_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".crt",
    ".tsbuildinfo",
)
PROOF_INCOMPLETE_PREFIX = "PROOF_INCOMPLETE:"
TEXT_METADATA_SUFFIXES = {".md", ".json", ".txt", ".yml", ".yaml"}
ABSOLUTE_PATH_PATTERNS = (
    re.compile(r'/Users/[^"\)\s]+'),
    re.compile(r'/home/[^"\)\s]+'),
    re.compile(r'/private/[^"\)\s]+'),
    re.compile(r"[A-Za-z]:\\[^\s]+"),
)


def _redact_embedded_path(value: str) -> str:
    """Redact any local absolute path fragments from an arbitrary string."""
    if not value:
        return value
    redacted = value.replace("\\", "/")
    for pattern in ABSOLUTE_PATH_PATTERNS:
        redacted = pattern.sub("[REDACTED_LOCAL_PATH]", redacted)
    return redacted


def _display_path(path: Path) -> str:
    """Render paths for reports without leaking local absolute prefixes."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return f"[REDACTED_LOCAL_PATH]/{resolved.name}"


def _compute_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _top_level_roots(names: list[str]) -> list[str]:
    roots = sorted({name.split("/", 1)[0] for name in names if name and "/" in name})
    return [root for root in roots if root]


def _dir_exists(names: set[str], root: str, rel_dir: str) -> bool:
    prefix = f"{root}/{rel_dir}"
    return any(name == prefix or name.startswith(prefix) for name in names)


def _read_text_member(zf: zipfile.ZipFile, name: str) -> str | None:
    try:
        raw = zf.read(name)
    except KeyError:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def inspect_archive(
    archive: Path,
    expected_root: str,
    allow_external: bool = False,
    require_release_candidate: bool = False,
) -> dict:
    report: dict = {
        "archive": _display_path(archive),
        "expected_root": expected_root,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "valid": False,
        "errors": [],
        "warnings": [],
        "archive_sha256": "",
        "compressed_size_bytes": 0,
        "uncompressed_size_bytes": 0,
        "top_level_roots": [],
        "actual_root": None,
        "largest_files": [],
        "largest_top_level_directories": [],
    }

    if not archive.exists() or not archive.is_file():
        report["errors"].append("archive_not_found")
        return report

    if re.match(r".*-main(?:\s+\d+)?\.zip$", archive.name, re.IGNORECASE):
        report["errors"].append("forbidden_raw_workspace_archive_name")

    report["archive_sha256"] = _compute_sha256(archive)

    try:
        with zipfile.ZipFile(archive, "r") as zf:
            infos = [info for info in zf.infolist() if info.filename and not info.filename.endswith("/")]
            names = [info.filename for info in infos]
            name_set = set(names)
            report["compressed_size_bytes"] = sum(info.compress_size for info in infos)
            report["uncompressed_size_bytes"] = sum(info.file_size for info in infos)

            roots = _top_level_roots(names)
            report["top_level_roots"] = roots
            if len(roots) != 1:
                report["errors"].append("archive_must_have_exactly_one_top_level_root")
                return report

            root = roots[0]
            report["actual_root"] = root
            if root != expected_root:
                report["errors"].append(f"archive_root_mismatch:{root}!={expected_root}")

            for rel_dir in REQUIRED_DIRECTORIES:
                if not _dir_exists(name_set, root, rel_dir):
                    report["errors"].append(f"missing_required_directory:{rel_dir}")

            for rel_file in REQUIRED_PROOF_FILES:
                if f"{root}/{rel_file}" not in name_set:
                    report["errors"].append(f"missing_required_proof_file:{rel_file}")

            for rel_file in REQUIRED_ROOT_FILES:
                if f"{root}/{rel_file}" not in name_set:
                    report["errors"].append(f"missing_required_root_file:{rel_file}")

            release_gate_name = f"{root}/artifacts/proof/current/release_gate.json"
            proof_manifest_name = f"{root}/artifacts/proof/current/proof_manifest.json"
            release_gate_data: dict | None = None
            proof_manifest_data: dict | None = None
            if release_gate_name in name_set:
                release_gate_text = _read_text_member(zf, release_gate_name)
                if release_gate_text:
                    try:
                        release_gate_data = json.loads(release_gate_text)
                    except json.JSONDecodeError:
                        report["errors"].append("invalid_release_gate_json")

            if proof_manifest_name in name_set:
                proof_manifest_text = _read_text_member(zf, proof_manifest_name)
                if proof_manifest_text:
                    try:
                        proof_manifest_data = json.loads(proof_manifest_text)
                    except json.JSONDecodeError:
                        report["errors"].append("invalid_proof_manifest_json")

            if release_gate_data is not None:
                alpha_gate_passed = release_gate_data.get("alpha_gate_passed")
                release_candidate = release_gate_data.get("release_candidate")
                production_ready = release_gate_data.get("production_ready")

                if alpha_gate_passed is not True:
                    target = "errors" if require_release_candidate else "warnings"
                    report[target].append("release_gate_not_alpha_passed")
                if release_candidate is not True:
                    target = "errors" if require_release_candidate else "warnings"
                    report[target].append("release_gate_not_release_candidate")
                if not isinstance(production_ready, bool):
                    report["errors"].append("release_gate_missing_explicit_production_ready")

                logs = release_gate_data.get("logs", {})
                if isinstance(logs, dict):
                    for key, rel_path in logs.items():
                        if not isinstance(rel_path, str) or not rel_path:
                            continue
                        normalized = rel_path.replace("\\", "/")
                        if normalized.startswith("artifacts/current/"):
                            report["errors"].append(
                                f"legacy_proof_log_reference:{key}:{normalized}"
                            )
                            continue
                        if not normalized.startswith("artifacts/proof/current/"):
                            continue
                        if f"{root}/{normalized}" not in name_set:
                            report["errors"].append(
                                f"missing_claimed_proof_file:{key}:{normalized}"
                            )

                checks = release_gate_data.get("checks", [])
                if isinstance(checks, list):
                    for check in checks:
                        if not isinstance(check, dict):
                            continue
                        check_name = check.get("name", "unknown")
                        log_path = check.get("log_path")
                        if not isinstance(log_path, str) or not log_path:
                            continue
                        normalized = log_path.replace("\\", "/")
                        if normalized.startswith("artifacts/current/"):
                            report["errors"].append(
                                "legacy_proof_log_reference:"
                                f"checks.{check_name}:{normalized}"
                            )
                            continue
                        if not normalized.startswith("artifacts/proof/current/"):
                            continue
                        if f"{root}/{normalized}" not in name_set:
                            report["errors"].append(
                                "missing_claimed_proof_file:"
                                f"checks.{check_name}:{normalized}"
                            )

            if proof_manifest_data is not None:
                required_logs = proof_manifest_data.get("required_logs", [])
                if not isinstance(required_logs, list) or not required_logs:
                    report["errors"].append("proof_manifest_required_logs_missing")
                else:
                    info_by_name = {info.filename: info for info in infos}
                    for entry in required_logs:
                        if not isinstance(entry, str) or not entry:
                            report["errors"].append("proof_manifest_required_logs_invalid_entry")
                            continue
                        archive_name = f"{root}/{entry}"
                        info = info_by_name.get(archive_name)
                        if info is None:
                            report["errors"].append(f"missing_required_log_from_manifest:{entry}")
                            continue
                        if info.file_size <= 0:
                            report["errors"].append(f"empty_required_log_from_manifest:{entry}")

            for info in infos:
                parts = Path(info.filename).parts
                if any(segment in FORBIDDEN_SEGMENTS for segment in parts):
                    report["errors"].append(f"forbidden_path:{info.filename}")
                rel_path = "/".join(parts[1:]) if len(parts) > 1 else info.filename
                rel_parts = Path(rel_path).parts

                if rel_parts:
                    norm_first = rel_parts[0].strip().casefold()
                    norm_rel_path = (
                        norm_first + "/" + "/".join(rel_parts[1:])
                        if len(rel_parts) > 1
                        else norm_first
                    )
                else:
                    norm_rel_path = rel_path

                if not allow_external and (
                    "external" in rel_parts
                    or norm_rel_path.startswith("external/")
                    or norm_rel_path.startswith("external_reference/")
                ):
                    report["errors"].append(f"forbidden_external_path:{info.filename}")
                if "research" in rel_parts or norm_rel_path.startswith("research/"):
                    report["errors"].append(f"forbidden_research_path:{info.filename}")
                for segment in parts:
                    if segment != segment.strip():
                        report["errors"].append(f"whitespace_path_segment:{info.filename}")
                        break
                if any(
                    rel_path.startswith(prefix) or norm_rel_path.startswith(prefix)
                    for prefix in FORBIDDEN_RELATIVE_PREFIXES
                ):
                    report["errors"].append(f"forbidden_release_surface_path:{info.filename}")
                name_lower = Path(rel_path).name.lower()
                if name_lower == "archive_validation.log" and not rel_path.startswith("artifacts/proof/current/"):
                    report["errors"].append(f"forbidden_secret_file:{info.filename}")
                    continue
                if name_lower in FORBIDDEN_FILE_NAMES:
                    report["errors"].append(f"forbidden_secret_file:{info.filename}")
                elif name_lower.endswith(FORBIDDEN_FILE_SUFFIXES) or (
                    name_lower.endswith(".log")
                    and not rel_path.startswith("artifacts/proof/current/")
                ):
                    report["errors"].append(f"forbidden_secret_or_log_suffix:{info.filename}")

            # Verify CURRENT_PROOF.md counts match release_gate.json
            current_proof_name = f"{root}/artifacts/proof/current/CURRENT_PROOF.md"
            if current_proof_name in name_set and release_gate_name in name_set:
                current_proof_text = _read_text_member(zf, current_proof_name)
                release_gate_text = _read_text_member(zf, release_gate_name)
                if current_proof_text and release_gate_text:
                    try:
                        release_gate_data = json.loads(release_gate_text)
                        # Extract key counts from release_gate.json
                        # Map release_gate.json field names to CURRENT_PROOF.md field names
                        expected_counts = {
                            "proof_input_file_count": release_gate_data.get(
                                "proof_input_file_count", 0
                            ),
                            "release_gate_check_count": release_gate_data.get("check_count", 0),
                            "backend pytest": release_gate_data.get(
                                "backend_pytest_passed", 0
                            ),
                            "backend import proof": release_gate_data.get(
                                "backend_import_route_count", 0
                            ),
                        }
                        # Verify these counts appear in CURRENT_PROOF.md
                        # CURRENT_PROOF.md uses format "- key: value" or "- key: PASS (value routes)"
                        for key, expected_value in expected_counts.items():
                            if expected_value is not None and expected_value > 0:
                                # Check for the pattern "- key: value" or "- key: PASS (value routes)"
                                pattern1 = f"- {key}: {expected_value}"
                                pattern2 = f"- {key}:[^\n]*{expected_value}"
                                if pattern1 not in current_proof_text and not re.search(pattern2, current_proof_text):
                                    report["errors"].append(
                                        f"proof_count_mismatch:{key}={expected_value} "
                                        f"not found in CURRENT_PROOF.md"
                                    )
                    except json.JSONDecodeError:
                        report["warnings"].append("release_gate_json_invalid")
            elif current_proof_name in name_set or release_gate_name in name_set:
                # If one exists but not the other, that's an error
                report["errors"].append(
                    "proof_artifacts_incomplete:missing_current_proof_or_release_gate"
                )

            for info in infos:
                suffix = Path(info.filename).suffix.lower()
                if suffix not in TEXT_METADATA_SUFFIXES:
                    continue
                text = _read_text_member(zf, info.filename)
                if text is None:
                    continue
                for pattern in ABSOLUTE_PATH_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        redacted_match = _redact_embedded_path(match.group(0))
                        report["errors"].append(
                            f"absolute_path_embedded:{info.filename}:{redacted_match}"
                        )
                        break

            largest_files = sorted(
                (
                    {
                        "path": info.filename,
                        "uncompressed_size": info.file_size,
                        "compressed_size": info.compress_size,
                    }
                    for info in infos
                ),
                key=lambda item: item["uncompressed_size"],
                reverse=True,
            )[:20]
            report["largest_files"] = largest_files

            dir_sizes: dict[str, int] = defaultdict(int)
            for info in infos:
                rel_parts = Path(info.filename).parts
                if len(rel_parts) >= 2:
                    dir_sizes[rel_parts[1]] += info.file_size
            report["largest_top_level_directories"] = [
                {"path": key, "uncompressed_size": size}
                for key, size in sorted(dir_sizes.items(), key=lambda item: item[1], reverse=True)
            ]
    except zipfile.BadZipFile:
        report["errors"].append("bad_zip_file")
        return report

    report["errors"] = sorted(set(report["errors"]))
    report["warnings"] = sorted(set(report["warnings"]))
    report["valid"] = not report["errors"]
    return report


def write_markdown(report: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# Archive Validation",
        "",
        f"- validated_at_utc: {report['validated_at_utc']}",
        f"- archive: {report['archive']}",
        f"- archive_sha256: {report['archive_sha256']}",
        f"- expected_root: {report['expected_root']}",
        f"- actual_root: {report.get('actual_root') or 'none'}",
        f"- top_level_roots: {', '.join(report['top_level_roots']) or 'none'}",
        f"- root_match: {'yes' if report['top_level_roots'] == [report['expected_root']] else 'no'}",
        f"- valid: {'PASS' if report['valid'] else 'FAIL'}",
        f"- compressed_size_bytes: {report['compressed_size_bytes']}",
        f"- uncompressed_size_bytes: {report['uncompressed_size_bytes']}",
        "",
        "## Errors",
        "",
    ]
    if report["errors"]:
        lines.extend(f"- {error}" for error in report["errors"])
    else:
        lines.append("- none")

    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        lines.extend(f"- {warning}" for warning in report["warnings"])
    else:
        lines.append("- none")

    lines.extend(["", "## Largest Files", ""])
    if report["largest_files"]:
        lines.append("| path | uncompressed | compressed |")
        lines.append("|---|---:|---:|")
        for item in report["largest_files"]:
            lines.append(
                f"| {item['path']} | {item['uncompressed_size']} | {item['compressed_size']} |"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Largest Top-Level Directories", ""])
    if report["largest_top_level_directories"]:
        lines.append("| path | uncompressed |")
        lines.append("|---|---:|")
        for item in report["largest_top_level_directories"]:
            lines.append(f"| {item['path']} | {item['uncompressed_size']} |")
    else:
        lines.append("- none")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _proof_incomplete_reasons(report: dict) -> list[str]:
    errors = report.get("errors", [])
    if not isinstance(errors, list):
        return []

    buckets = {
        "missing_required_proof_file": [],
        "missing_claimed_proof_file": [],
        "proof_count_mismatch": [],
        "invalid_release_gate_json": [],
        "proof_artifacts_incomplete": [],
    }
    for err in errors:
        if not isinstance(err, str):
            continue
        for key in buckets:
            if err.startswith(key + ":") or err == key:
                buckets[key].append(err)

    reasons: list[str] = []
    if buckets["missing_required_proof_file"]:
        reasons.append(
            "missing_required_proof_files="
            + ",".join(sorted(buckets["missing_required_proof_file"]))
        )
    if buckets["missing_claimed_proof_file"]:
        reasons.append(
            "missing_claimed_proof_files="
            + ",".join(sorted(buckets["missing_claimed_proof_file"]))
        )
    if buckets["proof_count_mismatch"]:
        reasons.append(
            "proof_count_mismatch="
            + ",".join(sorted(buckets["proof_count_mismatch"]))
        )
    if buckets["invalid_release_gate_json"]:
        reasons.append("invalid_release_gate_json")
    if buckets["proof_artifacts_incomplete"]:
        reasons.append("proof_artifacts_incomplete")

    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, help="Path to archive zip")
    parser.add_argument("--expected-root", required=True, help="Expected top-level archive root")
    parser.add_argument("--allow-external", action="store_true", help="Allow external/ paths in archive")
    parser.add_argument(
        "--require-release-candidate",
        action="store_true",
        help="Fail validation when release_gate.json is not alpha-passed and release-candidate",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Markdown output path",
    )
    parser.add_argument("--json", action="store_true", help="Also print JSON report")
    args = parser.parse_args()

    archive = Path(args.archive).resolve()
    output = Path(args.output).resolve()

    report = inspect_archive(
        archive,
        expected_root=args.expected_root,
        allow_external=args.allow_external,
        require_release_candidate=args.require_release_candidate,
    )
    write_markdown(report, output)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Archive validation written to {_display_path(output)}")
        print("PASS" if report["valid"] else "FAIL")
        reasons = _proof_incomplete_reasons(report)
        if reasons:
            print(PROOF_INCOMPLETE_PREFIX + "|".join(reasons))

    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
