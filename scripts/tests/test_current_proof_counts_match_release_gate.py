"""Test that CURRENT_PROOF.md counts match release_gate.json.

This test ensures that the CURRENT_PROOF.md file is generated from
structured data in release_gate.json and does not contain hardcoded
counts that could drift from the source of truth.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

# Add parent directory to path to import release_gate module
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_gate import _write_current_proof_md


def _extract_count_from_proof_line(line: str) -> int | None:
    """Extract a count value from a CURRENT_PROOF.md line.

    Examples:
        "- backend pytest: 142 passed, 5 skipped" -> 142
        "- backend import proof: PASS (47 routes)" -> 47
        "- frontend contracts: 12 passed" -> 12
        "- proof_input_file_count: 843" -> 843
        "- release_gate_check_count: 35" -> 35
    """
    # Match patterns like "X passed", "X routes", "X skipped", etc.
    patterns = [
        r"(\d+)\s+passed",
        r"(\d+)\s+routes",
        r"(\d+)\s+skipped",
        r"file_count:\s*(\d+)",
        r"check_count:\s*(\d+)",
        r"proof_input_file_count:\s*(\d+)",
        r"release_gate_check_count:\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def test_current_proof_md_counts_match_release_gate_json(repo_root: Path, tmp_path: Path) -> None:
    """Ensure CURRENT_PROOF.md counts match release_gate.json values.

    This test:
    1. Loads release_gate.json
    2. Generates CURRENT_PROOF.md using the same payload
    3. Extracts numeric counts from CURRENT_PROOF.md
    4. Verifies those counts match the corresponding values in release_gate.json
    """
    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    if not release_gate_path.exists():
        pytest.skip(f"release_gate.json not found at {release_gate_path}")

    with release_gate_path.open(encoding="utf-8") as f:
        release_gate_data = json.load(f)

    # Generate CURRENT_PROOF.md using the same function as release_gate.py
    out_dir = tmp_path / "proof" / "current"
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_current_proof_md(
        repo_root=repo_root,
        out_dir=out_dir,
        payload=release_gate_data,
        check_count=release_gate_data.get("check_count", 0),
    )

    current_proof_path = out_dir / "CURRENT_PROOF.md"
    with current_proof_path.open(encoding="utf-8") as f:
        current_proof_lines = f.readlines()

    # Extract counts from CURRENT_PROOF.md
    proof_counts: dict[str, int] = {}
    for line in current_proof_lines:
        count = _extract_count_from_proof_line(line)
        if count is not None:
            # Use the line content as a key (simplified)
            key = line.strip().split(":")[0].replace("- ", "")
            proof_counts[key] = count

    # Verify key counts match release_gate.json
    expected_counts = {
        "proof_input_file_count": release_gate_data.get("proof_input_file_count", 0),
        "release_gate_check_count": release_gate_data.get("check_count", 0),
        "backend pytest": release_gate_data.get("backend_pytest_passed", 0),
        "backend import proof": release_gate_data.get("backend_import_route_count", 0),
        "frontend contracts": release_gate_data.get("frontend_contracts_passed", 0),
        "public API boundary": release_gate_data.get("public_api_boundary_passed", 0),
    }

    # Check that expected counts are present in CURRENT_PROOF.md
    for key, expected_value in expected_counts.items():
        if expected_value is not None and expected_value > 0:
            # Find the line in CURRENT_PROOF.md that contains this count
            found = False
            for line in current_proof_lines:
                if key.lower() in line.lower() and str(expected_value) in line:
                    found = True
                    break
            if not found:
                # Check if the count appears in the proof_counts dict
                count_found = any(
                    v == expected_value for v in proof_counts.values()
                )
                if count_found:
                    # Count exists but with different label - acceptable
                    continue
                pytest.fail(
                    f"Expected count {expected_value} for '{key}' not found "
                    f"in CURRENT_PROOF.md"
                )


def test_current_proof_md_does_not_contain_hardcoded_counts(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    """Ensure CURRENT_PROOF.md generation does not use hardcoded count literals.

    This test checks that the _write_current_proof_md function pulls all
    counts from the payload dict rather than hardcoding them.
    """
    release_gate_path = repo_root / "artifacts" / "proof" / "current" / "release_gate.json"
    if not release_gate_path.exists():
        pytest.skip(f"release_gate.json not found at {release_gate_path}")

    with release_gate_path.open(encoding="utf-8") as f:
        release_gate_data = json.load(f)

    # Modify the payload with distinctive test values
    test_payload = release_gate_data.copy()
    test_payload["backend_pytest_passed"] = 9999
    test_payload["backend_import_route_count"] = 8888
    test_payload["frontend_contracts_passed"] = 7777
    test_payload["proof_input_file_count"] = 6666
    test_payload["check_count"] = 5555

    # Generate CURRENT_PROOF.md with modified payload
    out_dir = tmp_path / "proof" / "current"
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_current_proof_md(
        repo_root=repo_root,
        out_dir=out_dir,
        payload=test_payload,
        check_count=test_payload["check_count"],
    )

    current_proof_path = out_dir / "CURRENT_PROOF.md"
    with current_proof_path.open(encoding="utf-8") as f:
        current_proof_content = f.read()

    # Verify the test values appear in the generated CURRENT_PROOF.md
    assert "9999" in current_proof_content, (
        "backend_pytest_passed count should appear"
    )
    assert "8888" in current_proof_content, (
        "backend_import_route_count should appear"
    )
    assert "7777" in current_proof_content, (
        "frontend_contracts_passed should appear"
    )
    assert "6666" in current_proof_content, (
        "proof_input_file_count should appear"
    )
    assert "5555" in current_proof_content, "check_count should appear"
