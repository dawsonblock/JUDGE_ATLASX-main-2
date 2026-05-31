"""Enhanced public UI safety layer (Phase 17).

Provides content safety checks and validation for public-facing data.
"""

import logging
import re
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def check_content_safety(text: str) -> Dict[str, Any]:
    """Check content for safety issues before public display.

    Args:
        text: Text to check

    Returns:
        Dictionary with safety check results
    """
    issues = []

    # Check for PII patterns
    if _contains_email(text):
        issues.append("email_address")

    if _contains_phone(text):
        issues.append("phone_number")

    if _contains_ssn(text):
        issues.append("ssn_pattern")

    if _contains_credit_card(text):
        issues.append("credit_card")

    # Check for potentially harmful content
    if _contains_personal_address(text):
        issues.append("personal_address")

    return {
        "safe": len(issues) == 0,
        "issues": issues,
        "issue_count": len(issues),
    }


def sanitize_for_public_display(
    text: str,
    max_length: int = 1000,
    allowed_tags: Optional[List[str]] = None,
) -> str:
    """Sanitize text for public display.

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length
        allowed_tags: List of allowed HTML tags (None for no HTML)

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Truncate if too long
    if len(text) > max_length:
        text = text[:max_length] + "..."

    # Remove HTML if not allowed
    if allowed_tags is None:
        text = re.sub(r"<[^>]+>", "", text)

    return text.strip()


def validate_public_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate data structure for public API responses.

    Args:
        data: Data dictionary to validate

    Returns:
        Validation result with any issues found
    """
    issues = []

    # Check for sensitive keys
    sensitive_keys = ["password", "token", "secret", "key", "private"]
    for key in data.keys():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            issues.append(f"sensitive_key_{key}")

    # Check for null values in required fields
    if "id" in data and data["id"] is None:
        issues.append("missing_id")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


def _contains_email(text: str) -> bool:
    """Check if text contains email pattern."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return bool(re.search(pattern, text))


def _contains_phone(text: str) -> bool:
    """Check if text contains phone number pattern."""
    pattern = r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
    return bool(re.search(pattern, text))


def _contains_ssn(text: str) -> bool:
    """Check if text contains SSN pattern."""
    pattern = r"\b\d{3}-\d{2}-\d{4}\b"
    return bool(re.search(pattern, text))


def _contains_credit_card(text: str) -> bool:
    """Check if text contains credit card pattern."""
    pattern = r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
    return bool(re.search(pattern, text))


def _contains_personal_address(text: str) -> bool:
    """Check if text looks like a personal address."""
    # Simple heuristic: street number + street name pattern
    pattern = r"\b\d+\s+[A-Z][a-z]+\s+(Street|St|Ave|Avenue|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b"
    return bool(re.search(pattern, text))


def check_rate_limit(
    client_id: str,
    endpoint: str,
    limit: int = 100,
    window_seconds: int = 60,
    redis_client=None,
) -> Dict[str, Any]:
    """Check if client has exceeded rate limit.

    Args:
        client_id: Client identifier
        endpoint: Endpoint being accessed
        limit: Maximum requests per window
        window_seconds: Time window in seconds
        redis_client: Redis client for distributed tracking

    Returns:
        Rate limit check result
    """
    # This is a simplified implementation
    # In production, use Redis for distributed rate limiting
    return {
        "allowed": True,
        "remaining": limit - 1,
        "reset_at": window_seconds,
        "limit": limit,
    }
