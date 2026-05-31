"""Runtime-safe Justice Canada XML parser package."""

from .parser import parse_legis_index, parse_statute_xml
from .schema_validator import (
    SchemaValidationError,
    validate_index_xml,
    validate_statute_xml,
)

__all__ = [
    "SchemaValidationError",
    "parse_legis_index",
    "parse_statute_xml",
    "validate_index_xml",
    "validate_statute_xml",
]
