#!/usr/bin/env python3
"""Validate release integrity from a freshly extracted archive.

This script extracts the provided archive to a temp directory, resolves the
runtime root, then runs the canonical release/proof checks from inside the
extracted tree.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import zipfile
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str]:
    cp = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(
        part for part in (cp.stdout.strip(), cp.stderr.strip()) if part
    )
    return cp.returncode, output


def _resolve_runtime_root(extract_dir: Path) -> Path:
    candidates: list[Path] = []
    for marker in extract_dir.glob("**/scripts/release_gate.py"):
        root = marker.parents[1]
        if (
            (root / "backend").is_dir()
            and (root / "frontend").is_dir()
            and (root / "scripts").is_dir()
        ):
            candidates.append(root)
    unique = sorted(set(candidates))
    if len(unique) != 1:
        raise SystemExit(
            "runtime_root_resolution_failed: "
            f"expected 1, found {len(unique)}"
        )
    return unique[0]


def _build_checks(
    *,
    runtime_root: Path,
    repo_root: Path,
    archive_path: Path,
    expected_root: str,
) -> list[tuple[str, list[str], Path]]:
    return [
        (
            "check_no_pyc_strict_archive",
            ["bash", "scripts/check_no_pyc.sh", "--strict-archive"],
            runtime_root,
        ),
        (
            "validate_release_archive",
            [
                "python3",
                "scripts/validate_release_archive.py",
                "--archive",
                str(archive_path),
                "--expected-root",
                expected_root,
            ],
            repo_root,
        ),
        (
            "validate_final_zip",
            ["python3", "scripts/validate_final_zip.py", str(archive_path)],
            runtime_root,
        ),
        (
            "check_release_surface",
            [
                "python3",
                "scripts/check_release_surface.py",
                "--archive",
                str(archive_path),
            ],
            runtime_root,
        ),
        (
            "verify_archive_proof_freshness",
            [
                "python3",
                "scripts/verify_archive_proof_freshness.py",
                "--archive",
                str(archive_path),
            ],
            runtime_root,
        ),
        (
            "check_required_proof_logs",
            [
                "python3",
                "scripts/check_required_proof_logs.py",
                "--root",
                ".",
                "--strict-required-files",
                "--packaged-archive",
            ],
            runtime_root,
        ),
        (
            "check_proof_consistency",
            [
                "python3",
                "scripts/check_proof_consistency.py",
                "--packaged-archive",
            ],
            runtime_root,
        ),
        (
            "check_proof_freshness",
            ["python3", "scripts/check_proof_freshness.py"],
            runtime_root,
        ),
        (
            "verify_proof_hash_sync",
            ["python3", "scripts/verify_proof_hash_sync.py", "--root", "."],
            runtime_root,
        ),
        (
            "check_no_local_paths",
            [
                "python3",
                "scripts/check_no_local_paths_in_release_proof.py",
                "--root",
                ".",
            ],
            runtime_root,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=".", help="Repository root containing the archive"
    )
    parser.add_argument(
        "--archive",
        required=True,
        help="Archive path (absolute or repo-relative)",
    )
    parser.add_argument(
        "--expected-root",
        default="JUDGE_ATLAS-main",
        help="Expected top-level archive root",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    archive_path = Path(args.archive)
    if not archive_path.is_absolute():
        archive_path = (repo_root / archive_path).resolve()
    if not archive_path.exists() or not archive_path.is_file():
        raise SystemExit(f"archive_not_found:{archive_path}")

    failures: list[tuple[str, int, str]] = []

    with tempfile.TemporaryDirectory(
        prefix="judge_atlas_release_extract_"
    ) as tmp:
        extract_dir = Path(tmp)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_dir)

        runtime_root = _resolve_runtime_root(extract_dir)

        checks = _build_checks(
            runtime_root=runtime_root,
            repo_root=repo_root,
            archive_path=archive_path,
            expected_root=args.expected_root,
        )

        for name, cmd, cwd in checks:
            rc, output = _run(cmd, cwd=cwd)
            if rc != 0:
                failures.append((name, rc, output))

        if failures:
            print(
                "EXTRACTED_RELEASE_VALIDATION: FAIL "
                f"({len(failures)} checks failed)"
            )
            for name, rc, output in failures:
                print(f"- {name}: rc={rc}")
                if output:
                    print(output)
            return 1

    print("EXTRACTED_RELEASE_VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
