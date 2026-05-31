"""Validation reports — structured results for serializer input validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    field_path: str  # dot-separated path, e.g. "address.zip"
    message: str
    severity: Severity = Severity.ERROR
    code: Optional[str] = None  # machine-readable error code
    value: Any = None  # the offending value (omit if sensitive)

    def is_error(self) -> bool:
        return self.severity == Severity.ERROR

    def is_warning(self) -> bool:
        return self.severity == Severity.WARNING

    def as_dict(self) -> Dict[str, Any]:
        return {
            "field_path": self.field_path,
            "message": self.message,
            "severity": self.severity.value,
            "code": self.code,
        }


@dataclass
class ValidationReport:
    """Accumulates issues from a single validation pass."""

    subject: str = ""
    _issues: List[ValidationIssue] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------
    # Adding issues
    # ------------------------------------------------------------------

    def add(self, issue: ValidationIssue) -> None:
        self._issues.append(issue)

    def error(
        self,
        field_path: str,
        message: str,
        code: Optional[str] = None,
        value: Any = None,
    ) -> None:
        self.add(
            ValidationIssue(
                field_path=field_path,
                message=message,
                severity=Severity.ERROR,
                code=code,
                value=value,
            )
        )

    def warning(
        self,
        field_path: str,
        message: str,
        code: Optional[str] = None,
    ) -> None:
        self.add(
            ValidationIssue(
                field_path=field_path,
                message=message,
                severity=Severity.WARNING,
                code=code,
            )
        )

    def info(self, field_path: str, message: str) -> None:
        self.add(
            ValidationIssue(
                field_path=field_path,
                message=message,
                severity=Severity.INFO,
            )
        )

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def issues(self) -> List[ValidationIssue]:
        return list(self._issues)

    def by_severity(self, severity: Severity) -> List[ValidationIssue]:
        return [i for i in self._issues if i.severity == severity]

    def errors(self) -> List[ValidationIssue]:
        return self.by_severity(Severity.ERROR)

    def warnings(self) -> List[ValidationIssue]:
        return self.by_severity(Severity.WARNING)

    def is_valid(self) -> bool:
        return not any(i.is_error() for i in self._issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self._issues if i.is_error())

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self._issues if i.is_warning())

    @property
    def total_count(self) -> int:
        return len(self._issues)

    def field_errors(self, field_path: str) -> List[ValidationIssue]:
        return [i for i in self._issues if i.field_path == field_path and i.is_error()]

    def has_field_error(self, field_path: str) -> bool:
        return bool(self.field_errors(field_path))

    def unique_error_fields(self) -> List[str]:
        seen = []
        for i in self._issues:
            if i.is_error() and i.field_path not in seen:
                seen.append(i.field_path)
        return seen

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def as_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "valid": self.is_valid(),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.as_dict() for i in self._issues],
        }

    def merge(self, other: "ValidationReport") -> None:
        """Append all issues from another report into this one."""
        for issue in other._issues:
            self._issues.append(issue)

    def clear(self) -> None:
        self._issues.clear()


__all__ = ["Severity", "ValidationIssue", "ValidationReport"]
