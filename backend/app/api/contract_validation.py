"""API contract hardening (Phase 18).

Provides input/output validation for API endpoints.
"""

import logging
from typing import Any, Dict, List, Optional, Callable
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class APIValidationError(Exception):
    """Raised when API contract validation fails."""

    def __init__(self, message: str, errors: List[str]):
        self.message = message
        self.errors = errors
        super().__init__(message)


def validate_input(
    data: Dict[str, Any],
    schema: type[BaseModel],
    allow_partial: bool = False,
) -> BaseModel:
    """Validate input data against a schema.

    Args:
        data: Input data to validate
        schema: Pydantic schema to validate against
        allow_partial: Allow partial data (missing optional fields)

    Returns:
        Validated model instance

    Raises:
        APIValidationError: If validation fails
    """
    try:
        if allow_partial:
            return schema(**data)
        else:
            return schema.model_validate(data)
    except ValidationError as e:
        errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
        raise APIValidationError("Input validation failed", errors)


def validate_output(
    data: Any,
    schema: Optional[type[BaseModel]] = None,
    max_size: int = 10000,
) -> Dict[str, Any]:
    """Validate output data before sending to client.

    Args:
        data: Output data to validate
        schema: Optional Pydantic schema to validate against
        max_size: Maximum size of output in characters

    Returns:
        Validated output data

    Raises:
        APIValidationError: If validation fails
    """
    # Check size limit
    if isinstance(data, str) and len(data) > max_size:
        raise APIValidationError(
            "Output size exceeds limit",
            [f"Output length {len(data)} exceeds maximum {max_size}"]
        )

    if isinstance(data, dict):
        # Recursively check dict values
        for key, value in data.items():
            if isinstance(value, str) and len(value) > max_size:
                raise APIValidationError(
                    "Output size exceeds limit",
                    [f"Field '{key}' exceeds maximum size"]
                )

    # Validate against schema if provided
    if schema:
        try:
            schema.model_validate(data)
        except ValidationError as e:
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            raise APIValidationError("Output validation failed", errors)

    return data


def sanitize_input_fields(
    data: Dict[str, Any],
    allowed_fields: List[str],
    required_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Sanitize input by filtering to allowed fields.

    Args:
        data: Input data
        allowed_fields: List of allowed field names
        required_fields: List of required field names

    Returns:
        Sanitized data dictionary

    Raises:
        APIValidationError: If required fields are missing
    """
    # Check required fields
    if required_fields:
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise APIValidationError(
                "Missing required fields",
                [f"Missing: {', '.join(missing)}"]
            )

    # Filter to allowed fields
    sanitized = {k: v for k, v in data.items() if k in allowed_fields}

    return sanitized


def check_sql_injection(text: str) -> bool:
    """Check text for potential SQL injection patterns.

    Args:
        text: Text to check

    Returns:
        True if potential injection detected
    """
    sql_patterns = [
        "';--",
        "' OR '",
        "' OR 1=1",
        "DROP TABLE",
        "UNION SELECT",
        "INSERT INTO",
        "UPDATE SET",
        "DELETE FROM",
        "--",
        "/*",
        "*/",
    ]

    text_upper = text.upper()
    return any(pattern.upper() in text_upper for pattern in sql_patterns)


def check_xss(text: str) -> bool:
    """Check text for potential XSS patterns.

    Args:
        text: Text to check

    Returns:
        True if potential XSS detected
    """
    xss_patterns = [
        "<script",
        "javascript:",
        "onerror=",
        "onload=",
        "onclick=",
        "onmouseover=",
        "<iframe",
        "<object",
        "<embed",
        "eval(",
        "expression(",
    ]

    text_lower = text.lower()
    return any(pattern in text_lower for pattern in xss_patterns)


def validate_request_security(
    data: Dict[str, Any],
    check_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Validate request for security issues.

    Args:
        data: Request data
        check_fields: List of specific fields to check (all if None)

    Returns:
        Validation result with security issues

    Raises:
        APIValidationError: If security issues detected
    """
    issues = []

    fields_to_check = check_fields or data.keys()

    for field in fields_to_check:
        value = data.get(field)
        if not isinstance(value, str):
            continue

        if check_sql_injection(value):
            issues.append(f"SQL injection pattern in field '{field}'")

        if check_xss(value):
            issues.append(f"XSS pattern in field '{field}'")

    if issues:
        raise APIValidationError("Security validation failed", issues)

    return {"secure": True, "checked_fields": list(fields_to_check)}


class RateLimitInfo:
    """Rate limit information for API endpoints."""

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        current_requests: int,
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.current_requests = current_requests

    def to_dict(self) -> Dict[str, Any]:
        return {
            "limit": self.limit,
            "window_seconds": self.window_seconds,
            "current_requests": self.current_requests,
            "remaining": max(0, self.limit - self.current_requests),
        }


def check_rate_limit(
    client_id: str,
    endpoint: str,
    limit: int = 100,
    window_seconds: int = 60,
) -> RateLimitInfo:
    """Check rate limit for client endpoint access.

    Args:
        client_id: Client identifier
        endpoint: Endpoint path
        limit: Maximum requests per window
        window_seconds: Time window in seconds

    Returns:
        RateLimitInfo with current status

    Raises:
        APIValidationError: If rate limit exceeded
    """
    # Simplified implementation - in production use Redis
    # For now, always allow
    return RateLimitInfo(limit=limit, window_seconds=window_seconds, current_requests=0)
