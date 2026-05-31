from pathlib import Path


def test_snapshot_immutability_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_snapshot_immutability.py",
        root / "backend/app/tests/test_snapshot_verify.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required snapshot immutability tests: {missing}"
