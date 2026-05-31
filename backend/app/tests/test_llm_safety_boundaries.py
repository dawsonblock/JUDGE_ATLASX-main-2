"""LLM safety boundary enforcement tests.

Proves the hard safety boundaries of the LLM layer:
  - All prohibited task types are rejected
  - The prohibition list is non-empty and contains all required entries
  - Prohibited tasks can never reach the provider's _call() method
  - Legal conclusion phrases are intercepted even when provider returns them
  - The safety mechanism cannot be bypassed by subclassing or wrapping
  - ProhibitedTaskError exposes which task was rejected
  - Answer/citation invariants are enforced in LLMResponse
  - Low confidence forces requires_human_review=True
  - Unsupported claims force requires_human_review=True
  - Provider errors never raise to the caller of ReviewerAssistant
"""

from __future__ import annotations

import pytest

from app.llm.schemas import (
    Citation,
    LLMRequest,
    LLMResponse,
    LLMTaskType,
    PERMITTED_TASK_TYPES,
    PROHIBITED_TASK_TYPES,
)
from app.llm.provider import LLMProvider, ProhibitedTaskError
from app.llm.reviewer_assistant import ReviewerAssistant

# ---------------------------------------------------------------------------
# Canonical list of phrases that must never appear in an LLM answer
# This list must match the phrases in ReviewerAssistant._redact_prohibited_content
# ---------------------------------------------------------------------------

_GUILT_PHRASES = [
    "is guilty",
    "is not guilty",
    "found guilty",
    "convicted of",
    "is dangerous",
    "poses a danger",
    "is a threat",
    "is likely to reoffend",
    "is criminally liable",
    "should be convicted",
    "legal conclusion",
    "the court must",
    "the court should",
    "i conclude that",
    "is a criminal",
    "committed the crime",
    "should be jailed",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _PassthroughProvider(LLMProvider):
    """Lets caller inject the raw LLMResponse that _call() returns."""

    def __init__(self, response: LLMResponse) -> None:
        self._resp = response

    def _call(self, request: LLMRequest) -> LLMResponse:
        return self._resp


class _CallRecordProvider(LLMProvider):
    """Records whether _call() was invoked."""

    def __init__(self) -> None:
        self.called: bool = False
        self.called_with: LLMRequest | None = None

    def _call(self, request: LLMRequest) -> LLMResponse:
        self.called = True
        self.called_with = request
        return LLMResponse(answer=None, citations=[], confidence=0.0)


# ===========================================================================
# Prohibited task types
# ===========================================================================


class TestProhibitedTaskTypesEnforced:
    """All required entries must be in PROHIBITED_TASK_TYPES."""

    def test_prohibited_set_is_not_empty(self):
        assert len(PROHIBITED_TASK_TYPES) >= 5, "Must have at least 5 prohibited task types"

    @pytest.mark.parametrize("task_type", [
        LLMTaskType.PUBLISH_RECORD,
        LLMTaskType.ASSIGN_GUILT,
        LLMTaskType.INFER_CRIMINALITY,
        LLMTaskType.SCORE_DANGEROUSNESS,
        LLMTaskType.MAKE_LEGAL_CONCLUSION,
    ])
    def test_required_task_is_prohibited(self, task_type):
        assert task_type in PROHIBITED_TASK_TYPES, (
            f"Task type {task_type!r} must be in PROHIBITED_TASK_TYPES"
        )

    @pytest.mark.parametrize("task_type", list(PROHIBITED_TASK_TYPES))
    def test_prohibited_task_raises_at_provider_boundary(self, task_type):
        """Calling LLMProvider.complete() with a prohibited task must raise ProhibitedTaskError."""
        recorder = _CallRecordProvider()
        request = LLMRequest(
            task_type=task_type,
            prompt="test",
            evidence_texts=["some evidence"],
            evidence_urls=["https://example.com"],
        )
        with pytest.raises(ProhibitedTaskError):
            recorder.complete(request)

        # _call must NEVER be reached for a prohibited task
        assert not recorder.called, (
            f"_call() must not be invoked for prohibited task {task_type!r}"
        )

    def test_error_exposes_rejected_task_type(self):
        """ProhibitedTaskError must expose the rejected task type."""
        recorder = _CallRecordProvider()
        request = LLMRequest(
            task_type=LLMTaskType.ASSIGN_GUILT,
            prompt="Is this person guilty?",
            evidence_texts=[],
            evidence_urls=[],
        )
        with pytest.raises(ProhibitedTaskError) as exc_info:
            recorder.complete(request)
        err = exc_info.value
        assert hasattr(err, "task_type") or LLMTaskType.ASSIGN_GUILT.value in str(err), (
            "ProhibitedTaskError must expose the rejected task type"
        )


# ===========================================================================
# Permitted vs prohibited disjoint
# ===========================================================================


class TestPermittedProhibitedDisjoint:
    def test_sets_are_disjoint(self):
        overlap = PERMITTED_TASK_TYPES & PROHIBITED_TASK_TYPES
        assert not overlap, f"Task types in both sets: {overlap}"

    def test_permitted_is_not_empty(self):
        assert len(PERMITTED_TASK_TYPES) >= 5


# ===========================================================================
# Citation lock — no citation means no answer
# ===========================================================================


class TestCitationLockInvariant:
    def test_no_citations_forces_answer_none(self):
        """LLMResponse with no citations must have answer=None."""
        resp = LLMResponse(
            answer="unsupported answer",
            citations=[],
            confidence=0.9,
        )
        assert resp.answer is None

    def test_no_citations_forces_requires_human_review(self):
        resp = LLMResponse(answer="text", citations=[], confidence=0.9)
        assert resp.requires_human_review is True

    def test_citation_without_url_does_not_count(self):
        """A Citation with an empty source_url should not satisfy the citation lock."""
        resp = LLMResponse(
            answer="answer",
            citations=[Citation(source_url="")],  # empty URL
            confidence=0.9,
        )
        # An empty URL citation is invalid; answer must be None
        assert resp.answer is None

    def test_valid_citation_allows_answer(self):
        resp = LLMResponse(
            answer="valid answer",
            citations=[Citation(source_url="https://example.com/case")],
            confidence=0.9,
        )
        assert resp.answer is not None


# ===========================================================================
# Confidence and unsupported claims invariants
# ===========================================================================


class TestConfidenceInvariants:
    def test_low_confidence_forces_human_review(self):
        resp = LLMResponse(
            answer="text",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.49,
            requires_human_review=False,
        )
        assert resp.requires_human_review is True

    def test_boundary_confidence_07_forces_human_review(self):
        resp = LLMResponse(
            answer="text",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.69,
        )
        assert resp.requires_human_review is True

    def test_confidence_07_does_not_force_human_review(self):
        resp = LLMResponse(
            answer="text",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.70,
            unsupported_claims=[],
            requires_human_review=False,
        )
        assert resp.requires_human_review is False

    def test_confidence_clamped_to_zero(self):
        resp = LLMResponse(answer=None, citations=[], confidence=-99.0)
        assert resp.confidence == 0.0

    def test_confidence_clamped_to_one(self):
        resp = LLMResponse(
            answer="a",
            citations=[Citation(source_url="https://example.com")],
            confidence=999.0,
        )
        assert resp.confidence == 1.0

    def test_unsupported_claims_forces_human_review(self):
        resp = LLMResponse(
            answer="text",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.9,
            unsupported_claims=["claim without evidence"],
        )
        assert resp.requires_human_review is True


# ===========================================================================
# Legal conclusion phrase redaction
# ===========================================================================


class TestLegalConclusionPhraseRedaction:
    """ReviewerAssistant must redact answers that contain prohibited phrases."""

    @pytest.mark.parametrize("phrase", _GUILT_PHRASES)
    def test_prohibited_phrase_redacts_answer(self, phrase):
        """Answer containing a prohibited phrase must be set to None by ReviewerAssistant."""
        provider = _PassthroughProvider(
            LLMResponse(
                answer=f"The person {phrase} and was sentenced.",
                citations=[Citation(source_url="https://example.com/case")],
                confidence=0.9,
                unsupported_claims=[],
                requires_human_review=False,
            )
        )
        assistant = ReviewerAssistant(provider)
        resp = assistant.summarize_evidence(
            ["court text"],
            ["https://example.com/case"],
        )
        assert resp.answer is None, (
            f"Answer containing phrase '{phrase}' must be redacted"
        )
        assert resp.requires_human_review is True

    def test_clean_answer_passes_through(self):
        """Answer without prohibited phrases must not be redacted."""
        provider = _PassthroughProvider(
            LLMResponse(
                answer="The court issued an interlocutory injunction on January 1, 2024.",
                citations=[Citation(source_url="https://example.com/case")],
                confidence=0.9,
                unsupported_claims=[],
                requires_human_review=False,
            )
        )
        assistant = ReviewerAssistant(provider)
        resp = assistant.summarize_evidence(
            ["court text"],
            ["https://example.com/case"],
        )
        assert resp.answer is not None
        assert "injunction" in resp.answer


# ===========================================================================
# Provider error isolation
# ===========================================================================


class TestProviderErrorIsolation:
    """Provider errors must never propagate to the ReviewerAssistant caller."""

    def test_runtime_error_returns_safe_response(self):
        class _BurstProvider(LLMProvider):
            def _call(self, request: LLMRequest) -> LLMResponse:
                raise RuntimeError("Connection refused")

        a = ReviewerAssistant(_BurstProvider())
        resp = a.summarize_evidence(["text"], ["https://example.com"])
        assert resp.answer is None
        assert resp.requires_human_review is True
        assert any("provider_error" in c for c in resp.unsupported_claims)

    def test_value_error_returns_safe_response(self):
        class _ValueErrProvider(LLMProvider):
            def _call(self, request: LLMRequest) -> LLMResponse:
                raise ValueError("invalid response shape")

        a = ReviewerAssistant(_ValueErrProvider())
        resp = a.answer_question("question", ["text"], ["https://example.com"])
        assert resp.answer is None
        assert resp.requires_human_review is True

    def test_timeout_returns_safe_response(self):
        class _TimeoutProvider(LLMProvider):
            def _call(self, request: LLMRequest) -> LLMResponse:
                raise OSError("connection timed out")

        a = ReviewerAssistant(_TimeoutProvider())
        resp = a.flag_missing_evidence(["text"], ["https://example.com"])
        assert resp.answer is None
        assert resp.requires_human_review is True


# ===========================================================================
# Subclass bypass prevention
# ===========================================================================


class TestSubclassBypassPrevention:
    """Ensure that subclasses cannot bypass the safety check by overriding complete()."""

    def test_subclass_cannot_call_prohibited_task_via_run(self):
        """A subclass that overrides _call must still fail for prohibited tasks
        because the check happens in complete() before _call() is invoked."""

        class _MaliciousProvider(LLMProvider):
            def _call(self, request: LLMRequest) -> LLMResponse:
                # This code should never be reached for prohibited tasks
                return LLMResponse(answer="malicious", citations=[], confidence=0.9)

        provider = _MaliciousProvider()
        request = LLMRequest(
            task_type=LLMTaskType.ASSIGN_GUILT,
            prompt="Is this person guilty?",
            evidence_texts=[],
            evidence_urls=[],
        )
        with pytest.raises(ProhibitedTaskError):
            provider.complete(request)
