"""Reviewer assistant — the public entry point for LLM-assisted review.

The ReviewerAssistant is the ONLY way production code should access LLM
functionality.  It enforces all safety boundaries:

Permitted:
  - summarize evidence
  - extract names / dates / locations from evidence
  - compare claim to source text
  - flag missing evidence
  - detect contradictions between sources
  - answer evidence questions with citations

NEVER permitted:
  - publish records
  - assign guilt
  - infer criminality
  - score dangerousness
  - make legal conclusions
  - create unsupported accusations

Hard rule: No citation → no answer.
If the LLM cannot cite a source, the answer field will be None.
The response always includes requires_human_review.
"""

from __future__ import annotations

import logging

from app.llm.provider import LLMProvider, ProhibitedTaskError
from app.llm.schemas import (
    LLMRequest,
    LLMResponse,
    LLMTaskType,
    PERMITTED_TASK_TYPES,
    PROHIBITED_TASK_TYPES,
    Citation,
)

logger = logging.getLogger(__name__)


class ReviewerAssistant:
    """Orchestrates citation-locked LLM reviewer assistance.

    Usage::

        provider = OllamaProvider()          # or OpenAIProvider()
        assistant = ReviewerAssistant(provider)

        response = assistant.summarize_evidence(
            evidence_texts=["The court ruled that..."],
            evidence_urls=["https://www.canlii.org/..."],
        )
        if response.answer is not None:
            # answer is citation-grounded
            print(response.answer)
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    # -----------------------------------------------------------------------
    # Public API — one method per permitted task type
    # -----------------------------------------------------------------------

    def summarize_evidence(
        self,
        evidence_texts: list[str],
        evidence_urls: list[str],
        context: str | None = None,
    ) -> LLMResponse:
        """Summarize the provided evidence texts.

        Returns an LLMResponse with answer=None if no citations can be formed.
        """
        prompt = "Summarize the key facts from the evidence texts provided."
        if context:
            prompt = f"{context}\n\n{prompt}"
        return self._run(
            LLMTaskType.SUMMARIZE_EVIDENCE,
            prompt,
            evidence_texts,
            evidence_urls,
        )

    def extract_entities(
        self,
        evidence_texts: list[str],
        evidence_urls: list[str],
    ) -> LLMResponse:
        """Extract named entities (people, dates, locations) from evidence."""
        return self._run(
            LLMTaskType.EXTRACT_ENTITIES,
            "List all named people, dates, and locations mentioned in the evidence. "
            "Include only what is explicitly stated in the evidence.",
            evidence_texts,
            evidence_urls,
        )

    def compare_claim_to_source(
        self,
        claim: str,
        evidence_texts: list[str],
        evidence_urls: list[str],
    ) -> LLMResponse:
        """Compare a claim to the source evidence and indicate support level."""
        return self._run(
            LLMTaskType.COMPARE_CLAIM_TO_SOURCE,
            f"Does the evidence support this claim: '{claim}'? "
            "State 'supported', 'contradicted', or 'not mentioned', "
            "and cite the specific evidence passage.",
            evidence_texts,
            evidence_urls,
        )

    def flag_missing_evidence(
        self,
        evidence_texts: list[str],
        evidence_urls: list[str],
        claim: str | None = None,
    ) -> LLMResponse:
        """Identify what evidence would be needed to support a claim or the overall record."""
        prompt = (
            f"What evidence is missing or needed to verify this claim: '{claim}'? "
            "Do NOT make assumptions. Only assess gaps relative to the provided evidence."
            if claim
            else "What key evidence is missing or would be needed to verify the facts in this record? "
            "Do NOT make assumptions. Only assess gaps relative to the provided evidence."
        )
        return self._run(
            LLMTaskType.FLAG_MISSING_EVIDENCE,
            prompt,
            evidence_texts,
            evidence_urls,
        )

    def detect_contradictions(
        self,
        evidence_texts: list[str],
        evidence_urls: list[str],
    ) -> LLMResponse:
        """Detect contradictions between the provided evidence sources."""
        return self._run(
            LLMTaskType.DETECT_CONTRADICTIONS,
            "Identify any factual contradictions between the evidence sources. "
            "List each contradiction with the specific passages that conflict.",
            evidence_texts,
            evidence_urls,
        )

    def answer_question(
        self,
        question: str,
        evidence_texts: list[str],
        evidence_urls: list[str],
    ) -> LLMResponse:
        """Answer a specific question using only the provided evidence."""
        return self._run(
            LLMTaskType.ANSWER_EVIDENCE_QUESTION,
            question,
            evidence_texts,
            evidence_urls,
        )

    def produce_reviewer_notes(
        self,
        evidence_texts: list[str],
        evidence_urls: list[str],
    ) -> LLMResponse:
        """Produce structured notes for a human reviewer based on the evidence.

        Notes may include: key facts, gaps, flags, and recommended follow-up actions.
        The LLM must only reference what is explicitly in the evidence texts.
        """
        return self._run(
            LLMTaskType.SUMMARIZE_EVIDENCE,
            "Produce structured reviewer notes from the evidence: "
            "(1) Key established facts with citations. "
            "(2) Factual gaps or missing evidence. "
            "(3) Flags for human attention. "
            "(4) Recommended follow-up actions. "
            "Do NOT draw legal conclusions or assign fault.",
            evidence_texts,
            evidence_urls,
        )

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _run(
        self,
        task_type: LLMTaskType,
        prompt: str,
        evidence_texts: list[str],
        evidence_urls: list[str],
    ) -> LLMResponse:
        """Execute a task through the safety-enforced provider layer."""
        if task_type in PROHIBITED_TASK_TYPES:
            raise ProhibitedTaskError(
                f"Task type '{task_type.value}' is not permitted in the reviewer assistant."
            )
        if task_type not in PERMITTED_TASK_TYPES:
            raise ValueError(
                f"Unknown or unsupported task type: '{task_type.value}'"
            )

        request = LLMRequest(
            task_type=task_type,
            prompt=prompt,
            evidence_texts=evidence_texts,
            evidence_urls=evidence_urls,
        )

        logger.info(
            "ReviewerAssistant: task=%s provider=%s evidence_count=%d",
            task_type.value,
            self._provider.provider_name,
            len(evidence_texts),
        )

        try:
            response = self._provider.complete(request)
        except ProhibitedTaskError:
            raise
        except Exception as exc:
            logger.exception("LLM provider error: %s", exc)
            response = LLMResponse(
                answer=None,
                citations=[],
                confidence=0.0,
                unsupported_claims=[f"provider_error: {exc}"],
                requires_human_review=True,
                task_type=task_type,
            )

        # Final safety check: ensure no prohibited content in the answer
        if response.answer:
            response = self._redact_prohibited_content(response)

        return response

    @staticmethod
    def _redact_prohibited_content(response: LLMResponse) -> LLMResponse:
        """Ensure the answer contains no prohibited legal conclusions.

        This is a last-resort guard.  Well-behaved providers should never
        produce prohibited content if the system prompt is correct.
        """
        _PROHIBITED_PHRASES = [
            "is guilty",
            "is not guilty",
            "found guilty",
            "convicted of",
            "is a criminal",
            "committed the crime",
            "should be jailed",
            "should be convicted",
            "is dangerous",
            "poses a danger",
            "is a threat",
            "is likely to reoffend",
            "is criminally liable",
            "i conclude that",
            "legal conclusion",
            "the court must",
            "the court should",
        ]
        if response.answer is None:
            return response

        lower = response.answer.lower()
        for phrase in _PROHIBITED_PHRASES:
            if phrase in lower:
                logger.warning(
                    "LLM response contained prohibited phrase '%s'; suppressing answer",
                    phrase,
                )
                return LLMResponse(
                    answer=None,
                    citations=response.citations,
                    confidence=0.0,
                    unsupported_claims=response.unsupported_claims + ["prohibited_legal_conclusion"],
                    requires_human_review=True,
                    task_type=response.task_type,
                    model_name=response.model_name,
                    raw_response=response.raw_response,
                )
        return response
