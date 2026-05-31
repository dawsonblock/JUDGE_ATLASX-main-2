from pathlib import Path


def test_ai_cannot_publish_coverage_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        root / "backend/app/tests/test_ai_review_requires_reviewer_or_source_admin.py",
        root / "backend/app/tests/test_auto_review.py",
    ]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    assert not missing, f"missing required ai non-publish tests: {missing}"
