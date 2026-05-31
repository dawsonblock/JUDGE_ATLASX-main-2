from pathlib import Path


def test_review_gate_publication_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_review_gates.py",
        root / "backend/app/tests/test_review_rejected_not_public.py",
        root / "backend/app/tests/test_publish_rules.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required review/publication tests: {missing}"
