#!/usr/bin/env python3
"""Verify that a release archive is self-consistent and proof-complete.

Given a distributable ZIP produced by ``scripts/build_release_archive.py``,
this script checks:

1. The archive is parseable and contains an embedded ``release_gate.json``.
2. ``alpha_gate_passed`` is ``true`` in that JSON.
3. Every log_path referenced in ``proof_commands[*].log_path`` is present
   inside the ZIP.
4. No forbidden working-tree paths are present in the archive.

Exit codes:
  0 — all checks pass
  1 — one or more checks failed (details printed to stdout)

Usage::

    python3 scripts/verify_archive_proof_freshness.py --archive dist/JUDGE_ATLAS-main-final.zip
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path


FORBIDDEN_PREFIXES = (
    "external_reference/",
    "artifacts/history/",
    ".trunk/",
)
FORBIDDEN_FILE_NAMES = {
    ".coverage",
    ".ds_store",
    "thumbs.db",
}
# Forbidden path prefix variants under any root dir (e.g. JUDGE-main/external_reference/)
FORBIDDEN_INNER_SEGMENTS = (
    "/external_reference/",
    "/artifacts/history/",
    "/.trunk/",
)


def _find_gate_json(zf: zipfile.ZipFile) -> dict | None:
    """Locate release_gate.json inside the ZIP, under any top-level directory."""
    candidates = [
        name for name in zf.namelist()
        if name.endswith("artifacts/proof/current/release_gate.json")
    ]
    if not candidates:
        return None
    with zf.open(candidates[0]) as fh:
        try:
            return json.loads(fh.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None


def _find_member_by_suffix(zf: zipfile.ZipFile, suffix: str) -> str | None:
    candidates = [name for name in zf.namelist() if name.endswith(suffix)]
    if not candidates:
        return None
    return candidates[0]


def _load_json_by_suffix(zf: zipfile.ZipFile, suffix: str) -> dict | None:
    member = _find_member_by_suffix(zf, suffix)
    if member is None:
        return None
    with zf.open(member) as fh:
        try:
            payload = json.loads(fh.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    if not isinstance(payload, dict):
        return None
    return payload


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


def _resolve_member_for_rel_path(names: list[str], rel_path: str) -> str | None:
    for name in names:
        if name == rel_path or name.endswith("/" + rel_path):
            return name
    return None


def _referenced_log_paths(
    release_gate: dict,
    proof_manifest: dict | None,
    required_log_index: dict | None,
) -> set[str]:
    refs: set[str] = set()

    checks = release_gate.get("checks", [])
    if isinstance(checks, list):
        for entry in checks:
            if not isinstance(entry, dict):
                continue
            rel = entry.get("log_path")
            if isinstance(rel, str) and rel.startswith("artifacts/proof/current/"):
                refs.add(rel)

    if isinstance(proof_manifest, dict):
        for rel in proof_manifest.get("required_logs", []):
            if isinstance(rel, str) and rel.startswith("artifacts/proof/current/"):
                refs.add(rel)

    if isinstance(required_log_index, dict):
        entries = required_log_index.get("entries", [])
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                rel = entry.get("path")
                if isinstance(rel, str) and rel.startswith("artifacts/proof/current/"):
                    refs.add(rel)

    return refs


def verify_archive(archive_path: Path) -> list[str]:
    """Run all checks against a release archive ZIP.

    Returns:
        List of human-readable failure strings.  Empty list means all PASS.
    """
    failures: list[str] = []

    if not archive_path.exists():
        return [f"archive not found: {archive_path}"]

    try:
        zf = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile as exc:
        return [f"archive is not a valid ZIP: {exc}"]

    with zf:
        names = zf.namelist()
        names_set = set(names)

        # 1. Locate and parse embedded release_gate.json
        payload = _find_gate_json(zf)
        if payload is None:
            failures.append(
                "release_gate.json not found in archive (expected at "
                "<root>/artifacts/proof/current/release_gate.json)"
            )
        else:
            manifest = _load_json_by_suffix(
                zf,
                "artifacts/proof/current/proof_manifest.json",
            )
            required_log_index = _load_json_by_suffix(
                zf,
                "artifacts/proof/current/required_log_index.json",
            )

            if manifest is None:
                failures.append("proof_manifest.json not found or invalid in archive")
            if required_log_index is None:
                failures.append("required_log_index.json not found or invalid in archive")

            # 2. alpha_gate_passed must be true
            if not payload.get("alpha_gate_passed"):
                failures.append(
                    f"alpha_gate_passed is not true in release_gate.json "
                    f"(got: {payload.get('alpha_gate_passed')!r})"
                )

            if isinstance(manifest, dict):
                gate_commit = payload.get("commit_hash")
                manifest_commit = manifest.get("archive_hash")
                if (
                    isinstance(gate_commit, str)
                    and isinstance(manifest_commit, str)
                    and gate_commit
                    and manifest_commit
                    and gate_commit != manifest_commit
                ):
                    failures.append(
                        "commit hash mismatch between release_gate.json and proof_manifest.json"
                    )

                gate_input_hash = payload.get("proof_input_tree_hash")
                manifest_input_hash = manifest.get("proof_input_tree_hash")
                if (
                    isinstance(gate_input_hash, str)
                    and isinstance(manifest_input_hash, str)
                    and gate_input_hash
                    and manifest_input_hash
                    and gate_input_hash != manifest_input_hash
                ):
                    failures.append(
                        "proof input tree hash mismatch between release_gate.json and proof_manifest.json"
                    )

                gate_python = payload.get("python_version")
                manifest_python = manifest.get("python_version")
                if gate_python != manifest_python:
                    failures.append(
                        "python version mismatch between release_gate.json and proof_manifest.json"
                    )

                gate_node = payload.get("gate_runner_node_version") or payload.get("node_version")
                manifest_node = manifest.get("gate_runner_node_version") or manifest.get("node_version")
                if gate_node != manifest_node:
                    failures.append(
                        "node version mismatch between release_gate.json and proof_manifest.json"
                    )

                gate_time = _parse_iso8601(payload.get("generated_at") or payload.get("timestamp_utc"))
                manifest_time = _parse_iso8601(manifest.get("generated_at"))
                if gate_time is None or manifest_time is None:
                    failures.append(
                        "missing or invalid proof timestamp in release_gate.json/proof_manifest.json"
                    )
                else:
                    drift_seconds = abs((gate_time - manifest_time).total_seconds())
                    if drift_seconds > 1.0:
                        failures.append(
                            "proof timestamp mismatch between release_gate.json and proof_manifest.json"
                        )

            # 3. Every referenced log_path must exist in the archive
            missing_logs: list[str] = []
            empty_logs: list[str] = []
            for log_path in sorted(
                _referenced_log_paths(payload, manifest, required_log_index)
            ):
                member_name = _resolve_member_for_rel_path(names, log_path)
                if member_name is None:
                    missing_logs.append(log_path)
                    continue
                info = zf.getinfo(member_name)
                if info.file_size <= 0:
                    empty_logs.append(log_path)
            if missing_logs:
                failures.append(
                    f"{len(missing_logs)} proof log(s) referenced in "
                    f"release_gate/proof_manifest/required_log_index are absent from the archive:"
                )
                for p in sorted(missing_logs):
                    failures.append(f"  missing: {p}")
            if empty_logs:
                failures.append(
                    f"{len(empty_logs)} referenced proof log(s) are empty in the archive:"
                )
                for p in sorted(empty_logs):
                    failures.append(f"  empty: {p}")

        # 4. Forbidden working-tree paths must be absent
        for name in names:
            # Strip the root dir prefix (first segment) for prefix matching
            parts = name.split("/", 1)
            inner = parts[1] if len(parts) > 1 else name

            if any(inner.startswith(fp) for fp in FORBIDDEN_PREFIXES):
                failures.append(f"forbidden path in archive: {name}")
                continue

            file_name = Path(name).name.lower()
            if file_name in FORBIDDEN_FILE_NAMES:
                failures.append(f"forbidden file in archive: {name}")
                continue

            for seg in FORBIDDEN_INNER_SEGMENTS:
                if seg in ("/" + name + "/") or ("/" + inner).startswith(seg):
                    failures.append(f"forbidden segment in archive: {name}")
                    break

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        required=True,
        help="Path to the release ZIP archive to verify",
    )
    args = parser.parse_args()

    archive_path = Path(args.archive).resolve()
    print(f"Verifying archive: {archive_path}")

    failures = verify_archive(archive_path)

    if failures:
        print(f"ARCHIVE_PROOF_FRESHNESS: FAIL ({len(failures)} issue(s))")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("ARCHIVE_PROOF_FRESHNESS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
