#!/usr/bin/env python3
"""Legacy clean-release helper (deprecated).

Deprecated in favor of scripts/package_and_validate_release_archive.sh.
Canonical release artifact: dist/JUDGE_ATLAS-main-final.zip.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ZIP = REPO_ROOT / "dist" / "JUDGE_ATLAS-main-final.zip"
REF_ZIP = REPO_ROOT / "JUDGE_ATLAS-reference-bundle.zip"
MANIFEST_PATH = REPO_ROOT / "artifacts" / "proof" / "current" / "RELEASE_MANIFEST.json"

INCLUDED_DIRS = [
    "backend",
    "frontend",
    "docs",
    "deploy",
    "scripts",
    "tests",
    "tools",
    "artifacts/proof/current",
]

EXCLUDED_DIR_MARKERS = {
    "__MACOSX",
    "external_reference",
    "artifacts/old",
    "artifacts/archive",
    "artifacts/history",
    "generated_logs",
    "tmp",
    "cache",
    "old_phase_reports",
    "duplicate_status_docs",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".next",
    "dist",
    "coverage",
    ".git",
    ".venv",
    "venv",
    "docs/archive",
    "legacy_disabled",
    "reference_only",
    "reports",
    "research",
    "skills",
}

EXCLUDED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".tsbuildinfo",
}


def _is_macos_sidecar(path: Path) -> bool:
    return path.name.startswith("._")


def _git_commit() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    rel_text = rel.as_posix()

    for marker in EXCLUDED_DIR_MARKERS:
        if rel_text == marker or rel_text.startswith(marker + "/"):
            return True

    if any(part in EXCLUDED_DIR_MARKERS for part in rel.parts):
        return True

    if _is_macos_sidecar(path) or any(part.startswith("._") for part in rel.parts):
        return True

    if path.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
        return True

    return False


def _build_reference_bundle() -> str | None:
    ref_dir = REPO_ROOT / "external_reference"
    if not ref_dir.exists():
        return None

    if REF_ZIP.exists():
        REF_ZIP.unlink()

    with ZipFile(REF_ZIP, "w", compression=ZIP_DEFLATED) as zf:
        for path in ref_dir.rglob("*"):
            if path.is_dir():
                continue
            arcname = path.relative_to(REPO_ROOT).as_posix()
            zf.write(path, arcname)

    return REF_ZIP.name


def _write_release_manifest(file_count: int, reference_bundle: str | None) -> dict:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "release_mode": "alpha",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "included_directories": INCLUDED_DIRS,
        "excluded_directories": sorted(EXCLUDED_DIR_MARKERS),
        "file_count": file_count,
        "proof_scope": [
            "backend tests",
            "frontend contract tests",
            "runtime boundary validation",
            "source registry validation",
            "evidence store validation",
            "ingestion replay tests",
            "security startup blocker tests",
            "publication gate tests",
        ],
        "optional_reference_bundle": reference_bundle,
    }
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    raise SystemExit(
        "build_clean_release.py is deprecated. "
        "Use scripts/package_and_validate_release_archive.sh"
    )


if __name__ == "__main__":
    raise SystemExit(main())
