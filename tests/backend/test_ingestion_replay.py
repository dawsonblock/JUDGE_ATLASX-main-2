from pathlib import Path


def test_ingestion_replay_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "scripts/verify_snapshot_replay.py",
        root / "backend/app/tests/test_snapshot_verify.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required replay checks: {missing}"
