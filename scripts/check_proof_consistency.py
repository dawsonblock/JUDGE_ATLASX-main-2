#!/usr/bin/env python3
"""Check consistency between release_gate, proof_manifest, and required_log_index artifacts."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path


PROOF_INCOMPLETE_PREFIX = "PROOF_INCOMPLETE:"


def load_json_file(path: Path) -> dict:
    """Load and parse a JSON file."""
    if not path.exists():
        raise RuntimeError(f"Proof artifact not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return data


def load_text_file(path: Path) -> str:
    """Load a UTF-8 text file with a structured missing-artifact error."""
    if not path.exists():
        raise RuntimeError(f"Proof artifact not found: {path}")
    return path.read_text(encoding="utf-8")


def _parse_version(version: str) -> tuple[int, int, int] | None:
    if not isinstance(version, str):
        return None
    match = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    )


def _compare_versions(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _satisfies_range(version: str, spec: str) -> bool:
    parsed_version = _parse_version(version)
    if parsed_version is None:
        return False

    comparators = [token for token in spec.split() if token]
    for comparator in comparators:
        if comparator.startswith(">="):
            target = _parse_version(comparator[2:])
            if target is None or _compare_versions(parsed_version, target) < 0:
                return False
        elif comparator.startswith(">"):
            target = _parse_version(comparator[1:])
            if target is None or _compare_versions(parsed_version, target) <= 0:
                return False
        elif comparator.startswith("<="):
            target = _parse_version(comparator[2:])
            if target is None or _compare_versions(parsed_version, target) > 0:
                return False
        elif comparator.startswith("<"):
            target = _parse_version(comparator[1:])
            if target is None or _compare_versions(parsed_version, target) >= 0:
                return False
        else:
            target = _parse_version(comparator)
            if target is None or parsed_version != target:
                return False
    return True


def _policy_major(value: str | None) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = _parse_version(value.strip())
    if parsed is None:
        return None
    return parsed[0]


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_sha256(path: Path) -> tuple[str | None, str | None]:
    try:
        return _sha256(path), None
    except OSError as exc:
        return None, str(exc)


def _safe_size(path: Path) -> tuple[int | None, str | None]:
    try:
        return path.stat().st_size, None
    except OSError as exc:
        return None, str(exc)


def _entry_path(entry: dict) -> str | None:
    path = entry.get("path")
    if isinstance(path, str) and path:
        return path
    log_path = entry.get("log_path")
    if isinstance(log_path, str) and log_path:
        return log_path
    return None


def _manifest_entry_map(manifest: dict) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    proof_commands = manifest.get("proof_commands")
    if not isinstance(proof_commands, list):
        return mapping
    for entry in proof_commands:
        if not isinstance(entry, dict):
            continue
        path = _entry_path(entry)
        if path:
            mapping[path] = entry
    return mapping


def _parse_iso8601(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _check_file_and_manifest_entry(
    *,
    repo_root: Path,
    rel_path: str,
    manifest_map: dict[str, dict],
    errors: list[str],
    required: bool,
) -> None:
    abs_path = repo_root / rel_path
    if not abs_path.is_file():
        errors.append(f"missing_file:{rel_path}")
        return

    if rel_path.endswith(".log"):
        actual_size, size_error = _safe_size(abs_path)
        if size_error is not None or actual_size is None:
            errors.append(f"unreadable_file_size:{rel_path}:{size_error}")
            return
        if actual_size <= 0:
            errors.append(f"empty_log:{rel_path}")
            return

    entry = manifest_map.get(rel_path)
    if entry is None:
        if required:
            errors.append(f"missing_manifest_entry:{rel_path}")
        return

    expected_size = entry.get("size_bytes")
    if isinstance(expected_size, int):
        actual_size, size_error = _safe_size(abs_path)
        if size_error is not None or actual_size is None:
            errors.append(f"unreadable_file_size:{rel_path}:{size_error}")
            return
        if actual_size != expected_size:
            errors.append(
                f"size_mismatch:{rel_path}:expected={expected_size}:actual={actual_size}"
            )

    expected_hash = entry.get("sha256") or entry.get("log_sha256")
    if required and (not isinstance(expected_hash, str) or not expected_hash):
        errors.append(f"missing_hash:{rel_path}")
        return

    if isinstance(expected_hash, str) and expected_hash:
        actual_hash, hash_error = _safe_sha256(abs_path)
        if hash_error is not None or actual_hash is None:
            errors.append(f"unreadable_file_hash:{rel_path}:{hash_error}")
            return
        if actual_hash != expected_hash:
            errors.append(
                f"hash_mismatch:{rel_path}:expected={expected_hash}:actual={actual_hash}"
            )


def _collect_referenced_paths(release_gate: dict) -> tuple[set[str], set[str]]:
    required_paths: set[str] = set()
    optional_paths: set[str] = set()

    checks = release_gate.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            path = check.get("log_path")
            if not isinstance(path, str) or not path:
                continue
            if not path.startswith("artifacts/proof/current/"):
                continue
            if bool(check.get("required", True)):
                required_paths.add(path)
            else:
                optional_paths.add(path)

    logs = release_gate.get("logs", {})
    if isinstance(logs, dict):
        for path in logs.values():
            if not isinstance(path, str) or not path:
                continue
            if not path.startswith("artifacts/proof/current/"):
                continue
            optional_paths.add(path)

    optional_paths -= required_paths
    return required_paths, optional_paths


def check_node_version_consistency(manifest: dict, gate: dict) -> list[str]:
    errors = []

    manifest_node = manifest.get("gate_runner_node_version") or manifest.get("node_version")
    gate_node = gate.get("gate_runner_node_version") or gate.get("node_version")

    if manifest_node != gate_node:
        errors.append(
            f"node_version_mismatch:proof_manifest={manifest_node}:release_gate={gate_node}"
        )

    manifest_frontend = manifest.get("frontend_node_gate_version")
    gate_frontend = gate.get("frontend_node_gate_version")

    if (
        manifest_frontend is not None
        and gate_frontend is not None
        and manifest_frontend != gate_frontend
    ):
        errors.append(
            "frontend_node_version_mismatch:"
            f"proof_manifest={manifest_frontend}:release_gate={gate_frontend}"
        )

    return errors


def check_python_version_consistency(manifest: dict, gate: dict) -> list[str]:
    errors = []
    manifest_python = manifest.get("python_version")
    gate_python = gate.get("python_version")
    if manifest_python != gate_python:
        errors.append(
            f"python_version_mismatch:proof_manifest={manifest_python}:release_gate={gate_python}"
        )
    return errors


def check_platform_consistency(manifest: dict, gate: dict) -> list[str]:
    errors = []
    manifest_platform = manifest.get("platform")
    gate_platform = gate.get("platform")
    if manifest_platform != gate_platform:
        errors.append(
            f"platform_mismatch:proof_manifest={manifest_platform}:release_gate={gate_platform}"
        )
    return errors


def check_commit_hash_consistency(manifest: dict, gate: dict) -> list[str]:
    errors = []
    manifest_hash = manifest.get("archive_hash")
    gate_hash = gate.get("commit_hash")
    if manifest_hash and gate_hash and manifest_hash != gate_hash:
        errors.append(
            f"commit_hash_mismatch:proof_manifest={manifest_hash}:release_gate={gate_hash}"
        )
    return errors


def check_proof_input_consistency(manifest: dict, gate: dict) -> list[str]:
    errors = []

    manifest_hash = manifest.get("proof_input_tree_hash")
    gate_hash = gate.get("proof_input_tree_hash")
    if gate_hash and not manifest_hash:
        errors.append("missing_proof_input_hash_in_manifest")
    if manifest_hash and gate_hash and manifest_hash != gate_hash:
        errors.append(
            f"proof_input_hash_mismatch:proof_manifest={manifest_hash}:release_gate={gate_hash}"
        )

    manifest_count = manifest.get("proof_input_file_count")
    gate_count = gate.get("proof_input_file_count")
    if gate_count is not None and manifest_count is None:
        errors.append("missing_proof_input_file_count_in_manifest")
    if (
        manifest_count is not None
        and gate_count is not None
        and manifest_count != gate_count
    ):
        errors.append(
            "proof_input_count_mismatch:"
            f"proof_manifest={manifest_count}:release_gate={gate_count}"
        )

    return errors


def check_proof_timestamp_consistency(manifest: dict, gate: dict) -> list[str]:
    errors: list[str] = []

    manifest_time = _parse_iso8601(manifest.get("generated_at"))
    gate_time = _parse_iso8601(gate.get("generated_at") or gate.get("timestamp_utc"))

    if manifest_time is None:
        errors.append("missing_or_invalid_proof_manifest_generated_at")
    if gate_time is None:
        errors.append("missing_or_invalid_release_gate_generated_at")
    if manifest_time is None or gate_time is None:
        return errors

    drift_seconds = abs((manifest_time - gate_time).total_seconds())
    if drift_seconds > 1.0:
        errors.append(
            "proof_timestamp_mismatch:"
            f"proof_manifest={manifest.get('generated_at')}:"
            f"release_gate={gate.get('generated_at') or gate.get('timestamp_utc')}:"
            f"drift_seconds={drift_seconds:.3f}"
        )

    return errors


def _extract_markdown_scalar(text: str, key: str) -> str | None:
    pattern = rf"(?m)^-\s+{re.escape(key)}:\s*(.+?)\s*$"
    match = re.search(pattern, text)
    if not match:
        return None
    return match.group(1).strip()


def _extract_markdown_bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    header = heading.strip().lower()
    in_section = False
    bullets: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line.lower() == f"## {header}"
            continue
        if not in_section:
            continue
        if line.startswith("### "):
            break
        if line.startswith("- "):
            value = line[2:].strip()
            if value:
                bullets.append(value)

    return bullets


def _normalize_readiness_blocker(blocker: str) -> str | None:
    blocker = blocker.strip()
    if not blocker:
        return None
    if blocker.lower() == "none":
        return None
    if blocker.startswith("required_gate_failed:"):
        return blocker.split(":", 1)[1].strip() or None
    if blocker.startswith("missing_required_gate:"):
        return blocker.split(":", 1)[1].strip() or None
    if blocker.endswith("_not_pass"):
        return None
    return blocker


def check_hash_sync_across_all_sources(
    manifest: dict,
    gate: dict,
    current_proof_text: str,
) -> list[str]:
    errors: list[str] = []
    manifest_hash = manifest.get("proof_input_tree_hash")
    gate_hash = gate.get("proof_input_tree_hash")
    current_proof_hash = _extract_markdown_scalar(
        current_proof_text,
        "proof_input_tree_hash",
    )

    if gate_hash and not current_proof_hash:
        errors.append("current_proof_missing_proof_input_tree_hash")

    hash_sources = {
        "proof_manifest": manifest_hash,
        "release_gate": gate_hash,
        "current_proof": current_proof_hash,
    }
    present = {
        key: value
        for key, value in hash_sources.items()
        if isinstance(value, str) and value
    }
    if len(set(present.values())) > 1:
        errors.append(
            "proof_input_hash_mismatch_across_sources:" + json.dumps(present, sort_keys=True)
        )
    return errors


def check_readiness_vs_release_gate_consistency(
    gate: dict,
    release_readiness_text: str,
) -> list[str]:
    errors: list[str] = []

    readiness_status = _extract_markdown_scalar(release_readiness_text, "overall_status")
    if isinstance(readiness_status, str):
        gate_passed = bool(gate.get("alpha_gate_passed", False))
        normalized = readiness_status.strip().lower()
        if gate_passed and normalized == "blocked":
            errors.append("release_readiness_status_mismatch:gate_passed_but_readiness_blocked")
        if (not gate_passed) and normalized == "alpha-proof-pass":
            errors.append("release_readiness_status_mismatch:gate_blocked_but_readiness_pass")

    gate_blockers = gate.get("release_blockers_remaining", [])
    gate_blocker_set = (
        {item for item in gate_blockers if isinstance(item, str) and item}
        if isinstance(gate_blockers, list)
        else set()
    )
    readiness_blocker_set = set(
        _extract_markdown_bullets(release_readiness_text, "Remaining Blockers")
    )
    normalized_readiness_blockers: set[str] = set()
    for blocker in readiness_blocker_set:
        normalized_blocker = _normalize_readiness_blocker(blocker)
        if normalized_blocker:
            normalized_readiness_blockers.add(normalized_blocker)

    if gate_blocker_set != normalized_readiness_blockers:
        errors.append(
            "release_readiness_blockers_mismatch:"
            f"release_gate={sorted(gate_blocker_set)}:"
            f"release_readiness={sorted(readiness_blocker_set)}"
        )

    return errors


def check_required_index_consistency(
    *,
    repo_root: Path,
    required_log_index: dict,
    manifest_map: dict[str, dict],
) -> list[str]:
    errors: list[str] = []

    entries = required_log_index.get("entries")
    if not isinstance(entries, list):
        return ["required_log_index_entries_missing_or_invalid"]

    computed_missing: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("required_log_index_invalid_entry")
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            errors.append("required_log_index_entry_missing_path")
            continue

        exists = bool(entry.get("exists", False))
        abs_path = repo_root / path
        if exists and not abs_path.is_file():
            errors.append(f"required_log_index_exists_but_missing_on_disk:{path}")
        if not exists:
            computed_missing.append(path)
            if abs_path.is_file():
                errors.append(f"required_log_index_marked_missing_but_present:{path}")
            continue

        manifest_entry = manifest_map.get(path)
        if manifest_entry is None:
            errors.append(f"required_log_index_missing_manifest_entry:{path}")
            continue

        recorded_sha = entry.get("recorded_sha256")
        actual_sha, hash_error = _safe_sha256(abs_path)
        if hash_error is not None or actual_sha is None:
            errors.append(f"required_log_index_unreadable_file_hash:{path}:{hash_error}")
            continue
        if isinstance(recorded_sha, str) and recorded_sha and recorded_sha != actual_sha:
            errors.append(f"required_log_index_recorded_sha_mismatch:{path}")

        manifest_sha = manifest_entry.get("sha256") or manifest_entry.get("log_sha256")
        if isinstance(manifest_sha, str) and manifest_sha and manifest_sha != actual_sha:
            errors.append(f"required_log_index_manifest_sha_mismatch:{path}")

        recorded_size = entry.get("recorded_size_bytes")
        actual_size, size_error = _safe_size(abs_path)
        if size_error is not None or actual_size is None:
            errors.append(f"required_log_index_unreadable_file_size:{path}:{size_error}")
            continue
        if actual_size <= 0:
            errors.append(f"required_log_index_empty_log:{path}")
            continue
        if isinstance(recorded_size, int) and recorded_size != actual_size:
            errors.append(f"required_log_index_recorded_size_mismatch:{path}")

        manifest_size = manifest_entry.get("size_bytes")
        if isinstance(manifest_size, int) and manifest_size != actual_size:
            errors.append(f"required_log_index_manifest_size_mismatch:{path}")

    listed_missing = required_log_index.get("missing_required_logs", [])
    if isinstance(listed_missing, list):
        listed_missing_sorted = sorted([item for item in listed_missing if isinstance(item, str)])
        if sorted(computed_missing) != listed_missing_sorted:
            errors.append(
                "required_log_index_missing_required_logs_mismatch:"
                f"computed={sorted(computed_missing)}:listed={listed_missing_sorted}"
            )
    else:
        errors.append("required_log_index_missing_required_logs_invalid")

    return errors


def check_release_gate_proof_integrity(
    *,
    repo_root: Path,
    release_gate: dict,
    manifest: dict,
    required_log_index: dict,
    packaged_archive: bool = False,
) -> list[str]:
    errors: list[str] = []
    manifest_map = _manifest_entry_map(manifest)

    required_paths, optional_paths = _collect_referenced_paths(release_gate)

    for rel_path in sorted(required_paths):
        _check_file_and_manifest_entry(
            repo_root=repo_root,
            rel_path=rel_path,
            manifest_map=manifest_map,
            errors=errors,
            required=True,
        )

    for rel_path in sorted(optional_paths):
        _check_file_and_manifest_entry(
            repo_root=repo_root,
            rel_path=rel_path,
            manifest_map=manifest_map,
            errors=errors,
            required=False,
        )

    required_logs = manifest.get("required_logs", [])
    if isinstance(required_logs, list):
        for rel_path in required_logs:
            if isinstance(rel_path, str) and rel_path:
                _check_file_and_manifest_entry(
                    repo_root=repo_root,
                    rel_path=rel_path,
                    manifest_map=manifest_map,
                    errors=errors,
                    required=True,
                )
    else:
        errors.append("proof_manifest_required_logs_missing_or_invalid")

    errors.extend(
        check_required_index_consistency(
            repo_root=repo_root,
            required_log_index=required_log_index,
            manifest_map=manifest_map,
        )
    )

    alpha_gate_passed = bool(release_gate.get("alpha_gate_passed", False))
    archive_validation = None
    checks = release_gate.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and check.get("name") == "archive_validation":
                archive_validation = str(check.get("status", "")).upper()
                break

    missing_required_logs = required_log_index.get("missing_required_logs", [])
    if not isinstance(missing_required_logs, list):
        missing_required_logs = ["invalid_required_log_index_missing_required_logs"]

    if alpha_gate_passed:
        if missing_required_logs:
            errors.append("alpha_gate_passed_with_missing_required_logs")

        if not packaged_archive and archive_validation != "PASS":
            errors.append("alpha_gate_passed_without_archive_validation_pass")

        for rel_path in manifest.get("required_logs", []):
            if not isinstance(rel_path, str) or not rel_path:
                errors.append("alpha_gate_passed_with_invalid_required_log_entry")
                continue
            entry = manifest_map.get(rel_path)
            if entry is None:
                errors.append(f"alpha_gate_passed_missing_manifest_entry:{rel_path}")
                continue
            if not entry.get("sha256") and not entry.get("log_sha256"):
                errors.append(f"alpha_gate_passed_missing_hash:{rel_path}")
            if not (repo_root / rel_path).is_file():
                errors.append(f"alpha_gate_passed_missing_file:{rel_path}")

    return errors


def check_node_policy_alignment(repo_root: Path, manifest: dict, gate: dict) -> list[str]:
    errors = []

    package_json = load_json_file(repo_root / "frontend" / "package.json")
    node_range = package_json.get("engines", {}).get("node")
    root_nvmrc = repo_root / ".nvmrc"
    frontend_nvmrc = repo_root / "frontend" / ".nvmrc"
    root_major = root_nvmrc.read_text(encoding="utf-8").strip() if root_nvmrc.exists() else None
    frontend_major = (
        frontend_nvmrc.read_text(encoding="utf-8").strip() if frontend_nvmrc.exists() else None
    )

    policy_selector = root_major or frontend_major
    policy_major = _policy_major(policy_selector)
    if root_major is not None and frontend_major is not None and root_major != frontend_major:
        errors.append(f"nvmrc_mismatch:root={root_major}:frontend={frontend_major}")
    elif policy_selector is None:
        errors.append("missing_nvmrc_policy_files")
    elif policy_major is None:
        errors.append(f"invalid_nvmrc_value:{policy_selector}")

    gate_node = gate.get("frontend_node_gate_version") or gate.get("node_version")
    manifest_node = manifest.get("frontend_node_gate_version") or manifest.get("node_version")

    for label, version in (("proof_manifest.json", manifest_node), ("release_gate.json", gate_node)):
        if not isinstance(version, str):
            errors.append(f"missing_node_version_for_policy_check:{label}")
            continue
        parsed = _parse_version(version)
        if parsed is None:
            errors.append(f"unparsable_node_version:{label}:{version}")
            continue
        if policy_major is not None and parsed[0] != policy_major:
            errors.append(f"node_major_policy_mismatch:{label}:{version}:required={policy_major}")
        if not isinstance(node_range, str) or not _satisfies_range(version, node_range):
            errors.append(f"node_engines_policy_mismatch:{label}:{version}:engines={node_range}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root",
    )
    parser.add_argument(
        "--packaged-archive",
        action="store_true",
        help=(
            "Relax consistency checks for extracted packaged archives where "
            "archive_validation is not re-run inside the extracted tree."
        ),
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    proof_dir = repo_root / "artifacts" / "proof" / "current"

    manifest_path = proof_dir / "proof_manifest.json"
    gate_path = proof_dir / "release_gate.json"
    required_log_index_path = proof_dir / "required_log_index.json"
    current_proof_path = proof_dir / "CURRENT_PROOF.md"
    release_readiness_path = proof_dir / "release_readiness.md"

    print("Checking proof artifact consistency...")
    print(f"  proof_manifest.json: {manifest_path}")
    print(f"  release_gate.json: {gate_path}")
    print(f"  required_log_index.json: {required_log_index_path}")
    print(f"  CURRENT_PROOF.md: {current_proof_path}")
    print(f"  release_readiness.md: {release_readiness_path}")

    all_errors: list[str] = []

    json_artifacts = [manifest_path, gate_path, required_log_index_path]
    text_artifacts = [current_proof_path, release_readiness_path]

    missing_json_artifacts = [
        str(path.relative_to(repo_root))
        for path in json_artifacts
        if not path.exists()
    ]
    missing_text_artifacts = [
        str(path.relative_to(repo_root))
        for path in text_artifacts
        if not path.exists()
    ]
    if missing_json_artifacts or missing_text_artifacts:
        parts: list[str] = []
        if missing_json_artifacts:
            parts.append(
                "missing_json_artifacts="
                + ",".join(sorted(missing_json_artifacts))
            )
        if missing_text_artifacts:
            parts.append(
                "missing_text_artifacts="
                + ",".join(sorted(missing_text_artifacts))
            )
        print(PROOF_INCOMPLETE_PREFIX + "|".join(parts))
        return 1

    json_load_errors: list[str] = []
    text_load_errors: list[str] = []

    try:
        manifest = load_json_file(manifest_path)
    except RuntimeError as exc:
        json_load_errors.append(f"{manifest_path.relative_to(repo_root)}:{exc}")
        manifest = {}
    try:
        gate = load_json_file(gate_path)
    except RuntimeError as exc:
        json_load_errors.append(f"{gate_path.relative_to(repo_root)}:{exc}")
        gate = {}
    try:
        required_log_index = load_json_file(required_log_index_path)
    except RuntimeError as exc:
        json_load_errors.append(
            f"{required_log_index_path.relative_to(repo_root)}:{exc}"
        )
        required_log_index = {}
    try:
        current_proof_text = load_text_file(current_proof_path)
    except RuntimeError as exc:
        text_load_errors.append(f"{current_proof_path.relative_to(repo_root)}:{exc}")
        current_proof_text = ""
    try:
        release_readiness_text = load_text_file(release_readiness_path)
    except RuntimeError as exc:
        text_load_errors.append(
            f"{release_readiness_path.relative_to(repo_root)}:{exc}"
        )
        release_readiness_text = ""

    if json_load_errors or text_load_errors:
        for error in json_load_errors + text_load_errors:
            print(f"ERROR: {error}")
        parts = []
        if json_load_errors:
            parts.append(
                "invalid_json_artifacts="
                + ",".join(
                    sorted(
                        {
                            item.split(":", 1)[0]
                            for item in json_load_errors
                            if ":" in item
                        }
                    )
                )
            )
        if text_load_errors:
            parts.append(
                "unreadable_text_artifacts="
                + ",".join(
                    sorted(
                        {
                            item.split(":", 1)[0]
                            for item in text_load_errors
                            if ":" in item
                        }
                    )
                )
            )
        print(PROOF_INCOMPLETE_PREFIX + "|".join(parts))
        return 1

    all_errors.extend(check_node_version_consistency(manifest, gate))
    all_errors.extend(check_python_version_consistency(manifest, gate))
    all_errors.extend(check_platform_consistency(manifest, gate))
    all_errors.extend(check_commit_hash_consistency(manifest, gate))
    all_errors.extend(check_proof_input_consistency(manifest, gate))
    all_errors.extend(check_proof_timestamp_consistency(manifest, gate))
    try:
        all_errors.extend(check_node_policy_alignment(repo_root, manifest, gate))
    except RuntimeError as exc:
        all_errors.append(f"node_policy_alignment_error:{exc}")
    all_errors.extend(
        check_release_gate_proof_integrity(
            repo_root=repo_root,
            release_gate=gate,
            manifest=manifest,
            required_log_index=required_log_index,
            packaged_archive=bool(args.packaged_archive),
        )
    )
    all_errors.extend(
        check_hash_sync_across_all_sources(
            manifest,
            gate,
            current_proof_text,
        )
    )
    all_errors.extend(
        check_readiness_vs_release_gate_consistency(
            gate,
            release_readiness_text,
        )
    )

    if all_errors:
        print("\nProof artifact consistency check FAILED")
        print("\nErrors found:")
        for error in sorted(set(all_errors)):
            print(f"  - {error}")
        return 1

    print("\nProof artifact consistency check PASSED")
    print("All proof artifacts are consistent with each other.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
