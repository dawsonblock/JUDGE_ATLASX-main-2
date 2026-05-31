#!/usr/bin/env python3
"""Verify proof_input_tree_hash consistency across canonical proof artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


RELEASE_HASH_RE = re.compile(r"release_gate\.json proof_input_tree_hash=([0-9a-f]{64})")
ACTUAL_HASH_RE = re.compile(r"proof_freshness actual_hash=([0-9a-f]{64})")
GENERIC_HASH_RE = re.compile(r"proof_input_tree_hash=([0-9a-f]{64})")
CURRENT_PROOF_HASH_RE = re.compile(r"- proof_input_tree_hash: ([0-9a-f]{64})")
FRESHNESS_HASH_RE = re.compile(r"proof_input_tree_hash=([0-9a-f]{64})")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_with_fallback(text: str, primary: re.Pattern[str]) -> str:
    match = primary.search(text)
    if match:
        return match.group(1)
    generic = GENERIC_HASH_RE.search(text)
    if generic:
        return generic.group(1)
    return ""


def verify_hash_sync(repo_root: Path) -> tuple[bool, list[str], dict[str, str]]:
    errors: list[str] = []

    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    current_proof_path = repo_root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md"
    proof_freshness_path = repo_root / "artifacts" / "proof" / "current" / "proof_freshness.log"
    archive_validation_path = repo_root / "artifacts" / "proof" / "current" / "archive_validation.log"

    for path in (
        release_gate_path,
        current_proof_path,
        proof_freshness_path,
    ):
        if not path.is_file():
            errors.append(f"missing_file:{path.relative_to(repo_root)}")

    if errors:
        return False, errors, {}

    release_gate = json.loads(_read_text(release_gate_path))
    release_hash = release_gate.get("proof_input_tree_hash", "")
    if not isinstance(release_hash, str):
        release_hash = ""

    current_proof_text = _read_text(current_proof_path)
    proof_freshness_text = _read_text(proof_freshness_path)
    archive_validation_text = ""
    archive_validation_present = archive_validation_path.is_file()
    if archive_validation_present:
        archive_validation_text = _read_text(archive_validation_path)

    current_proof_match = CURRENT_PROOF_HASH_RE.search(current_proof_text)
    freshness_match = FRESHNESS_HASH_RE.search(proof_freshness_text)

    values = {
        "release_gate.json": release_hash,
        "CURRENT_PROOF.md": current_proof_match.group(1) if current_proof_match else "",
        "proof_freshness.log": freshness_match.group(1) if freshness_match else "",
    }

    if archive_validation_present:
        values["archive_validation.log release_hash"] = _extract_with_fallback(
            archive_validation_text, RELEASE_HASH_RE
        )
        values["archive_validation.log actual_hash"] = _extract_with_fallback(
            archive_validation_text, ACTUAL_HASH_RE
        )

    present_values = {name: value for name, value in values.items() if value}

    core_required = (
        "release_gate.json",
        "CURRENT_PROOF.md",
        "proof_freshness.log",
    )
    missing_core = [name for name in core_required if not values.get(name)]
    if missing_core:
        errors.append("missing_hash_values:" + ",".join(missing_core))
        return False, errors, values

    unique = sorted(set(present_values.values()))
    if len(unique) != 1:
        errors.append("hash_mismatch")
        return False, errors, values

    return True, [], values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    ok, errors, values = verify_hash_sync(repo_root)
    if not ok:
        print("PROOF_HASH_SYNC: FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        if values:
            for name, value in values.items():
                print(f"VALUE: {name}={value}")
        return 1

    synchronized_hash = next(iter(values.values()))
    print("PROOF_HASH_SYNC: PASS")
    print(f"proof_input_tree_hash={synchronized_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
