#!/usr/bin/env python3
"""Validate FINAL_RELEASE_HANDOFF claims against the actual release archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re

PATH_PATTERN = re.compile(r"^\s*-\s*Path:\s*(.+?)\s*$", re.IGNORECASE)
SHA_PATTERN = re.compile(
    r"^\s*-\s*SHA-256:\s*([0-9a-fA-F]{64})\s*$",
    re.IGNORECASE,
)
BOOLEAN_FIELD_PATTERNS = {
    "alpha_gate_passed": re.compile(r"^\s*-\s*alpha_gate_passed:\s*(true|false)\s*$", re.IGNORECASE),
    "release_candidate": re.compile(r"^\s*-\s*release_candidate:\s*(true|false)\s*$", re.IGNORECASE),
    "production_ready": re.compile(r"^\s*-\s*production_ready:\s*(true|false)\s*$", re.IGNORECASE),
}
CLASSIFICATION_PATTERN = re.compile(
    r"^\s*-\s*release_classification:\s*(.+?)\s*$",
    re.IGNORECASE,
)
PROOF_ANCHOR_PATH_PATTERNS = {
    "release_gate_path": re.compile(
        r"^\s*-\s*release_gate_path:\s*(.+?)\s*$", re.IGNORECASE
    ),
    "proof_manifest_path": re.compile(
        r"^\s*-\s*proof_manifest_path:\s*(.+?)\s*$", re.IGNORECASE
    ),
    "required_log_index_path": re.compile(
        r"^\s*-\s*required_log_index_path:\s*(.+?)\s*$", re.IGNORECASE
    ),
}
PROOF_ANCHOR_SHA_PATTERNS = {
    "release_gate_sha256": re.compile(
        r"^\s*-\s*release_gate_sha256:\s*([0-9a-fA-F]{64})\s*$",
        re.IGNORECASE,
    ),
    "proof_manifest_sha256": re.compile(
        r"^\s*-\s*proof_manifest_sha256:\s*([0-9a-fA-F]{64})\s*$",
        re.IGNORECASE,
    ),
    "required_log_index_sha256": re.compile(
        r"^\s*-\s*required_log_index_sha256:\s*([0-9a-fA-F]{64})\s*$",
        re.IGNORECASE,
    ),
}


def _compute_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_claims(
    handoff_path: pathlib.Path,
) -> tuple[
    str | None,
    str | None,
    dict[str, bool],
    str | None,
    dict[str, str],
    dict[str, str],
    str,
]:
    claimed_path: str | None = None
    claimed_sha: str | None = None
    boolean_claims: dict[str, bool] = {}
    classification: str | None = None
    anchor_paths: dict[str, str] = {}
    anchor_shas: dict[str, str] = {}
    content = handoff_path.read_text(encoding="utf-8", errors="ignore")
    for line in content.splitlines():
        if claimed_path is None:
            match = PATH_PATTERN.match(line)
            if match:
                claimed_path = match.group(1).strip()
        if claimed_sha is None:
            match = SHA_PATTERN.match(line)
            if match:
                claimed_sha = match.group(1).lower()
        if classification is None:
            match = CLASSIFICATION_PATTERN.match(line)
            if match:
                classification = match.group(1).strip()
        for key, pattern in BOOLEAN_FIELD_PATTERNS.items():
            if key in boolean_claims:
                continue
            match = pattern.match(line)
            if match:
                boolean_claims[key] = match.group(1).lower() == "true"
        for key, pattern in PROOF_ANCHOR_PATH_PATTERNS.items():
            if key in anchor_paths:
                continue
            match = pattern.match(line)
            if match:
                anchor_paths[key] = match.group(1).strip()
        for key, pattern in PROOF_ANCHOR_SHA_PATTERNS.items():
            if key in anchor_shas:
                continue
            match = pattern.match(line)
            if match:
                anchor_shas[key] = match.group(1).lower()
    return (
        claimed_path,
        claimed_sha,
        boolean_claims,
        classification,
        anchor_paths,
        anchor_shas,
        content,
    )


def _expected_release_classification(release_gate: dict) -> str:
    if bool(release_gate.get("release_candidate", False)):
        return "proof-hardened alpha release candidate"
    if bool(release_gate.get("alpha_gate_passed", False)):
        return "proof-hardened alpha proof snapshot"
    return "proof-blocked alpha proof snapshot"


def validate_handoff(
    repo_root: pathlib.Path,
    archive_path: pathlib.Path,
    handoff_path: pathlib.Path,
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if not handoff_path.exists() or not handoff_path.is_file():
        errors.append(f"handoff_not_found:{handoff_path}")
        return False, errors

    if not archive_path.exists() or not archive_path.is_file():
        errors.append(f"archive_not_found:{archive_path}")
        return False, errors

    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    release_gate: dict | None = None
    if release_gate_path.exists() and release_gate_path.is_file():
        try:
            release_gate = json.loads(release_gate_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"release_gate_parse_error:{release_gate_path}")

    (
        claimed_path,
        claimed_sha,
        boolean_claims,
        classification,
        anchor_paths,
        anchor_shas,
        handoff_text,
    ) = _extract_claims(handoff_path)
    if not claimed_path:
        errors.append("missing_claimed_path")
    if not claimed_sha:
        errors.append("missing_claimed_sha256")

    actual_sha = _compute_sha256(archive_path)

    if claimed_sha and claimed_sha != actual_sha:
        errors.append(
            f"sha256_mismatch:claimed={claimed_sha}:actual={actual_sha}"
        )

    if claimed_path:
        claimed_archive = pathlib.Path(claimed_path)
        if not claimed_archive.is_absolute():
            claimed_archive = (repo_root / claimed_archive).resolve()
        else:
            claimed_archive = claimed_archive.resolve()

        if claimed_archive != archive_path.resolve():
            errors.append(
                "archive_path_mismatch:"
                f"claimed={claimed_archive}:actual={archive_path.resolve()}"
            )

        if not claimed_archive.exists() or not claimed_archive.is_file():
            errors.append(f"claimed_archive_missing:{claimed_archive}")

    anchor_pairs = (
        ("release_gate_path", "release_gate_sha256"),
        ("proof_manifest_path", "proof_manifest_sha256"),
        ("required_log_index_path", "required_log_index_sha256"),
    )
    for path_key, sha_key in anchor_pairs:
        rel_path = anchor_paths.get(path_key)
        claimed_anchor_sha = anchor_shas.get(sha_key)
        if not rel_path:
            errors.append(f"missing_proof_anchor:{path_key}")
            continue
        if not claimed_anchor_sha:
            errors.append(f"missing_proof_anchor:{sha_key}")
            continue

        anchor_path = pathlib.Path(rel_path)
        if not anchor_path.is_absolute():
            anchor_path = (repo_root / anchor_path).resolve()
        else:
            anchor_path = anchor_path.resolve()

        if not anchor_path.exists() or not anchor_path.is_file():
            errors.append(f"proof_anchor_missing:{path_key}:{anchor_path}")
            continue

        actual_anchor_sha = _compute_sha256(anchor_path)
        if actual_anchor_sha != claimed_anchor_sha:
            errors.append(
                "proof_anchor_sha_mismatch:"
                f"{sha_key}:claimed={claimed_anchor_sha}:actual={actual_anchor_sha}"
            )

    if release_gate is not None:
        for key in ("alpha_gate_passed", "release_candidate", "production_ready"):
            if key not in boolean_claims:
                errors.append(f"missing_claimed_{key}")
                continue
            if bool(release_gate.get(key, False)) != boolean_claims[key]:
                errors.append(
                    f"{key}_mismatch:claimed={boolean_claims[key]}:actual={bool(release_gate.get(key, False))}"
                )

        expected_classification = _expected_release_classification(release_gate)
        if classification is None:
            errors.append("missing_release_classification")
        elif classification != expected_classification:
            errors.append(
                f"release_classification_mismatch:claimed={classification}:actual={expected_classification}"
            )

        normalized_handoff = handoff_text.lower()
        if "not ready for production deployment" not in normalized_handoff:
            errors.append("missing_not_production_ready_note")
        if (
            (classification is None or "alpha" not in classification.lower())
            and "proof-hardened alpha" not in normalized_handoff
        ):
            errors.append("missing_alpha_wording")

    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--archive",
        default="dist/JUDGE_ATLAS-main-final.zip",
        help="Archive path to verify",
    )
    parser.add_argument(
        "--handoff",
        default="FINAL_RELEASE_HANDOFF.md",
        help="Path to release handoff markdown",
    )
    args = parser.parse_args()

    repo_root = pathlib.Path(args.root).resolve()
    archive_path = pathlib.Path(args.archive)
    if not archive_path.is_absolute():
        archive_path = (repo_root / archive_path).resolve()
    handoff_path = pathlib.Path(args.handoff)
    if not handoff_path.is_absolute():
        handoff_path = (repo_root / handoff_path).resolve()

    ok, errors = validate_handoff(repo_root, archive_path, handoff_path)
    if ok:
        try:
            handoff_display = str(handoff_path.relative_to(repo_root))
        except ValueError:
            handoff_display = str(handoff_path)
        try:
            archive_display = str(archive_path.relative_to(repo_root))
        except ValueError:
            archive_display = str(archive_path)
        print("HANDOFF_CONSISTENCY: PASS")
        print(f"handoff={handoff_display}")
        print(f"archive={archive_display}")
        print(f"sha256={_compute_sha256(archive_path)}")
        return 0

    print("HANDOFF_CONSISTENCY: FAIL")
    print(f"handoff={handoff_path}")
    print(f"archive={archive_path}")
    for err in errors:
        print(f"ERROR: {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
