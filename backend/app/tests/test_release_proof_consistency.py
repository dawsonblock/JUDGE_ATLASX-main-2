"""Test consistency of Markdown proof files with the authoritative release_gate.json.

This test fails if any Markdown proof file (CURRENT_PROOF.md, release_readiness.md,
FIX_VERIFICATION_REPORT.md) claims success/pass while the JSON gate says blocked (alpha_gate_passed is false).
"""

import json
import re
from pathlib import Path
import pytest


@pytest.fixture
def repo_root():
    """Return the repository root directory."""
    return Path(__file__).parent.parent.parent.parent


@pytest.fixture
def release_gate_path(repo_root):
    """Return path to release_gate.json."""
    return repo_root / "artifacts" / "proof" / "current" / "release_gate.json"


@pytest.fixture
def current_proof_path(repo_root):
    """Return path to CURRENT_PROOF.md in artifacts."""
    return repo_root / "artifacts" / "proof" / "current" / "CURRENT_PROOF.md"


@pytest.fixture
def root_current_proof_path(repo_root):
    """Return path to CURRENT_PROOF.md in repo root."""
    return repo_root / "CURRENT_PROOF.md"


@pytest.fixture
def release_readiness_path(repo_root):
    """Return path to release_readiness.md."""
    return repo_root / "artifacts" / "proof" / "current" / "release_readiness.md"


@pytest.fixture
def fix_verification_report_path(repo_root):
    """Return path to FIX_VERIFICATION_REPORT.md."""
    return repo_root / "artifacts" / "proof" / "current" / "FIX_VERIFICATION_REPORT.md"


def test_release_proof_files_consistency(
    release_gate_path,
    current_proof_path,
    root_current_proof_path,
    release_readiness_path,
    fix_verification_report_path,
):
    """Verify that Markdown proof files reflect the exact status of release_gate.json."""
    if not release_gate_path.exists():
        pytest.skip(f"release_gate.json not found at {release_gate_path}")

    # 1. Load authoritative release_gate.json
    gate_data = json.loads(release_gate_path.read_text(encoding="utf-8"))
    alpha_gate_passed = gate_data.get("alpha_gate_passed")
    assert alpha_gate_passed is not None, "release_gate.json missing 'alpha_gate_passed'"

    # 2. Check CURRENT_PROOF.md (artifacts)
    if current_proof_path.exists():
        content = current_proof_path.read_text(encoding="utf-8").lower()
        if alpha_gate_passed:
            assert "- alpha_gate_passed: true" in content
            assert "- alpha_gate_status: pass" in content
            assert "- alpha_gate_passed: false" not in content
            assert "- alpha_gate_status: blocked" not in content
        else:
            assert "- alpha_gate_passed: false" in content
            assert "- alpha_gate_status: blocked" in content
            assert "- alpha_gate_passed: true" not in content
            assert "- alpha_gate_status: pass" not in content

    # 3. Check CURRENT_PROOF.md (repo root)
    if root_current_proof_path.exists():
        content = root_current_proof_path.read_text(encoding="utf-8").lower()
        if alpha_gate_passed:
            assert "- alpha_gate_passed: true" in content
            assert "- alpha_gate_status: pass" in content
            assert "- alpha_gate_passed: false" not in content
            assert "- alpha_gate_status: blocked" not in content
        else:
            assert "- alpha_gate_passed: false" in content
            assert "- alpha_gate_status: blocked" in content
            assert "- alpha_gate_passed: true" not in content
            assert "- alpha_gate_status: pass" not in content

    # 4. Check release_readiness.md
    if release_readiness_path.exists():
        content = release_readiness_path.read_text(encoding="utf-8").lower()
        overall_status_match = re.search(r"^- overall_status: (.+)$", content, re.MULTILINE)
        assert overall_status_match, "release_readiness.md missing overall_status"
        overall_status = overall_status_match.group(1).strip()

        if alpha_gate_passed:
            assert overall_status == "alpha-proof-pass"
        else:
            assert overall_status == "blocked"
            assert overall_status != "alpha-proof-pass"

    # 5. Check FIX_VERIFICATION_REPORT.md
    if fix_verification_report_path.exists():
        content = fix_verification_report_path.read_text(encoding="utf-8").lower()
        passed_line = f"- alpha_gate_passed: {str(alpha_gate_passed).lower()}"
        assert passed_line in content, f"FIX_VERIFICATION_REPORT.md does not match gate status (expected: {passed_line})"
        if alpha_gate_passed:
            assert "- alpha_gate_passed: false" not in content
        else:
            assert "- alpha_gate_passed: true" not in content
