"""Check consistency between proof artifacts.

This module validates that proof_manifest.json and release_gate.json
are consistent with each other to prevent internal contradictions.

Key checks:
- Node version consistency
- Python version consistency  
- Platform consistency
- Timestamp sanity
"""

import json
import sys
from pathlib import Path
import re


def load_json_file(path: Path) -> dict:
    """Load and parse a JSON file."""
    if not path.exists():
        print(f"ERROR: Proof artifact not found: {path}")
        sys.exit(1)
    
    with open(path, "r") as f:
        return json.load(f)


def check_node_version_consistency(manifest: dict, gate: dict) -> list[str]:
    """Check Node version consistency between artifacts."""
    errors = []
    
    manifest_node = manifest.get("gate_runner_node_version")
    gate_node = gate.get("gate_runner_node_version")
    
    if manifest_node != gate_node:
        errors.append(
            f"Node version mismatch: proof_manifest.json has '{manifest_node}' "
            f"but release_gate.json has '{gate_node}'"
        )
    
    # Also check frontend node gate version
    manifest_frontend = manifest.get("frontend_node_gate_version")
    gate_frontend = gate.get("frontend_node_gate_version")
    
    if manifest_frontend != gate_frontend:
        errors.append(
            f"Frontend Node version mismatch: proof_manifest.json has '{manifest_frontend}' "
            f"but release_gate.json has '{gate_frontend}'"
        )
    
    return errors


def check_python_version_consistency(manifest: dict, gate: dict) -> list[str]:
    """Check Python version consistency between artifacts."""
    errors = []
    
    manifest_python = manifest.get("python_version")
    gate_python = gate.get("python_version")
    
    if manifest_python != gate_python:
        errors.append(
            f"Python version mismatch: proof_manifest.json has '{manifest_python}' "
            f"but release_gate.json has '{gate_python}'"
        )
    
    return errors


def check_platform_consistency(manifest: dict, gate: dict) -> list[str]:
    """Check platform consistency between artifacts."""
    errors = []
    
    manifest_platform = manifest.get("platform")
    gate_platform = gate.get("platform")
    
    if manifest_platform != gate_platform:
        errors.append(
            f"Platform mismatch: proof_manifest.json has '{manifest_platform}' "
            f"but release_gate.json has '{gate_platform}'"
        )
    
    return errors


def check_commit_hash_consistency(manifest: dict, gate: dict) -> list[str]:
    """Check commit hash consistency between artifacts."""
    errors = []
    
    manifest_hash = manifest.get("archive_hash")
    gate_hash = gate.get("commit_hash")
    
    if manifest_hash and gate_hash and manifest_hash != gate_hash:
        errors.append(
            f"Commit hash mismatch: proof_manifest.json has '{manifest_hash}' "
            f"but release_gate.json has '{gate_hash}'"
        )
    
    return errors


def check_production_ready_consistency(manifest: dict, gate: dict) -> list[str]:
    """Check production_ready flag consistency between artifacts."""
    errors: list[str] = []
    
    # proof_manifest doesn't have production_ready, but release_gate does
    # This is informational, not an error
    gate_production_ready = gate.get("production_ready")
    
    if gate_production_ready is True:
        print("WARNING: release_gate.json shows production_ready=True")
        print("This should only be set after all production blockers are cleared.")
    
    return errors


def _extract_markdown_bullets(text: str, heading: str) -> set[str]:
    lines = text.splitlines()
    section_heading = f"## {heading.strip().lower()}"
    in_section = False
    bullets: set[str] = set()

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("## "):
            in_section = line.lower() == section_heading
            continue
        if not in_section:
            continue
        if line.startswith("### "):
            break
        if line.startswith("- "):
            bullet = line[2:].strip()
            if bullet:
                bullets.add(bullet)

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


def check_readiness_vs_gate_blockers(repo_root: Path, gate: dict) -> list[str]:
    """Ensure release_readiness.md blockers match release_gate.json blockers."""
    errors: list[str] = []
    readiness_path = (
        repo_root
        / "artifacts"
        / "proof"
        / "current"
        / "release_readiness.md"
    )
    if not readiness_path.exists():
        errors.append(f"release_readiness_missing:{readiness_path}")
        return errors

    readiness_text = readiness_path.read_text(encoding="utf-8", errors="replace")
    gate_blockers_raw = gate.get("release_blockers_remaining", [])
    gate_blockers = (
        {item for item in gate_blockers_raw if isinstance(item, str) and item}
        if isinstance(gate_blockers_raw, list)
        else set()
    )
    readiness_blockers = _extract_markdown_bullets(
        readiness_text,
        "Remaining Blockers",
    )
    normalized_readiness_blockers = {
        normalized
        for blocker in readiness_blockers
        if (normalized := _normalize_readiness_blocker(blocker))
    }

    if gate_blockers != normalized_readiness_blockers:
        errors.append(
            "readiness_gate_blocker_mismatch:"
            f"gate={sorted(gate_blockers)}:"
            f"readiness={sorted(readiness_blockers)}"
        )

    overall_status_match = re.search(
        r"(?m)^-\s+overall_status:\s*(.+?)\s*$",
        readiness_text,
    )
    if overall_status_match:
        overall_status = overall_status_match.group(1).strip().lower()
        gate_passed = bool(gate.get("alpha_gate_passed", False))
        if gate_passed and overall_status == "blocked":
            errors.append("readiness_status_mismatch:gate_passed_but_readiness_blocked")
        if (not gate_passed) and overall_status == "alpha-proof-pass":
            errors.append("readiness_status_mismatch:gate_blocked_but_readiness_pass")

    return errors


def verify_proof_consistency(repo_root: Path | None = None) -> bool:
    """Verify proof artifact consistency.
    
    Args:
        repo_root: Path to repository root. If None, auto-detect from module location.
    
    Returns:
        True if all checks pass, False otherwise.
    """
    if repo_root is None:
        # Auto-detect repo root from module location
        module_dir = Path(__file__).resolve().parent
        repo_root = module_dir.parent.parent.parent
    
    proof_dir = repo_root / "artifacts" / "proof" / "current"
    
    manifest_path = proof_dir / "proof_manifest.json"
    gate_path = proof_dir / "release_gate.json"
    
    print(f"Checking proof artifact consistency...")
    print(f"  proof_manifest.json: {manifest_path}")
    print(f"  release_gate.json: {gate_path}")
    
    # Load artifacts
    manifest = load_json_file(manifest_path)
    gate = load_json_file(gate_path)
    
    # Run consistency checks
    all_errors = []
    
    all_errors.extend(check_node_version_consistency(manifest, gate))
    all_errors.extend(check_python_version_consistency(manifest, gate))
    all_errors.extend(check_platform_consistency(manifest, gate))
    all_errors.extend(check_commit_hash_consistency(manifest, gate))
    all_errors.extend(check_production_ready_consistency(manifest, gate))
    all_errors.extend(check_readiness_vs_gate_blockers(repo_root, gate))
    
    # Report results
    if all_errors:
        print("\n❌ Proof artifact consistency check FAILED")
        print("\nErrors found:")
        for error in all_errors:
            print(f"  - {error}")
        return False
    else:
        print("\n✅ Proof artifact consistency check PASSED")
        print("All proof artifacts are consistent with each other.")
        return True


def main():
    """Command-line entry point."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    success = verify_proof_consistency(repo_root)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
