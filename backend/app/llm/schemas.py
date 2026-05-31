"""LLM response/request schemas for the reviewer assistant boundary.

These schemas define the strict contract between the LLM layer and the rest
of the application.

Design rules:
  - Every LLMResponse MUST include citations.  No citations = no answer.
  - Every LLMResponse MUST include a confidence score in [0.0, 1.0].
  - unsupported_claims lists any claims in the answer not backed by citations.
  - requires_human_review is True if the response contains low-confidence claims
    or any unsupported claims.
  - The LLM layer NEVER:
      * publishes records
      * assigns guilt
      * infers criminality
      * scores dangerousness
      * makes legal conclusions
      * creates unsupported accusations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LLMTaskType(str, Enum):
    """Permitted LLM task types within the reviewer assistant boundary."""

    SUMMARIZE_EVIDENCE = "summarize_evidence"
    EXTRACT_ENTITIES = "extract_entities"       # names, dates, locations
    COMPARE_CLAIM_TO_SOURCE = "compare_claim_to_source"
    FLAG_MISSING_EVIDENCE = "flag_missing_evidence"
    DETECT_CONTRADICTIONS = "detect_contradictions"
    ANSWER_EVIDENCE_QUESTION = "answer_evidence_question"

    # Explicitly prohibited — these must never be created by production code.
    # Listed here so that test suites can verify they are rejected.
    PUBLISH_RECORD = "publish_record"             # PROHIBITED
    ASSIGN_GUILT = "assign_guilt"                  # PROHIBITED
    INFER_CRIMINALITY = "infer_criminality"        # PROHIBITED
    SCORE_DANGEROUSNESS = "score_dangerousness"    # PROHIBITED
    MAKE_LEGAL_CONCLUSION = "make_legal_conclusion"  # PROHIBITED


# Task types that the ReviewerAssistant is permitted to execute.
PERMITTED_TASK_TYPES: frozenset[LLMTaskType] = frozenset(
    {
        LLMTaskType.SUMMARIZE_EVIDENCE,
        LLMTaskType.EXTRACT_ENTITIES,
        LLMTaskType.COMPARE_CLAIM_TO_SOURCE,
        LLMTaskType.FLAG_MISSING_EVIDENCE,
        LLMTaskType.DETECT_CONTRADICTIONS,
        LLMTaskType.ANSWER_EVIDENCE_QUESTION,
    }
)

# Task types that are never permitted regardless of caller.
PROHIBITED_TASK_TYPES: frozenset[LLMTaskType] = frozenset(
    {
        LLMTaskType.PUBLISH_RECORD,
        LLMTaskType.ASSIGN_GUILT,
        LLMTaskType.INFER_CRIMINALITY,
        LLMTaskType.SCORE_DANGEROUSNESS,
        LLMTaskType.MAKE_LEGAL_CONCLUSION,
    }
)


@dataclass
class Citation:
    """A citation linking an LLM claim to a specific evidence source."""

    source_url: str
    """Direct URL to the source document."""

    quote: str | None = None
    """Verbatim quote or excerpt from the source (optional but encouraged)."""

    snapshot_hash: str | None = None
    """SHA-256 hash of the source snapshot at time of retrieval (optional)."""

    fetched_at: str | None = None
    """ISO-8601 timestamp when the source was fetched."""


@dataclass
class LLMRequest:
    """A request to the LLM reviewer assistant."""

    task_type: LLMTaskType
    """The type of task to perform (must be in PERMITTED_TASK_TYPES)."""

    prompt: str
    """The question or instruction to the LLM."""

    evidence_texts: list[str] = field(default_factory=list)
    """Source texts the LLM must ground its answer in.

    At least one evidence text should be provided for evidence-grounded tasks.
    The LLM must not make claims unsupported by these texts.
    """

    evidence_urls: list[str] = field(default_factory=list)
    """URLs corresponding to evidence_texts (used to populate citations)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Optional additional context (e.g., jurisdiction, record type)."""


@dataclass
class LLMResponse:
    """A response from the LLM reviewer assistant.

    Invariants:
      - answer is None if there are no citations.
      - confidence is in [0.0, 1.0].
      - requires_human_review is True if:
          * confidence < 0.7
          * there are any unsupported_claims
          * no citations were produced
    """

    answer: str | None
    """The LLM's answer, or None if no citations support it."""

    citations: list[Citation] = field(default_factory=list)
    """Citations that support the answer.  Empty → answer must be None."""

    confidence: float = 0.0
    """Confidence in [0.0, 1.0].  Below 0.7 triggers requires_human_review."""

    unsupported_claims: list[str] = field(default_factory=list)
    """Claims in the answer that are NOT backed by any citation."""

    requires_human_review: bool = True
    """True if the response should not be used without human verification."""

    task_type: LLMTaskType | None = None
    """The task type this response corresponds to."""

    model_name: str | None = None
    """The model that produced this response (for audit/traceability)."""

    raw_response: str | None = None
    """Raw model output, preserved for audit purposes."""

    def __post_init__(self) -> None:
        # Enforce: citations must have non-empty source_url to count
        valid_citations = [c for c in self.citations if c.source_url]
        self.citations = valid_citations
        # Enforce: no citations → answer must be None
        if not self.citations:
            self.answer = None
            self.requires_human_review = True
        # Enforce: unsupported claims → requires human review
        if self.unsupported_claims:
            self.requires_human_review = True
        # Enforce: low confidence → requires human review
        if self.confidence < 0.7:
            self.requires_human_review = True
        # Clamp confidence to valid range
        self.confidence = max(0.0, min(1.0, self.confidence))
