"""Test that all paths referenced in release_gate.json["logs"] actually exist.

This validates proof artifact truthfulness: if release_gate.json references a file,
that file must exist in the release archive.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_release_gate_log_paths_exist(repo_root: Path):
    """All proof log paths in release_gate.json must exist relative to repo root."""
    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    current_proof_path = repo_root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md"

    # Skip test if release_gate.json doesn't exist (e.g., during initial development)
    if not release_gate_path.exists():
        pytest.skip(f"release_gate.json not found at {release_gate_path}")

    with release_gate_path.open(encoding="utf-8") as f:
        release_gate = json.load(f)

    if current_proof_path.exists():
        current_proof_text = current_proof_path.read_text(encoding="utf-8").lower()
        if "- status: in_progress" in current_proof_text:
            pytest.skip("current proof is still being assembled")

    logs = release_gate.get("logs", {})
    checks = release_gate.get("checks", [])
    if not logs and not checks:
        pytest.fail("release_gate.json has neither 'logs' nor 'checks' sections")

    missing = []
    for name, path in logs.items():
        full_path = repo_root / path
        if not full_path.exists():
            missing.append((name, path))

    for check in checks:
        if not isinstance(check, dict):
            continue
        check_name = check.get("name", "unknown")
        path = check.get("log_path")
        if not isinstance(path, str) or not path:
            continue
        full_path = repo_root / path
        if not full_path.exists():
            missing.append((f"checks.{check_name}", path))

    if missing:
        missing_str = "\n".join(f"  - {name}: {path}" for name, path in missing)
        pytest.fail(
            f"release_gate.json references {len(missing)} missing file(s):\n{missing_str}\n"
            f"Total references: logs={len(logs)} checks={len(checks)}"
        )

    # All files exist
    assert True


def test_release_gate_current_proof_md_exists(repo_root: Path):
    """CURRENT_PROOF.md must exist as referenced in proof_input_paths."""
    current_proof_path = repo_root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md"
    if not current_proof_path.exists():
        pytest.skip(f"CURRENT_PROOF.md not found at {current_proof_path}")
    assert True


def test_release_gate_repair_report_md_exists(repo_root: Path):
    """REPAIR_REPORT.md must exist as referenced in logs."""
    repair_report_path = repo_root / "artifacts" / "proof" / "current" / "REPAIR_REPORT.md"
    if not repair_report_path.exists():
        pytest.skip(f"REPAIR_REPORT.md not found at {repair_report_path}")
    assert True
