"""Data contracts for the LangExtract extraction pipeline.

These types are in a separate module so callers can import them without
requiring ``langextract`` to be installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GroundedExtraction:
    """A single extraction result grounded to a char-level span.

    Every field is immutable after construction.  The ``text`` field holds the
    verbatim span text (``extracted_text[span_start:span_end]``); callers MUST
    verify this matches the source before persisting.

    Invariants:
    - ``span_start < span_end``
    - ``text`` is a non-empty string
    - ``confidence`` is in [0.0, 1.0] (enforced by the runner via CONFIDENCE_CAPS)
    - ``source_snapshot_id`` remains consistent through the full write path
    """

    source_snapshot_id: int
    """Primary key of the SourceSnapshot from which this extraction originates."""

    extraction_class: str
    """Extraction class name; must be a key in APPROVED_CLASSES."""

    text: str
    """Verbatim span text from the source (extracted_text[span_start:span_end])."""

    span_start: int
    """Inclusive character offset (0-based) of the span in extracted_text."""

    span_end: int
    """Exclusive character offset (0-based) of the span in extracted_text."""

    attributes: dict[str, Any]
    """Additional structured attributes returned by the model."""

    model_id: str
    """Identifier of the LangExtract model used for this extraction."""

    confidence: float
    """Confidence score, clamped to CONFIDENCE_CAPS[extraction_class]."""


class UngroundedExtractionError(ValueError):
    """Raised when LangExtract returns a result without a ``char_interval``.

    The runner rejects all such results — only span-grounded extractions may
    be persisted as evidence.
    """


class UnknownExtractionClassError(ValueError):
    """Raised when an extraction class is not in APPROVED_CLASSES.

    Callers must only request classes from the approved list to prevent
    open-ended extraction.
    """
