from pathlib import Path


def test_public_record_evidence_gate_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_evidence_required_for_publish.py",
        root / "backend/app/tests/test_public_map_reviewed_only.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required public evidence gate tests: {missing}"
