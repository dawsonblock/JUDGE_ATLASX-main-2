"""LLM reviewer assistant safety tests.

Proves:
  - Permitted task types succeed
  - Prohibited task types are rejected with ProhibitedTaskError
  - No citation → answer is None (citation lock)
  - Low confidence → requires_human_review = True
  - Unsupported claims → requires_human_review = True
  - Legal-conclusion phrases are redacted from answers
  - OpenAI provider requires OPENAI_API_KEY
  - Ollama provider returns empty response on connection failure
  - Schemas enforce invariants in __post_init__
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
# Minimal concrete provider for testing
# ---------------------------------------------------------------------------


class _EchoProvider(LLMProvider):
    """Provider that echoes the question back with a citation if evidence_urls is non-empty."""

    def _call(self, request: LLMRequest) -> LLMResponse:
        citations = [Citation(source_url=u) for u in request.evidence_urls]
        return LLMResponse(
            answer=request.prompt if citations else None,
            citations=citations,
            confidence=0.9 if citations else 0.0,
            unsupported_claims=[],
            requires_human_review=not bool(citations),
            task_type=request.task_type,
            model_name="echo",
        )


class _AlwaysCiteProvider(LLMProvider):
    """Provider that always returns an answer with a citation."""

    def __init__(self, answer: str = "test answer"):
        self._answer = answer

    def _call(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            answer=self._answer,
            citations=[Citation(source_url="https://example.com/source")],
            confidence=0.9,
            unsupported_claims=[],
            requires_human_review=False,
            task_type=request.task_type,
            model_name="always_cite",
        )


# ===========================================================================
# Tests: LLMResponse schema invariants
# ===========================================================================


class TestLLMResponseInvariants:
    def test_no_citations_forces_answer_none(self):
        """No citations → answer must be None regardless of input."""
        resp = LLMResponse(
            answer="Some answer text",
            citations=[],  # no citations
            confidence=0.9,
        )
        assert resp.answer is None

    def test_no_citations_forces_requires_human_review_true(self):
        """No citations → requires_human_review must be True."""
        resp = LLMResponse(answer="text", citations=[], confidence=0.9)
        assert resp.requires_human_review is True

    def test_low_confidence_requires_human_review(self):
        """confidence < 0.7 → requires_human_review must be True."""
        resp = LLMResponse(
            answer="text",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.5,
        )
        assert resp.requires_human_review is True

    def test_high_confidence_with_citations_no_human_review(self):
        """confidence >= 0.7 with citations and no unsupported claims → no human review needed."""
        resp = LLMResponse(
            answer="answer",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.8,
            unsupported_claims=[],
            requires_human_review=False,
        )
        assert resp.requires_human_review is False

    def test_unsupported_claims_requires_human_review(self):
        """Unsupported claims → requires_human_review must be True."""
        resp = LLMResponse(
            answer="answer",
            citations=[Citation(source_url="https://example.com")],
            confidence=0.9,
            unsupported_claims=["claim 1 has no citation"],
        )
        assert resp.requires_human_review is True

    def test_confidence_clamped_below_zero(self):
        """Confidence below 0.0 must be clamped to 0.0."""
        resp = LLMResponse(
            answer=None, citations=[], confidence=-1.5
        )
        assert resp.confidence == 0.0

    def test_confidence_clamped_above_one(self):
        """Confidence above 1.0 must be clamped to 1.0."""
        resp = LLMResponse(
            answer="a",
            citations=[Citation(source_url="https://example.com")],
            confidence=5.0,
        )
        assert resp.confidence == 1.0


# ===========================================================================
# Tests: LLMProvider safety boundary — prohibited task types
# ===========================================================================


class TestProhibitedTaskTypes:
    """All PROHIBITED_TASK_TYPES must be rejected with ProhibitedTaskError."""

    @pytest.mark.parametrize("task_type", list(PROHIBITED_TASK_TYPES))
    def test_prohibited_task_raises(self, task_type):
        """Calling complete() with a prohibited task must raise ProhibitedTaskError."""
        provider = _EchoProvider()
        request = LLMRequest(
            task_type=task_type,
            prompt="test",
            evidence_texts=["evidence"],
            evidence_urls=["https://example.com"],
        )
        with pytest.raises(ProhibitedTaskError):
            provider.complete(request)

    def test_publish_record_is_prohibited(self):
        assert LLMTaskType.PUBLISH_RECORD in PROHIBITED_TASK_TYPES

    def test_assign_guilt_is_prohibited(self):
        assert LLMTaskType.ASSIGN_GUILT in PROHIBITED_TASK_TYPES

    def test_infer_criminality_is_prohibited(self):
        assert LLMTaskType.INFER_CRIMINALITY in PROHIBITED_TASK_TYPES

    def test_score_dangerousness_is_prohibited(self):
        assert LLMTaskType.SCORE_DANGEROUSNESS in PROHIBITED_TASK_TYPES

    def test_make_legal_conclusion_is_prohibited(self):
        assert LLMTaskType.MAKE_LEGAL_CONCLUSION in PROHIBITED_TASK_TYPES


# ===========================================================================
# Tests: Permitted task types succeed
# ===========================================================================


class TestPermittedTaskTypes:
    """All PERMITTED_TASK_TYPES must be accepted by the provider."""

    @pytest.mark.parametrize("task_type", list(PERMITTED_TASK_TYPES))
    def test_permitted_task_succeeds(self, task_type):
        provider = _EchoProvider()
        request = LLMRequest(
            task_type=task_type,
            prompt="test question",
            evidence_texts=["The court held that..."],
            evidence_urls=["https://example.com/case"],
        )
        resp = provider.complete(request)
        assert isinstance(resp, LLMResponse)
        # No citations = no answer, but no exception
        assert resp.answer == "test question"  # echo provider returns prompt when cited

    def test_permitted_tasks_do_not_include_prohibited(self):
        """PERMITTED and PROHIBITED sets must be disjoint."""
        assert not (PERMITTED_TASK_TYPES & PROHIBITED_TASK_TYPES)


# ===========================================================================
# Tests: Citation lock — no citation = no answer
# ===========================================================================


class TestCitationLock:
    def test_provider_without_citations_returns_none_answer(self):
        """If provider returns no citations, the base class sets answer=None."""
        class NoCiteProvider(LLMProvider):
            def _call(self, request: LLMRequest) -> LLMResponse:
                return LLMResponse(
                    answer="some answer without citation",
                    citations=[],  # no citations
                    confidence=0.9,
                )

        provider = NoCiteProvider()
        request = LLMRequest(
            task_type=LLMTaskType.SUMMARIZE_EVIDENCE,
            prompt="summarize",
            evidence_texts=["text"],
            evidence_urls=[],  # no URLs
        )
        resp = provider.complete(request)
        assert resp.answer is None, "No citations should force answer=None"
        assert resp.requires_human_review is True


# ===========================================================================
# Tests: ReviewerAssistant prohibited task types
# ===========================================================================


class TestReviewerAssistantSafety:
    def test_summarize_evidence_works(self):
        """summarize_evidence must succeed with a citation."""
        assistant = ReviewerAssistant(_EchoProvider())
        resp = assistant.summarize_evidence(
            evidence_texts=["The court ruled on Jan 1..."],
            evidence_urls=["https://example.com/case"],
        )
        assert isinstance(resp, LLMResponse)

    def test_prohibited_task_type_raises(self):
        """ReviewerAssistant._run() with prohibited task must raise."""
        assistant = ReviewerAssistant(_EchoProvider())
        with pytest.raises(ProhibitedTaskError):
            assistant._run(
                LLMTaskType.ASSIGN_GUILT,
                "Is this person guilty?",
                ["evidence"],
                ["https://example.com"],
            )

    def test_answer_with_guilt_phrase_is_redacted(self):
        """Answers containing 'is guilty' must have their answer suppressed."""
        provider = _AlwaysCiteProvider(answer="The defendant is guilty of fraud.")
        assistant = ReviewerAssistant(provider)
        resp = assistant.summarize_evidence(
            evidence_texts=["court text"],
            evidence_urls=["https://example.com/case"],
        )
        assert resp.answer is None, "Prohibited phrase should suppress the answer"
        assert resp.requires_human_review is True

    def test_answer_without_prohibited_phrase_passes(self):
        """Answers without prohibited phrases must not be redacted."""
        provider = _AlwaysCiteProvider(answer="The court issued an order on January 1, 2024.")
        assistant = ReviewerAssistant(provider)
        resp = assistant.summarize_evidence(
            evidence_texts=["court text"],
            evidence_urls=["https://example.com/case"],
        )
        assert resp.answer is not None
        assert "court issued an order" in resp.answer

    def test_provider_error_returns_safe_empty_response(self):
        """Provider errors must return a safe response (not raise to the caller)."""
        class ErrorProvider(LLMProvider):
            def _call(self, request: LLMRequest) -> LLMResponse:
                raise RuntimeError("Connection refused")

        assistant = ReviewerAssistant(ErrorProvider())
        resp = assistant.summarize_evidence(
            evidence_texts=["text"],
            evidence_urls=["https://example.com"],
        )
        assert resp.answer is None
        assert resp.requires_human_review is True
        assert any("provider_error" in c for c in resp.unsupported_claims)

    def test_extract_entities_returns_response(self):
        """extract_entities must return a valid LLMResponse."""
        assistant = ReviewerAssistant(_EchoProvider())
        resp = assistant.extract_entities(
            evidence_texts=["Judge John Smith ruled on Dec 5, 2023 in Regina."],
            evidence_urls=["https://example.com/case"],
        )
        assert isinstance(resp, LLMResponse)

    def test_compare_claim_to_source_returns_response(self):
        """compare_claim_to_source must return a valid LLMResponse."""
        assistant = ReviewerAssistant(_EchoProvider())
        resp = assistant.compare_claim_to_source(
            claim="The judge ruled in favour of the defendant",
            evidence_texts=["The court held for the plaintiff."],
            evidence_urls=["https://example.com/case"],
        )
        assert isinstance(resp, LLMResponse)

    def test_no_evidence_texts_results_in_no_answer(self):
        """If no evidence is provided, the response must have answer=None."""
        assistant = ReviewerAssistant(_EchoProvider())
        resp = assistant.answer_question(
            question="What happened?",
            evidence_texts=[],  # no evidence
            evidence_urls=[],   # no URLs → no citations
        )
        assert resp.answer is None
        assert resp.requires_human_review is True


# ===========================================================================
# Tests: OpenAI provider requires API key
# ===========================================================================


class TestOpenAIProviderRequiresKey:
    def test_missing_api_key_returns_error_response(self):
        """OpenAI provider with no API key must return an error response (not raise)."""
        from app.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(api_key="")  # No key
        request = LLMRequest(
            task_type=LLMTaskType.SUMMARIZE_EVIDENCE,
            prompt="summarize",
            evidence_texts=["text"],
            evidence_urls=[],
        )
        resp = provider._call(request)
        assert resp.answer is None
        assert any("OPENAI_API_KEY" in c for c in resp.unsupported_claims)


# ===========================================================================
# Tests: Ollama provider graceful error handling
# ===========================================================================


class TestOllamaProviderGracefulError:
    def test_connection_failure_returns_error_response(self):
        """Ollama provider on failed connection must return safe error response."""
        from app.llm.ollama_provider import OllamaProvider

        # Use a port that should not be listening
        provider = OllamaProvider(base_url="http://localhost:19999", model="llama3")
        request = LLMRequest(
            task_type=LLMTaskType.SUMMARIZE_EVIDENCE,
            prompt="summarize",
            evidence_texts=["text"],
            evidence_urls=[],
        )
        resp = provider._call(request)
        # Should not raise; should return safe empty response
        assert resp.answer is None
        assert resp.requires_human_review is True
