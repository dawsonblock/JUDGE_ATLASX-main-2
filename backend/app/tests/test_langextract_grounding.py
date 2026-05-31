"""Tests for the LangExtract extraction pipeline (Phase 1).

Coverage requirements from spec
---------------------------------
1. Ungrounded extraction (missing char_interval) → UngroundedExtractionError
2. Grounded extraction → MemoryClaim + MemoryEvidenceLink created
3. ReviewItem has status=PENDING
4. public_visibility=False on ReviewItem
5. source_snapshot_id preserved end-to-end
6. span_start / span_end / text match verbatim
7. fetch_urls=False is always passed to langextract
8. Unknown extraction class → UnknownExtractionClassError
9. Application starts normally without langextract installed
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    snapshot_id: int = 42,
    text: str = "Alice Smith was arrested in Regina.",
) -> MagicMock:
    snap = MagicMock()
    snap.id = snapshot_id
    snap.extracted_text = text
    return snap


def _make_raw_result(char_interval=(0, 11), confidence: float = 0.9) -> SimpleNamespace:
    """Simulate a single result object returned by langextract.extract()."""
    return SimpleNamespace(
        char_interval=char_interval,
        confidence=confidence,
        attributes={"raw": "test"},
        extra=None,
        metadata=None,
    )


def _make_fake_langextract(results_by_class: dict) -> ModuleType:
    """Create a fake langextract module returning pre-defined results."""
    mod = ModuleType("langextract")

    def _extract(text, extraction_class, model_id, prompt_hint, fetch_urls):  # noqa: ANN001
        _extract.last_call_kwargs = {
            "text": text,
            "extraction_class": extraction_class,
            "model_id": model_id,
            "prompt_hint": prompt_hint,
            "fetch_urls": fetch_urls,
        }
        return results_by_class.get(extraction_class, [])

    _extract.last_call_kwargs = {}
    mod.extract = _extract
    return mod


# ---------------------------------------------------------------------------
# Test 8 — Unknown class → UnknownExtractionClassError (no langextract needed)
# ---------------------------------------------------------------------------

class TestUnknownExtractionClass:
    def test_unknown_class_raises_before_import(self) -> None:
        """UnknownExtractionClassError is raised before langextract is imported."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.contracts import UnknownExtractionClassError

        snap = _make_snapshot()
        with pytest.raises(UnknownExtractionClassError, match="not in APPROVED_CLASSES"):
            run_extraction(snap, classes=["totally_unknown_class"], model_id="test")


# ---------------------------------------------------------------------------
# Test 9 — App starts without langextract (ImportError at call time only)
# ---------------------------------------------------------------------------

class TestOptionalDependency:
    def test_import_extraction_package_without_langextract(self) -> None:
        """The extraction package is importable even without langextract."""
        # Remove langextract from sys.modules if present, simulate absence.
        langextract_saved = sys.modules.pop("langextract", None)
        try:
            # These imports must succeed even without langextract installed.
            import app.extraction.contracts as _c  # noqa: F401
            import app.extraction.prompt_specs as _p  # noqa: F401
            import app.extraction.review_item_mapper as _r  # noqa: F401
        finally:
            if langextract_saved is not None:
                sys.modules["langextract"] = langextract_saved

    def test_run_extraction_raises_import_error_without_langextract(self) -> None:
        """run_extraction raises ImportError when langextract is absent."""
        from app.extraction.langextract_runner import run_extraction

        langextract_saved = sys.modules.pop("langextract", None)
        try:
            snap = _make_snapshot()
            with pytest.raises(ImportError, match="langextract is not installed"):
                run_extraction(snap, classes=["person_name"], model_id="test")
        finally:
            if langextract_saved is not None:
                sys.modules["langextract"] = langextract_saved


# ---------------------------------------------------------------------------
# Test 1 — Ungrounded extraction → UngroundedExtractionError
# ---------------------------------------------------------------------------

class TestUngroundedExtraction:
    def test_missing_char_interval_raises(self) -> None:
        """A result without char_interval raises UngroundedExtractionError."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.contracts import UngroundedExtractionError

        ungrounded = SimpleNamespace(
            char_interval=None,
            confidence=0.8,
            attributes={},
            extra=None,
            metadata=None,
        )
        fake_langextract = _make_fake_langextract({"person_name": [ungrounded]})

        snap = _make_snapshot()
        with patch.dict(sys.modules, {"langextract": fake_langextract}):
            with pytest.raises(UngroundedExtractionError, match="char_interval"):
                run_extraction(snap, classes=["person_name"], model_id="test-model")


# ---------------------------------------------------------------------------
# Tests 2, 3, 4, 5, 6, 7 — Happy path
# ---------------------------------------------------------------------------

class TestGroundedExtractionHappyPath:
    TEXT = "Alice Smith was arrested in Regina on March 5, 2024."
    SNAPSHOT_ID = 99
    MODEL_ID = "test-model-v1"

    def _setup(self):
        """Return snapshot, fake langextract, and a grounded result."""
        raw_result = _make_raw_result(char_interval=(0, 11), confidence=0.9)
        fake_le = _make_fake_langextract({"person_name": [raw_result]})
        snap = _make_snapshot(snapshot_id=self.SNAPSHOT_ID, text=self.TEXT)
        return snap, fake_le, raw_result

    # ------------------------------------------------------------------
    # run_extraction output validation
    # ------------------------------------------------------------------

    def test_grounded_extraction_returns_list(self) -> None:
        """run_extraction returns a non-empty list for a valid grounded result."""
        from app.extraction.langextract_runner import run_extraction

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            results = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)
        assert len(results) == 1

    def test_span_text_matches_verbatim(self) -> None:
        """Test 6 — span text is extracted verbatim from extracted_text."""
        from app.extraction.langextract_runner import run_extraction

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            results = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)
        g = results[0]
        # char_interval=(0,11) → "Alice Smith"
        assert g.text == self.TEXT[0:11]
        assert g.span_start == 0
        assert g.span_end == 11

    def test_source_snapshot_id_preserved(self) -> None:
        """Test 5 — source_snapshot_id from snapshot is preserved in result."""
        from app.extraction.langextract_runner import run_extraction

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            results = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)
        assert results[0].source_snapshot_id == self.SNAPSHOT_ID

    def test_confidence_clamped_by_cap(self) -> None:
        """Confidence is clamped to CONFIDENCE_CAPS['person_name'] = 0.60."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.prompt_specs import CONFIDENCE_CAPS

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            results = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)
        cap = CONFIDENCE_CAPS["person_name"]
        assert results[0].confidence <= cap

    def test_fetch_urls_is_always_false(self) -> None:
        """Test 7 — fetch_urls=False is always passed to langextract.extract."""
        from app.extraction.langextract_runner import run_extraction

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)
        assert fake_le.extract.last_call_kwargs["fetch_urls"] is False

    # ------------------------------------------------------------------
    # map_to_review_items output validation
    # ------------------------------------------------------------------

    def test_review_item_status_pending(self) -> None:
        """Test 3 — ReviewItem.status is PENDING."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.review_item_mapper import map_to_review_items
        from app.ingestion.statuses import PENDING

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            extractions = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)

        db = MagicMock(spec=["add", "flush"])
        # Simulate flush populating claim.id
        added_objects: list = []

        def _add_side_effect(obj):
            added_objects.append(obj)
            if hasattr(obj, "id") and obj.id is None:
                object.__setattr__(obj, "id", 1) if isinstance(obj, object) else None
        db.add.side_effect = added_objects.append

        # We need claim.id to be set when flush() is called.
        # Patch MemoryClaim so flush sets id=1.
        claim_mock = MagicMock()
        claim_mock.id = 1
        claim_mock.claim_key = "aabbcc"

        with patch("app.extraction.review_item_mapper.MemoryClaim", return_value=claim_mock):
            review_items = map_to_review_items(extractions, db)

        assert len(review_items) == 1
        ri = review_items[0]
        assert ri.status == PENDING

    def test_review_item_public_visibility_false(self) -> None:
        """Test 4 — ReviewItem.public_visibility is False."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.review_item_mapper import map_to_review_items

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            extractions = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)

        db = MagicMock(spec=["add", "flush"])
        claim_mock = MagicMock()
        claim_mock.id = 1
        claim_mock.claim_key = "aabbcc"

        with patch("app.extraction.review_item_mapper.MemoryClaim", return_value=claim_mock):
            review_items = map_to_review_items(extractions, db)

        assert review_items[0].public_visibility is False

    def test_memory_claim_created_with_sentinel_entity_id(self) -> None:
        """Test 2 — MemoryClaim is created; entity_id=0 is the pre-review sentinel."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.review_item_mapper import map_to_review_items

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            extractions = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)

        db = MagicMock(spec=["add", "flush"])

        created_claims: list = []

        def _capture_claim(**kwargs):
            obj = MagicMock()
            obj.id = 1
            obj.claim_key = "aabbcc"
            created_claims.append(kwargs)
            return obj

        with patch("app.extraction.review_item_mapper.MemoryClaim", side_effect=_capture_claim):
            map_to_review_items(extractions, db)

        assert len(created_claims) == 1
        assert created_claims[0]["entity_id"] == 0, "entity_id must be 0 (pre-review sentinel)"

    def test_memory_evidence_link_snapshot_id(self) -> None:
        """Test 5 (link) — MemoryEvidenceLink.snapshot_id matches source_snapshot_id."""
        from app.extraction.langextract_runner import run_extraction
        from app.extraction.review_item_mapper import map_to_review_items

        snap, fake_le, _ = self._setup()
        with patch.dict(sys.modules, {"langextract": fake_le}):
            extractions = run_extraction(snap, classes=["person_name"], model_id=self.MODEL_ID)

        created_links: list = []

        def _capture_link(**kwargs):
            obj = MagicMock()
            created_links.append(kwargs)
            return obj

        db = MagicMock(spec=["add", "flush"])
        claim_mock = MagicMock()
        claim_mock.id = 55
        claim_mock.claim_key = "deadbeef"

        with patch("app.extraction.review_item_mapper.MemoryClaim", return_value=claim_mock):
            with patch(
                "app.extraction.review_item_mapper.MemoryEvidenceLink",
                side_effect=_capture_link,
            ):
                map_to_review_items(extractions, db)

        assert len(created_links) == 1
        assert created_links[0]["snapshot_id"] == self.SNAPSHOT_ID
