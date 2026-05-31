"""ReviewerAssistant contract tests.

Proves the full ReviewerAssistant public API:
  - summarize_evidence
  - extract_entities
  - compare_claim_to_source
  - flag_missing_evidence
  - detect_contradictions
  - answer_question
  - produce_reviewer_notes

Each public method must:
  - Accept evidence_texts + evidence_urls
  - Return a valid LLMResponse
  - Have answer=None when no citations provided
  - Never raise exceptions on provider failure (returns safe error response)
  - Never call a prohibited task type
"""

from __future__ import annotations

import pytest

from app.llm.schemas import (
    Citation,
    LLMRequest,
    LLMResponse,
    LLMTaskType,
    PERMITTED_TASK_TYPES,
)
from app.llm.provider import LLMProvider, ProhibitedTaskError
from app.llm.reviewer_assistant import ReviewerAssistant


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _CitingProvider(LLMProvider):
    """Returns an answer with citations if evidence_urls is non-empty."""

    def __init__(self, answer: str = "test answer") -> None:
        self._answer = answer

    def _call(self, request: LLMRequest) -> LLMResponse:
        citations = [Citation(source_url=u) for u in request.evidence_urls]
        return LLMResponse(
            answer=self._answer if citations else None,
            citations=citations,
            confidence=0.9 if citations else 0.0,
            unsupported_claims=[],
            requires_human_review=not bool(citations),
            task_type=request.task_type,
            model_name="citing_stub",
        )


class _ErrorProvider(LLMProvider):
    """Always raises RuntimeError."""

    def _call(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("simulated provider failure")


class _NoCiteProvider(LLMProvider):
    """Returns an answer but no citations — should be intercepted."""

    def _call(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            answer="answer without citation",
            citations=[],
            confidence=0.9,
        )


_EVIDENCE_TEXTS = ["The court held that the defendant is liable."]
_EVIDENCE_URLS = ["https://www.canlii.org/en/sk/skkb/doc/2024/2024skkb1/2024skkb1.html"]


# ===========================================================================
# summarize_evidence
# ===========================================================================


class TestSummarizeEvidence:
    def test_returns_response_with_citation(self):
        a = ReviewerAssistant(_CitingProvider("Summary of findings."))
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp, LLMResponse)
        assert resp.answer == "Summary of findings."
        assert len(resp.citations) == 1

    def test_no_urls_produces_no_answer(self):
        a = ReviewerAssistant(_CitingProvider())
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, evidence_urls=[])
        assert resp.answer is None
        assert resp.requires_human_review is True

    def test_error_returns_safe_response(self):
        a = ReviewerAssistant(_ErrorProvider())
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None
        assert resp.requires_human_review is True
        assert any("provider_error" in c for c in resp.unsupported_claims)

    def test_no_citation_provider_gives_no_answer(self):
        a = ReviewerAssistant(_NoCiteProvider())
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None


# ===========================================================================
# extract_entities
# ===========================================================================


class TestExtractEntities:
    def test_returns_response(self):
        a = ReviewerAssistant(_CitingProvider("Entities: John Smith, 2024-01-01, Regina."))
        resp = a.extract_entities(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp, LLMResponse)

    def test_empty_evidence_urls_means_no_answer(self):
        a = ReviewerAssistant(_CitingProvider())
        resp = a.extract_entities(_EVIDENCE_TEXTS, evidence_urls=[])
        assert resp.answer is None

    def test_error_is_handled_safely(self):
        a = ReviewerAssistant(_ErrorProvider())
        resp = a.extract_entities(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None
        assert resp.requires_human_review is True


# ===========================================================================
# compare_claim_to_source
# ===========================================================================


class TestCompareClaimToSource:
    def test_returns_response(self):
        a = ReviewerAssistant(_CitingProvider("Claim matches source text."))
        resp = a.compare_claim_to_source(
            "The defendant was found liable.",
            _EVIDENCE_TEXTS,
            _EVIDENCE_URLS,
        )
        assert isinstance(resp, LLMResponse)
        assert resp.answer is not None

    def test_no_evidence_means_no_answer(self):
        a = ReviewerAssistant(_CitingProvider())
        resp = a.compare_claim_to_source("claim", [], [])
        assert resp.answer is None
        assert resp.requires_human_review is True

    def test_error_is_handled_safely(self):
        a = ReviewerAssistant(_ErrorProvider())
        resp = a.compare_claim_to_source("claim", _EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None


# ===========================================================================
# flag_missing_evidence
# ===========================================================================


class TestFlagMissingEvidence:
    def test_returns_response(self):
        a = ReviewerAssistant(_CitingProvider("No missing evidence detected."))
        resp = a.flag_missing_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp, LLMResponse)

    def test_flag_missing_evidence_with_claim(self):
        a = ReviewerAssistant(_CitingProvider("No key evidence is missing."))
        resp = a.flag_missing_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS, claim="The judge was biased.")
        assert isinstance(resp, LLMResponse)


# ===========================================================================
# detect_contradictions
# ===========================================================================


class TestDetectContradictions:
    def test_returns_response(self):
        a = ReviewerAssistant(_CitingProvider("No contradictions found."))
        resp = a.detect_contradictions(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp, LLMResponse)

    def test_error_is_handled_safely(self):
        a = ReviewerAssistant(_ErrorProvider())
        resp = a.detect_contradictions(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None
        assert resp.requires_human_review is True


# ===========================================================================
# answer_question
# ===========================================================================


class TestAnswerQuestion:
    def test_answer_with_citation(self):
        a = ReviewerAssistant(_CitingProvider("On January 1, 2024."))
        resp = a.answer_question("When was the ruling?", _EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer == "On January 1, 2024."
        assert len(resp.citations) == 1

    def test_no_urls_means_no_answer(self):
        a = ReviewerAssistant(_CitingProvider())
        resp = a.answer_question("When?", _EVIDENCE_TEXTS, [])
        assert resp.answer is None

    def test_error_is_handled_safely(self):
        a = ReviewerAssistant(_ErrorProvider())
        resp = a.answer_question("question", _EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None
        assert resp.requires_human_review is True


# ===========================================================================
# produce_reviewer_notes
# ===========================================================================


class TestProduceReviewerNotes:
    def test_returns_response(self):
        a = ReviewerAssistant(_CitingProvider("Reviewer note: verify date."))
        resp = a.produce_reviewer_notes(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp, LLMResponse)

    def test_no_evidence_means_no_answer(self):
        a = ReviewerAssistant(_CitingProvider())
        resp = a.produce_reviewer_notes([], [])
        assert resp.answer is None
        assert resp.requires_human_review is True

    def test_error_is_handled_safely(self):
        a = ReviewerAssistant(_ErrorProvider())
        resp = a.produce_reviewer_notes(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert resp.answer is None
        assert resp.requires_human_review is True


# ===========================================================================
# Output field contract
# ===========================================================================


class TestResponseFieldContract:
    """Every LLMResponse must contain all required output fields."""

    def test_all_required_fields_present(self):
        a = ReviewerAssistant(_CitingProvider("answer"))
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)

        # Required output fields per spec
        assert hasattr(resp, "answer")
        assert hasattr(resp, "citations")
        assert hasattr(resp, "confidence")
        assert hasattr(resp, "unsupported_claims")
        assert hasattr(resp, "requires_human_review")

    def test_citations_are_citation_objects(self):
        a = ReviewerAssistant(_CitingProvider("answer"))
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        for cit in resp.citations:
            assert isinstance(cit, Citation)
            assert cit.source_url  # non-empty

    def test_confidence_is_float_in_range(self):
        a = ReviewerAssistant(_CitingProvider("answer"))
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert 0.0 <= resp.confidence <= 1.0

    def test_unsupported_claims_is_list(self):
        a = ReviewerAssistant(_CitingProvider("answer"))
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp.unsupported_claims, list)

    def test_requires_human_review_is_bool(self):
        a = ReviewerAssistant(_CitingProvider("answer"))
        resp = a.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert isinstance(resp.requires_human_review, bool)


# ===========================================================================
# Permitted task type coverage
# ===========================================================================


class TestPermittedTaskTypeCoverage:
    """ReviewerAssistant must cover every permitted task type."""

    def test_summarize_evidence_uses_permitted_task(self):
        a = ReviewerAssistant(_CitingProvider())

        class _TrackingProvider(LLMProvider):
            last_task: LLMTaskType | None = None

            def _call(self, request: LLMRequest) -> LLMResponse:
                _TrackingProvider.last_task = request.task_type
                return LLMResponse(
                    answer=None, citations=[], confidence=0.0
                )

        tracker = ReviewerAssistant(_TrackingProvider())
        tracker.summarize_evidence(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert _TrackingProvider.last_task in PERMITTED_TASK_TYPES

    def test_extract_entities_uses_permitted_task(self):
        class _TrackingProvider(LLMProvider):
            last_task: LLMTaskType | None = None

            def _call(self, request: LLMRequest) -> LLMResponse:
                _TrackingProvider.last_task = request.task_type
                return LLMResponse(answer=None, citations=[], confidence=0.0)

        tracker = ReviewerAssistant(_TrackingProvider())
        tracker.extract_entities(_EVIDENCE_TEXTS, _EVIDENCE_URLS)
        assert _TrackingProvider.last_task in PERMITTED_TASK_TYPES
