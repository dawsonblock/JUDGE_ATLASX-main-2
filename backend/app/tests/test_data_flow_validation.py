"""Tests for data flow validation (Phase 23).

Tests data flow architecture and integrity validation.
"""

from app.data.data_flow_validation import DataFlowValidator


class TestDataFlowValidator:
    """Test data flow validation functionality."""

    def test_validate_ingestion_to_memory_flow(self, db_session):
        """Test ingestion to memory flow validation."""
        validator = DataFlowValidator(db_session)
        result = validator.validate_ingestion_to_memory_flow()

        assert "component" in result
        assert "valid" in result
        assert "issues" in result

    def test_validate_memory_to_evidence_flow(self, db_session):
        """Test memory to evidence flow validation."""
        validator = DataFlowValidator(db_session)
        result = validator.validate_memory_to_evidence_flow()

        assert "component" in result
        assert "valid" in result
        assert "issues" in result

    def test_validate_evidence_to_publication_flow(self, db_session):
        """Test evidence to publication flow validation."""
        validator = DataFlowValidator(db_session)
        result = validator.validate_evidence_to_publication_flow()

        assert "component" in result
        assert "valid" in result
        assert "issues" in result

    def test_validate_review_to_publication_flow(self, db_session):
        """Test review to publication flow validation."""
        validator = DataFlowValidator(db_session)
        result = validator.validate_review_to_publication_flow()

        assert "component" in result
        assert "valid" in result
        assert "issues" in result

    def test_run_full_validation(self, db_session):
        """Test running all validations."""
        validator = DataFlowValidator(db_session)
        results = validator.run_full_validation()

        assert "ingestion_to_memory" in results
        assert "memory_to_evidence" in results
        assert "evidence_to_publication" in results
        assert "review_to_publication" in results
        assert "overall_valid" in results
        assert "total_issues" in results
