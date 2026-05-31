"""LangExtract integration — optional extraction worker.

This package is an **optional** feature.  The application starts normally
even when ``langextract`` is not installed.  Enable the feature by making
``langextract`` available in the runtime environment.

Public API (safe to import unconditionally)::

    from app.extraction.contracts import (
        GroundedExtraction,
        UngroundedExtractionError,
        UnknownExtractionClassError,
    )
    from app.extraction.prompt_specs import APPROVED_CLASSES, CONFIDENCE_CAPS

The runner and mapper are only safe to import when langextract is installed::

    from app.extraction.langextract_runner import run_extraction
    from app.extraction.review_item_mapper import map_to_review_items

Safety invariants:
- fetch_urls is ALWAYS False — the runner never fetches external URLs.
- Any LangExtract result without ``char_interval`` raises
  ``UngroundedExtractionError`` — ungrounded claims are never persisted.
- All produced ReviewItems have ``status=PENDING`` and
  ``public_visibility=False`` — nothing is auto-published.
"""
