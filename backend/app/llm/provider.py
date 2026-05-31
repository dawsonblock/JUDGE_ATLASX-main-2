"""Abstract LLM provider interface.

All LLM backends must implement this interface.  The ReviewerAssistant
depends only on LLMProvider — never on a concrete implementation.

Design rules (enforced here):
  - Prohibited task types are rejected before the request reaches any provider.
  - No provider may return an answer without citations.
  - Providers are stateless — each call is independent.
"""

from __future__ import annotations

import abc

from app.llm.schemas import (
    LLMRequest,
    LLMResponse,
    PROHIBITED_TASK_TYPES,
)


class ProhibitedTaskError(ValueError):
    """Raised when a caller attempts a prohibited LLM task type."""


class LLMProvider(abc.ABC):
    """Abstract base for all LLM provider implementations.

    Subclasses implement ``_call(request)`` and return an ``LLMResponse``.
    This base class enforces the safety boundary before delegating.
    """

    @property
    def provider_name(self) -> str:
        """Human-readable name for logging and audit trails."""
        return self.__class__.__name__

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Run the LLM request with safety enforcement.

        Raises:
            ProhibitedTaskError: If request.task_type is in PROHIBITED_TASK_TYPES.

        Returns:
            LLMResponse with answer=None if no citations could be produced.
        """
        self._enforce_task_type(request)
        response = self._call(request)
        # Apply the citation lock: no citations → no answer
        if not response.citations:
            response = LLMResponse(
                answer=None,
                citations=[],
                confidence=response.confidence,
                unsupported_claims=response.unsupported_claims,
                requires_human_review=True,
                task_type=request.task_type,
                model_name=response.model_name,
                raw_response=response.raw_response,
            )
        return response

    @abc.abstractmethod
    def _call(self, request: LLMRequest) -> LLMResponse:
        """Execute the actual LLM call.  Subclasses implement this method.

        Implementations MUST:
          - Set citations from the provided evidence_texts / evidence_urls.
          - Set confidence based on how well the answer is grounded.
          - Populate unsupported_claims for any claim not backed by evidence.
          - NEVER assign guilt, infer criminality, or make legal conclusions.
        """

    @staticmethod
    def _enforce_task_type(request: LLMRequest) -> None:
        """Raise ProhibitedTaskError if the task type is not permitted."""
        if request.task_type in PROHIBITED_TASK_TYPES:
            raise ProhibitedTaskError(
                f"Task type '{request.task_type.value}' is prohibited. "
                "The LLM layer may not publish records, assign guilt, "
                "infer criminality, score dangerousness, or make legal conclusions."
            )
