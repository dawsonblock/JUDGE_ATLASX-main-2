"""Structured CLI errors for machine-readable output."""

from __future__ import annotations


class CliError(Exception):
    """Raised when a CLI command fails in a structured way."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        next_action: str = "",
        **extra: object,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.next_action = next_action
        self.extra = extra
