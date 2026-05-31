from pathlib import Path


def test_review_audit_log_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_review_decision_audit.py",
        root / "backend/app/tests/test_admin_memory_audit_logging.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required review audit tests: {missing}"
