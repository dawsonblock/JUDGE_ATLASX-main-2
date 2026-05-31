from pathlib import Path


def test_snapshot_required_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_evidence_required_for_publish.py",
        root / "backend/app/tests/test_evidence_publication_uses_verified_snapshot.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required snapshot gate tests: {missing}"
