"""Tests for enhanced public safety layer (Phase 17).

Tests content safety checks, sanitization, and validation.
"""

import pytest

from app.services.public_safety_enhanced import (
    check_content_safety,
    sanitize_for_public_display,
    validate_public_data,
    check_rate_limit,
)


class TestContentSafety:
    """Test content safety checks."""

    def test_check_content_safety_clean_text(self):
        """Test safety check on clean text."""
        result = check_content_safety("This is safe content")

        assert result["safe"] is True
        assert result["issues"] == []
        assert result["issue_count"] == 0

    def test_check_content_safety_email(self):
        """Test safety check detects email."""
        result = check_content_safety("Contact user@example.com")

        assert result["safe"] is False
        assert "email_address" in result["issues"]

    def test_check_content_safety_phone(self):
        """Test safety check detects phone number."""
        result = check_content_safety("Call 555-123-4567")

        assert result["safe"] is False
        assert "phone_number" in result["issues"]

    def test_check_content_safety_ssn(self):
        """Test safety check detects SSN pattern."""
        result = check_content_safety("SSN: 123-45-6789")

        assert result["safe"] is False
        assert "ssn_pattern" in result["issues"]

    def test_check_content_safety_credit_card(self):
        """Test safety check detects credit card."""
        result = check_content_safety("Card: 4111-1111-1111-1111")

        assert result["safe"] is False
        assert "credit_card" in result["issues"]

    def test_check_content_safety_address(self):
        """Test safety check detects personal address."""
        result = check_content_safety("123 Main Street")

        assert result["safe"] is False
        assert "personal_address" in result["issues"]


class TestSanitization:
    """Test text sanitization for public display."""

    def test_sanitize_short_text(self):
        """Test sanitization of short text."""
        result = sanitize_for_public_display("Safe text")

        assert result == "Safe text"

    def test_sanitize_long_text(self):
        """Test truncation of long text."""
        long_text = "A" * 2000
        result = sanitize_for_public_display(long_text, max_length=100)

        assert len(result) <= 104  # 100 + "..."

    def test_sanitize_html(self):
        """Test HTML removal."""
        result = sanitize_for_public_display("<p>Text</p>")

        assert result == "Text"

    def test_sanitize_empty_text(self):
        """Test sanitization of empty text."""
        result = sanitize_for_public_display("")

        assert result == ""

    def test_sanitize_with_allowed_tags(self):
        """Test sanitization with allowed HTML tags."""
        result = sanitize_for_public_display(
            "<p>Text</p>", allowed_tags=["p"]
        )

        assert "<p>" in result


class TestDataValidation:
    """Test public data validation."""

    def test_validate_clean_data(self):
        """Test validation of clean data."""
        data = {"id": 1, "name": "Test"}
        result = validate_public_data(data)

        assert result["valid"] is True
        assert result["issues"] == []

    def test_validate_sensitive_key(self):
        """Test validation detects sensitive keys."""
        data = {"password": "secret"}
        result = validate_public_data(data)

        assert result["valid"] is False
        assert "sensitive_key_password" in result["issues"]

    def test_validate_missing_id(self):
        """Test validation detects missing ID."""
        data = {"id": None}
        result = validate_public_data(data)

        assert result["valid"] is False
        assert "missing_id" in result["issues"]


class TestRateLimiting:
    """Test rate limiting checks."""

    def test_check_rate_limit_allowed(self):
        """Test rate limit allows requests."""
        result = check_rate_limit("client1", "/api/data")

        assert result["allowed"] is True
        assert result["remaining"] >= 0

    def test_check_rate_limit_custom_limit(self):
        """Test rate limit with custom limit."""
        result = check_rate_limit("client1", "/api/data", limit=50)

        assert result["limit"] == 50
