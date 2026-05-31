"""Tests for API contract validation (Phase 18).

Tests input/output validation, security checks, and rate limiting.
"""

import pytest
from pydantic import BaseModel, Field

from app.api.contract_validation import (
    validate_input,
    validate_output,
    sanitize_input_fields,
    check_sql_injection,
    check_xss,
    validate_request_security,
    check_rate_limit,
    APIValidationError,
)


class TestInputSchema(BaseModel):
    """Test schema for input validation."""
    __test__ = False

    name: str
    age: int = Field(ge=0, le=150)
    email: str


class TestInputValidation:
    """Test input validation."""

    def test_validate_input_valid(self):
        """Test validation of valid input."""
        data = {"name": "John", "age": 30, "email": "john@example.com"}
        result = validate_input(data, TestInputSchema)

        assert result.name == "John"
        assert result.age == 30

    def test_validate_input_invalid(self):
        """Test validation of invalid input."""
        data = {"name": "John", "age": 200, "email": "john@example.com"}

        with pytest.raises(APIValidationError):
            validate_input(data, TestInputSchema)


class TestOutputValidation:
    """Test output validation."""

    def test_validate_output_dict(self):
        """Test validation of dict output."""
        data = {"id": 1, "name": "Test"}
        result = validate_output(data)

        assert result == data

    def test_validate_output_size_limit(self):
        """Test size limit enforcement."""
        data = "A" * 20000

        with pytest.raises(APIValidationError):
            validate_output(data, max_size=1000)

    def test_validate_output_string(self):
        """Test validation of string output."""
        data = "Test output"
        result = validate_output(data)

        assert result == data


class TestFieldSanitization:
    """Test input field sanitization."""

    def test_sanitize_allowed_fields(self):
        """Test sanitization with allowed fields."""
        data = {"name": "John", "age": 30, "extra": "data"}
        allowed = ["name", "age"]
        result = sanitize_input_fields(data, allowed)

        assert "name" in result
        assert "age" in result
        assert "extra" not in result

    def test_sanitize_required_fields(self):
        """Test required field validation."""
        data = {"name": "John"}
        allowed = ["name", "age"]
        required = ["name", "age"]

        with pytest.raises(APIValidationError):
            sanitize_input_fields(data, allowed, required)

    def test_sanitize_all_required_present(self):
        """Test sanitization when all required fields present."""
        data = {"name": "John", "age": 30}
        allowed = ["name", "age"]
        required = ["name"]
        result = sanitize_input_fields(data, allowed, required)

        assert "name" in result
        assert "age" in result


class TestSecurityChecks:
    """Test security validation."""

    def test_check_sql_injection(self):
        """Test SQL injection detection."""
        assert check_sql_injection("'; DROP TABLE users;--")
        assert not check_sql_injection("Normal text")

    def test_check_xss(self):
        """Test XSS detection."""
        assert check_xss("<script>alert('xss')</script>")
        assert not check_xss("Normal text")

    def test_validate_request_security_clean(self):
        """Test security validation on clean data."""
        data = {"name": "John", "comment": "Safe comment"}
        result = validate_request_security(data)

        assert result["secure"] is True

    def test_validate_request_security_sql(self):
        """Test security validation detects SQL injection."""
        data = {"name": "John", "comment": "'; DROP TABLE users;--"}

        with pytest.raises(APIValidationError):
            validate_request_security(data)

    def test_validate_request_security_xss(self):
        """Test security validation detects XSS."""
        data = {"name": "John", "comment": "<script>alert('xss')</script>"}

        with pytest.raises(APIValidationError):
            validate_request_security(data)

    def test_validate_request_security_specific_fields(self):
        """Test security validation on specific fields."""
        data = {
            "name": "John",
            "comment": "'; DROP TABLE users;--",
            "safe_field": "Safe text",
        }

        with pytest.raises(APIValidationError):
            validate_request_security(data, check_fields=["comment"])
