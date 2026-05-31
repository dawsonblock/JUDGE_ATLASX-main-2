"""Tests for claim evidence links (Phase 4).

Tests evidence link validation, orphan detection, and support type constraints.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim, MemoryEvidenceLink, SourceSnapshot
from app.memory.claim_evidence import (
    validate_public_claim_has_evidence,
    detect_orphan_evidence_links,
    create_evidence_link,
)
from app.db.session import SessionLocal


class TestEvidenceLinkValidation:
    """Test evidence link validation logic."""

    def test_public_claim_requires_supporting_evidence(self, db_session):
        """Test that public claims must have supporting evidence."""
        # Create a public claim
        claim = MemoryClaim(
            claim_key="test_claim_1_public",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            status="public",
        )
        db_session.add(claim)
        db_session.commit()

        # Without evidence, validation should fail
        assert not validate_public_claim_has_evidence(claim.id, db_session)

        # Add supporting evidence
        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
        )
        db_session.add(snapshot)
        db_session.commit()

        evidence = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            evidence_checksum="evidence_hash",
            support_type="supports",
            confidence=0.8,
        )
        db_session.add(evidence)
        db_session.commit()

        # With evidence, validation should pass
        assert validate_public_claim_has_evidence(claim.id, db_session)

    def test_non_public_claim_does_not_require_evidence(self, db_session):
        """Test that non-public claims don't require evidence."""
        claim = MemoryClaim(
            claim_key="test_claim_1_draft",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
            status="draft",
        )
        db_session.add(claim)
        db_session.commit()

        # Draft claims should pass validation even without evidence
        assert validate_public_claim_has_evidence(claim.id, db_session)


class TestOrphanEvidenceDetection:
    """Test orphan evidence link detection."""

    def test_detect_orphan_links(self, db_session):
        """Test detection of evidence links with missing references."""
        # Create a claim and snapshot
        claim = MemoryClaim(
            claim_key="test_claim_1_orphan",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
        )
        db_session.add(snapshot)
        db_session.commit()

        # Create a valid evidence link
        valid_link = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            evidence_checksum="valid_hash",
        )
        db_session.add(valid_link)
        db_session.commit()

        # Create an orphan link (non-existent claim)
        orphan_link = MemoryEvidenceLink(
            claim_id=999999,
            snapshot_id=snapshot.id,
            evidence_checksum="orphan_hash",
        )
        db_session.add(orphan_link)
        db_session.commit()

        orphans = detect_orphan_evidence_links(db_session)
        assert len(orphans) == 1
        assert orphans[0].id == orphan_link.id


class TestEvidenceLinkCreation:
    """Test evidence link creation with validation."""

    def test_create_evidence_link_valid(self, db_session):
        """Test creating a valid evidence link."""
        claim = MemoryClaim(
            claim_key="test_claim_1_create_valid",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
        )
        db_session.add(snapshot)
        db_session.commit()

        link = create_evidence_link(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            support_type="supports",
            quote_text="Test quote",
            char_start=10,
            char_end=20,
            page_number=1,
            confidence=0.8,
            db=db_session,
        )

        assert link.claim_id == claim.id
        assert link.snapshot_id == snapshot.id
        assert link.support_type == "supports"
        assert link.quote_text == "Test quote"
        assert link.char_start == 10
        assert link.char_end == 20
        assert link.page_number == 1
        assert link.confidence == 0.8

    def test_create_evidence_link_invalid_support_type(self, db_session):
        """Test that invalid support_type raises ValueError."""
        claim = MemoryClaim(
            claim_key="test_claim_1_invalid_support",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
        )
        db_session.add(snapshot)
        db_session.commit()

        with pytest.raises(ValueError) as exc_info:
            create_evidence_link(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                support_type="invalid_type",
                db=db_session,
            )

        assert "Invalid support_type" in str(exc_info.value)

    def test_create_evidence_link_invalid_confidence(self, db_session):
        """Test that confidence outside 0.0-1.0 range raises ValueError."""
        claim = MemoryClaim(
            claim_key="test_claim_1_invalid_type",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
        )
        db_session.add(snapshot)
        db_session.commit()

        with pytest.raises(ValueError) as exc_info:
            create_evidence_link(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                support_type="supports",
                confidence=1.5,
                db=db_session,
            )

        assert "Confidence must be between 0.0 and 1.0" in str(exc_info.value)

    def test_create_evidence_link_invalid_char_offsets(self, db_session):
        """Test that invalid character offsets raise ValueError."""
        claim = MemoryClaim(
            claim_key="test_claim_1_invalid_offsets",
            claim_type="test",
            entity_id=1,
            claim_value="Test value",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="test_source",
            snapshot_hash="test_hash",
            content="Test content",
        )
        db_session.add(snapshot)
        db_session.commit()

        # Test start > end
        with pytest.raises(ValueError) as exc_info:
            create_evidence_link(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                support_type="supports",
                char_start=20,
                char_end=10,
                db=db_session,
            )

        assert "Character start must be <= end" in str(exc_info.value)

        # Test negative offsets
        with pytest.raises(ValueError) as exc_info:
            create_evidence_link(
                claim_id=claim.id,
                snapshot_id=snapshot.id,
                support_type="supports",
                char_start=-1,
                char_end=10,
                db=db_session,
            )

        assert "Character offsets must be non-negative" in str(exc_info.value)


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
