"""Tests for done criteria validation (Phase 24).

Tests completion validation of all project phases.
"""

from app.validation.done_criteria import DoneCriteriaValidator


class TestDoneCriteriaValidator:
    """Test done criteria validation functionality."""

    def test_check_phase_completion(self):
        """Test phase completion check."""
        validator = DoneCriteriaValidator(".")
        result = validator.check_phase_completion()

        assert "total_phases" in result
        assert "completed" in result
        assert "pending" in result
        assert "completion_percentage" in result
        assert result["total_phases"] == 24

    def test_check_test_coverage(self):
        """Test test coverage check."""
        validator = DoneCriteriaValidator(".")
        result = validator.check_test_coverage()

        assert "phases_with_tests" in result
        assert "phases_without_tests" in result
        assert "test_coverage_percentage" in result

    def test_validate_done_criteria(self):
        """Test full done criteria validation."""
        validator = DoneCriteriaValidator(".")
        result = validator.validate_done_criteria()

        assert "all_phases_complete" in result
        assert "all_phases_tested" in result
        assert "is_done" in result
        assert "phase_completion" in result
        assert "test_coverage" in result
        assert "ready_for_release" in result
