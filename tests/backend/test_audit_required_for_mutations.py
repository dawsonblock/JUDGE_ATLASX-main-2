from pathlib import Path


def test_audit_required_for_mutations_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_graph_mutation_audit_fail_closed.py",
        root / "backend/app/tests/test_admin_quarantine_audit_logging.py",
        root / "backend/app/tests/test_review_decision_audit.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required audit mutation tests: {missing}"
