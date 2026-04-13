"""
Application-specific exceptions.

These are mapped to structured HTTP responses by global exception handlers.
"""
from __future__ import annotations


class AppError(Exception):
    """Base class for predictable API errors."""

    def __init__(self, message: str, *, details: str | None = None, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.status_code = status_code


class OpenAPIResolutionError(AppError):
    """OpenAPI document or operation resolution failed."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message, details=details, status_code=400)


class UpstreamFetchError(AppError):
    """Failed to fetch remote OpenAPI document."""

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message, details=details, status_code=502)


class LLMUnavailableError(AppError):
    """LLM provider misconfiguration or failure."""

    def __init__(self, message: str, *, details: str | None = None, status_code: int = 503) -> None:
        super().__init__(message, details=details, status_code=status_code)
