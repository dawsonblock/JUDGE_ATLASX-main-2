"""Tests for CI/CD gate validation (Phase 21).

Tests CI/CD pipeline gates and deployment validation.
"""

from app.ci.cicd_gate import CICDGate


class TestCICDGate:
    """Test CI/CD gate functionality."""

    def test_check_git_clean(self):
        """Test git clean check."""
        gate = CICDGate(".")
        result = gate.check_git_clean()

        assert "is_clean" in result
        assert "passed" in result

    def test_check_branch_name(self):
        """Test branch name validation."""
        gate = CICDGate(".")
        result = gate.check_branch_name(["main", "develop"])

        assert "branch" in result
        assert "passed" in result

    def test_check_environment_variables_empty(self):
        """Test environment check with no requirements."""
        gate = CICDGate(".")
        result = gate.check_environment_variables([])

        assert result["passed"] is True
        assert result["required_count"] == 0

    def test_check_environment_variables_missing(self):
        """Test environment check with missing vars."""
        gate = CICDGate(".")
        result = gate.check_environment_variables(["NONEXISTENT_VAR"])

        assert result["passed"] is False
        assert result["missing_count"] == 1

    def test_check_dependencies(self):
        """Test dependency check."""
        gate = CICDGate(".")
        result = gate.check_dependencies()

        assert "required_count" in result
        assert "installed_count" in result
        assert "passed" in result

    def test_check_database_connection(self):
        """Test database connection check."""
        gate = CICDGate(".")
        result = gate.check_database_connection()

        assert "passed" in result

    def test_run_pre_deployment_checks(self):
        """Test running all pre-deployment checks."""
        gate = CICDGate(".")
        results = gate.run_pre_deployment_checks()

        assert "git_clean" in results
        assert "branch_name" in results
        assert "environment_vars" in results
        assert "dependencies" in results
        assert "database" in results
        assert "overall_passed" in results
