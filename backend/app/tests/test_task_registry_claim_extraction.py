import pytest

from app.orchestration.task_registry import TaskRegistry


def test_extract_claims_task_returns_conservative_claims():
    registry = TaskRegistry()

    result = registry._task_extract_claims(
        None,
        "/tmp/workspace",
        {"text": "A short factual statement. Another sentence."},
    )

    assert result["claims_extracted"] == 2
    assert result["claims"][0]["authority"] == "derivative_only"
    assert result["claims"][0]["claim_type"] == "explicit_text_span"


def test_extract_claims_task_fails_closed_when_extractor_raises(monkeypatch):
    def boom(_text: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.ai.claim_extractor.extract_claims_from_text",
        boom,
    )

    registry = TaskRegistry()

    with pytest.raises(ValueError, match="claim extraction failed"):
        registry._task_extract_claims(
            None,
            "/tmp/workspace",
            {"text": "This should fail."},
        )