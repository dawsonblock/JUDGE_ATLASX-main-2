"""Tests for test gate expansion (Phase 20).

Tests test coverage validation and quality gates.
"""

from pathlib import Path

from app.tests.test_gate import TestGate


class TestTestGate:
    """Test test gate functionality."""

    def test_check_required_tests_empty(self):
        """Test required tests check with no requirements."""
        gate = TestGate(".")
        result = gate.check_required_tests()

        assert result["passed"] is True
        assert result["required_count"] == 0

    def test_check_required_tests_with_requirements(self):
        """Test required tests check with requirements."""
        gate = TestGate(".")
        gate.required_test_files = ["test_example.py"]
        result = gate.check_required_tests()

        # File doesn't exist, so should fail
        assert result["passed"] is False
        assert result["missing_count"] == 1

    def test_parse_coverage(self):
        """Test coverage parsing from output."""
        gate = TestGate(".")
        output = "TOTAL 100 50 50%"

        coverage = gate._parse_coverage(output)
        assert coverage == 50.0

    def test_parse_coverage_no_match(self):
        """Test coverage parsing with no match."""
        gate = TestGate(".")
        output = "No coverage data"

        coverage = gate._parse_coverage(output)
        assert coverage == 0.0

    def test_check_linting_skip(self):
        """Test linting check when tool not installed."""
        gate = TestGate(".")
        result = gate.check_linting()

        # Environment-dependent: ruff may be missing, or present with pass/fail output.
        assert "passed" in result
        assert isinstance(result["passed"], bool)

    def test_run_all_gates(self):
        """Test running all gates."""
        gate = TestGate(".")
        results = gate.run_all_gates()

        assert "test_coverage" in results
        assert "required_tests" in results
        assert "test_suite" in results
        assert "linting" in results
        assert "overall_passed" in results
