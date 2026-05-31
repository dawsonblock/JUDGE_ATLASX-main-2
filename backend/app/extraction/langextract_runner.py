"""LangExtract runner — optional extraction worker.

Reads a ``SourceSnapshot`` and produces a list of ``GroundedExtraction``
objects.  ``langextract`` is a **soft dependency**: this module is safe to
import without it installed; the exception is raised only when
``run_extraction()`` is actually called.

Safety invariants enforced here
--------------------------------
- ``fetch_urls=False`` is **always** passed to langextract — no network access.
- Any result without a ``char_interval`` raises ``UngroundedExtractionError``.
- Any requested class not in ``APPROVED_CLASSES`` raises
  ``UnknownExtractionClassError`` before langextract is ever called.
- Confidence is clamped to ``CONFIDENCE_CAPS[cls]`` before returning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.extraction.contracts import (
    GroundedExtraction,
    UngroundedExtractionError,
    UnknownExtractionClassError,
)
from app.extraction.prompt_specs import APPROVED_CLASSES, CONFIDENCE_CAPS, DEFAULT_CONFIDENCE_CAP

if TYPE_CHECKING:
    from app.models.entities import SourceSnapshot


def run_extraction(
    snapshot: SourceSnapshot,
    classes: list[str],
    model_id: str,
) -> list[GroundedExtraction]:
    """Run LangExtract over *snapshot* for the given extraction *classes*.

    Parameters
    ----------
    snapshot:
        The ``SourceSnapshot`` whose ``extracted_text`` will be analysed.
        ``snapshot.id`` must be a persisted integer (not ``None``).
    classes:
        List of extraction class names to request.  Each must be a key in
        ``APPROVED_CLASSES``; an ``UnknownExtractionClassError`` is raised
        immediately otherwise.
    model_id:
        Identifier of the LangExtract model to use; stored verbatim on each
        ``GroundedExtraction`` for audit purposes.

    Returns
    -------
    list[GroundedExtraction]
        One entry per grounded extraction result.  Results lacking a
        ``char_interval`` are rejected with ``UngroundedExtractionError``.

    Raises
    ------
    UnknownExtractionClassError
        If any class in *classes* is not in ``APPROVED_CLASSES``.
    UngroundedExtractionError
        If LangExtract returns any result without a ``char_interval``.
    ImportError
        If ``langextract`` is not installed.
    ValueError
        If ``snapshot.extracted_text`` is ``None`` or empty.
    """
    # Validate classes FIRST — before importing langextract so callers get a
    # clear error even in environments without the optional dependency.
    for cls in classes:
        if cls not in APPROVED_CLASSES:
            raise UnknownExtractionClassError(
                f"Extraction class {cls!r} is not in APPROVED_CLASSES. "
                f"Permitted classes: {sorted(APPROVED_CLASSES)}"
            )

    if not snapshot.extracted_text:
        raise ValueError(
            f"SourceSnapshot id={snapshot.id} has no extracted_text — "
            "cannot run extraction on empty content."
        )

    # Lazy import — optional dependency.
    try:
        import langextract  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "langextract is not installed.  Install it with: "
            "pip install langextract\n"
            "The rest of the application works without it."
        ) from exc

    extracted_text: str = snapshot.extracted_text
    results: list[GroundedExtraction] = []

    for cls in classes:
        spec = APPROVED_CLASSES[cls]
        cap = CONFIDENCE_CAPS.get(cls, DEFAULT_CONFIDENCE_CAP)

        raw_results = langextract.extract(
            text=extracted_text,
            extraction_class=cls,
            model_id=model_id,
            prompt_hint=spec["prompt_hint"],
            fetch_urls=False,  # SAFETY: never allow network access from runner
        )

        for raw in raw_results:
            char_interval = getattr(raw, "char_interval", None)
            if char_interval is None:
                raise UngroundedExtractionError(
                    f"LangExtract returned a result for class {cls!r} without a "
                    f"char_interval.  Only grounded extractions may be persisted. "
                    f"Raw result: {raw!r}"
                )

            span_start: int = char_interval[0]
            span_end: int = char_interval[1]
            span_text = extracted_text[span_start:span_end]

            raw_confidence: float = float(getattr(raw, "confidence", 0.0))
            confidence = min(raw_confidence, cap)

            # Collect any attributes beyond the core fields.
            attrs: dict = {}
            for attr in ("attributes", "extra", "metadata"):
                val = getattr(raw, attr, None)
                if isinstance(val, dict):
                    attrs = val
                    break

            results.append(
                GroundedExtraction(
                    source_snapshot_id=snapshot.id,
                    extraction_class=cls,
                    text=span_text,
                    span_start=span_start,
                    span_end=span_end,
                    attributes=attrs,
                    model_id=model_id,
                    confidence=confidence,
                )
            )

    return results
