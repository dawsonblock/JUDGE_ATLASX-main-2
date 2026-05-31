#!/usr/bin/env python3
"""Generate FINAL_RELEASE_HANDOFF.md from concrete release artifacts.

This script overwrites the handoff file so release metadata cannot
silently drift from the built archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


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
PROOF_INCOMPLETE_PREFIX = "PROOF_INCOMPLETE:"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object in {path}")
    return data


def _release_classification(release_gate: dict) -> str:
    if bool(release_gate.get("release_candidate", False)):
        return "proof-hardened alpha release candidate"
    if bool(release_gate.get("alpha_gate_passed", False)):
        return "proof-hardened alpha proof snapshot"
    return "proof-blocked alpha proof snapshot"


def _resolve_relative(repo_root: Path, candidate: Path) -> str:
    candidate_resolved = candidate.resolve()
    repo_root_resolved = repo_root.resolve()
    try:
        resolved = candidate_resolved.relative_to(repo_root_resolved)
        return str(resolved).replace("\\", "/")
    except ValueError:
        # Keep absolute path when archive is intentionally outside repo_root.
        return str(candidate_resolved).replace("\\", "/")


def _missing_referenced_logs(repo_root: Path, release_gate: dict) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()

    for entry in release_gate.get("checks", []):
        if not isinstance(entry, dict):
            continue
        log_path = entry.get("log_path")
        if not isinstance(log_path, str) or not log_path:
            continue
        if log_path in seen:
            continue
        seen.add(log_path)
        if not (repo_root / log_path).is_file():
            missing.append(log_path)

    for _name, log_path in release_gate.get("logs", {}).items():
        if not isinstance(log_path, str) or not log_path:
            continue
        if log_path in seen:
            continue
        if not log_path.startswith("artifacts/proof/current/"):
            continue
        seen.add(log_path)
        if not (repo_root / log_path).is_file():
            missing.append(log_path)

    return sorted(missing)


def _missing_required_proof_files(repo_root: Path) -> list[str]:
    return sorted(
        rel_path
        for rel_path in DEFAULT_REQUIRED_PROOF_FILES
        if not (repo_root / rel_path).is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--archive",
        required=True,
        help="Path to release archive (absolute or repo-relative)",
    )
    parser.add_argument(
        "--output",
        default="FINAL_RELEASE_HANDOFF.md",
        help="Handoff markdown path (absolute or repo-relative)",
    )
    parser.add_argument(
        "--allow-blocked-snapshot",
        action="store_true",
        help=(
            "Allow generating handoff when release_candidate is false. "
            "Without this flag, handoff generation requires release_candidate=true."
        ),
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()

    archive_path = Path(args.archive)
    if not archive_path.is_absolute():
        archive_path = (repo_root / archive_path).resolve()
    if not archive_path.exists() or not archive_path.is_file():
        raise SystemExit(f"archive_not_found:{archive_path}")

    release_gate_path = (
        repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    )
    proof_manifest_path = (
        repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json"
    )
    required_log_index_path = (
        repo_root / "artifacts" / "proof" / "current" / "required_log_index.json"
    )
    if not release_gate_path.exists():
        raise SystemExit(f"release_gate_not_found:{release_gate_path}")
    if not proof_manifest_path.exists():
        raise SystemExit(f"proof_manifest_not_found:{proof_manifest_path}")
    if not required_log_index_path.exists():
        raise SystemExit(f"required_log_index_not_found:{required_log_index_path}")

    release_gate = _load_json(release_gate_path)
    _load_json(proof_manifest_path)

    missing_required_proof_files = _missing_required_proof_files(repo_root)
    missing_referenced_logs = _missing_referenced_logs(repo_root, release_gate)
    if missing_required_proof_files or missing_referenced_logs:
        errors: list[str] = []
        if missing_required_proof_files:
            errors.append(
                "missing_required_proof_files="
                + ",".join(missing_required_proof_files)
            )
        if missing_referenced_logs:
            errors.append(
                "missing_referenced_logs=" + ",".join(missing_referenced_logs)
            )
        raise SystemExit(PROOF_INCOMPLETE_PREFIX + "|".join(errors))

    archive_rel = _resolve_relative(repo_root, archive_path)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    archive_hash = _sha256(archive_path)
    release_gate_hash = _sha256(release_gate_path)
    proof_manifest_hash = _sha256(proof_manifest_path)
    required_log_index_hash = _sha256(required_log_index_path)

    alpha_gate_passed = bool(release_gate.get("alpha_gate_passed", False))
    release_candidate = bool(release_gate.get("release_candidate", False))
    production_ready = bool(release_gate.get("production_ready", False))
    proof_complete = bool(release_candidate)
    if not release_candidate and not args.allow_blocked_snapshot:
        raise SystemExit(
            "release_candidate_false: refusing handoff generation without --allow-blocked-snapshot"
        )
    runtime = release_gate.get("runtime", {})
    if not isinstance(runtime, dict):
        runtime = {}
    runtime_python = runtime.get("python", "unknown")
    runtime_node = runtime.get("node_version", "unknown")
    runtime_npm = runtime.get("npm_version", "unknown")
    blockers = release_gate.get("release_blockers_remaining")
    if blockers is None:
        blockers = release_gate.get("blocked_release_checks")
    if blockers is None:
        blocker_text = "none"
    else:
        blocker_text = json.dumps(blockers, ensure_ascii=True)
    release_classification = _release_classification(release_gate)

    generated_at = datetime.now(timezone.utc).isoformat()
    commit = "unknown"

    markdown = "\n".join(
        [
            "# Final Release Handoff",
            "",
            "This document is generated from the built archive and",
            "canonical proof artifacts.",
            "Manual edits are not authoritative.",
            "",
            "## Authoritative Archive",
            f"- Path: {archive_rel}",
            f"- SHA-256: {archive_hash}",
            "",
            "## Proof Anchors",
            "- release_gate_path: artifacts/proof/current/release_gate.json",
            f"- release_gate_sha256: {release_gate_hash}",
            (
                "- proof_manifest_path: "
                "artifacts/proof/current/proof_manifest.json"
            ),
            f"- proof_manifest_sha256: {proof_manifest_hash}",
            (
                "- required_log_index_path: "
                "artifacts/proof/current/required_log_index.json"
            ),
            f"- required_log_index_sha256: {required_log_index_hash}",
            "",
            "## Release Status",
            f"- release_classification: {release_classification}",
            f"- alpha_gate_passed: {str(alpha_gate_passed).lower()}",
            f"- release_candidate: {str(release_candidate).lower()}",
            f"- production_ready: {str(production_ready).lower()}",
            f"- proof_complete: {str(proof_complete).lower()}",
            f"- blocked_release_checks: {blocker_text}",
            "",
            "## Build Metadata",
            f"- created_at_utc: {generated_at}",
            f"- generated_at_utc: {generated_at}",
            f"- git_commit: {commit}",
            (
                f"- python: "
                f"{runtime_python}"
            ),
            (f"- node: {runtime_node}"),
            (f"- npm: {runtime_npm}"),
            "",
            "## Notes",
            f"- This is a {release_classification}.",
            "- It is not ready for production deployment.",
            "- Ship only the archive listed above.",
            "- Validation must run against a fresh extraction",
            "  of that archive.",
            "- `release_gate.json` is only valid as a proof artifact when every",
            "  log path it references exists inside `artifacts/proof/current/`",
            "  at packaging time. Do not ship manually zipped working trees.",
            "",
        ]
    )

    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote handoff: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
