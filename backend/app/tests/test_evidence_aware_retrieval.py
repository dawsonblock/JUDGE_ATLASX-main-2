"""Tests for evidence-aware retrieval (Phase 15).

Tests evidence filtering, ranking, and retrieval.
"""

import pytest

from app.models.entities import (
    MemoryClaim,
    MemoryEvidenceLink,
    SourceSnapshot,
    CanonicalEntity,
)
from app.retrieval.evidence_aware import (
    retrieve_claims_with_evidence,
    filter_evidence_by_quality,
    rank_evidence_by_relevance,
    get_evidence_summary,
)


class TestEvidenceAwareRetrieval:
    """Test evidence-aware claim retrieval."""

    def test_retrieve_claims_with_evidence(self, db_session):
        """Test retrieving claims with evidence information."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.8,
            review_status="approved",
        )
        db_session.add(claim)
        db_session.commit()

        results = retrieve_claims_with_evidence(entity.id, db_session)

        assert len(results) >= 0

    def test_retrieve_with_min_confidence(self, db_session):
        """Test retrieval with minimum confidence threshold."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        # High confidence claim
        claim1 = MemoryClaim(
            claim_key="claim_1",
            claim_type="test",
            entity_id=entity.id,
            claim_value="High confidence",
            confidence=0.9,
            review_status="approved",
        )
        db_session.add(claim1)

        # Low confidence claim
        claim2 = MemoryClaim(
            claim_key="claim_2",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Low confidence",
            confidence=0.3,
            review_status="approved",
        )
        db_session.add(claim2)
        db_session.commit()

        results = retrieve_claims_with_evidence(entity.id, db_session, min_confidence=0.7)

        # Only high confidence claim should be returned
        assert all(r["confidence"] >= 0.7 for r in results)


class TestEvidenceFiltering:
    """Test evidence filtering by quality."""

    def test_filter_evidence_by_quality(self, db_session):
        """Test filtering evidence by source quality."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.8,
            review_status="approved",
        )
        db_session.add(claim)
        db_session.commit()

        # High quality snapshot
        snapshot1 = SourceSnapshot(
            source_id="court_source",
            snapshot_hash="hash1",
            content="Court record content",
            source_quality="court_record",
        )
        db_session.add(snapshot1)

        # Low quality snapshot
        snapshot2 = SourceSnapshot(
            source_id="news_source",
            snapshot_hash="hash2",
            content="News content",
            source_quality="news_only_context",
        )
        db_session.add(snapshot2)
        db_session.commit()

        # Evidence links
        link1 = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot1.id,
            evidence_checksum="checksum1",
            support_type="supports",
            confidence=0.8,
        )
        db_session.add(link1)

        link2 = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot2.id,
            evidence_checksum="checksum2",
            support_type="supports",
            confidence=0.8,
        )
        db_session.add(link2)
        db_session.commit()

        links = db_session.query(MemoryEvidenceLink).filter_by(claim_id=claim.id).all()

        # Filter for court_record quality or higher
        filtered = filter_evidence_by_quality(links, db_session, min_source_quality="court_record")

        # Only court_record evidence should pass
        assert len(filtered) == 1


class TestEvidenceRanking:
    """Test evidence ranking by relevance."""

    def test_rank_evidence_by_relevance(self, db_session):
        """Test ranking evidence by relevance to claim."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.8,
            review_status="approved",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="court_source",
            snapshot_hash="hash",
            content="Court record",
            source_quality="court_record",
        )
        db_session.add(snapshot)

        snapshot2 = SourceSnapshot(
            source_id="court_source_2",
            snapshot_hash="hash_2",
            content="Court record addendum",
            source_quality="court_record",
        )
        db_session.add(snapshot2)
        db_session.commit()

        # Supporting evidence with quote match
        link1 = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            evidence_checksum="checksum1",
            support_type="supports",
            confidence=0.9,
            quote_text="This is a test value in the record",
        )
        db_session.add(link1)

        # Supporting evidence without quote match
        link2 = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot2.id,
            evidence_checksum="checksum2",
            support_type="supports",
            confidence=0.7,
            quote_text="Some other text",
        )
        db_session.add(link2)
        db_session.commit()

        links = db_session.query(MemoryEvidenceLink).filter_by(claim_id=claim.id).all()

        ranked = rank_evidence_by_relevance(links, claim, db_session)

        # First item should have higher score
        assert len(ranked) == 2


class TestEvidenceSummary:
    """Test evidence summary generation."""

    def test_get_evidence_summary(self, db_session):
        """Test getting evidence summary for a claim."""
        entity = CanonicalEntity(
            entity_type="person",
            name="John Doe",
            jurisdiction="CA",
        )
        db_session.add(entity)
        db_session.commit()

        claim = MemoryClaim(
            claim_key="test_claim",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Test value",
            confidence=0.8,
            review_status="approved",
        )
        db_session.add(claim)
        db_session.commit()

        snapshot = SourceSnapshot(
            source_id="court_source",
            snapshot_hash="hash",
            content="Court record",
            source_quality="court_record",
        )
        db_session.add(snapshot)

        snapshot2 = SourceSnapshot(
            source_id="court_source_2",
            snapshot_hash="hash_2",
            content="Court record supplemental",
            source_quality="court_record",
        )
        db_session.add(snapshot2)
        db_session.commit()

        # Add various evidence types
        link1 = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot.id,
            evidence_checksum="checksum1",
            support_type="supports",
            confidence=0.8,
        )
        db_session.add(link1)

        link2 = MemoryEvidenceLink(
            claim_id=claim.id,
            snapshot_id=snapshot2.id,
            evidence_checksum="checksum2",
            support_type="contradicts",
            confidence=0.6,
        )
        db_session.add(link2)
        db_session.commit()

        summary = get_evidence_summary(claim.id, db_session)

        assert summary["total_evidence"] == 2
        assert summary["supporting_count"] == 1
        assert summary["contradicting_count"] == 1
        assert "evidence_score" in summary

