"""Domain exceptions and error contract.

Error body shape (02-api-contracts.md):
    {"error": {"code": str, "message": str, "details": {...}?}}

Each domain exception carries the HTTP status and machine code mandated by the
contract. The exception handlers in app.main map these to JSON responses.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for domain errors mapped to the API error contract."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_body(self) -> dict[str, Any]:
        """Render the error contract body."""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


class EmptyTranscriptionError(DomainError):
    """full_text / message empty, or transcription without text. -> 400."""

    status_code = 400
    code = "empty_transcription"


class BadRequestError(DomainError):
    """Other input business-rule violations. -> 400."""

    status_code = 400
    code = "bad_request"


class UnauthorizedError(DomainError):
    """Missing / invalid X-API-Key. -> 401."""

    status_code = 401
    code = "unauthorized"


class TranscriptionNotFoundError(DomainError):
    """transcription_id not found. -> 404."""

    status_code = 404
    code = "transcription_not_found"


class SummaryNotFoundError(DomainError):
    """summary_id not found or not belonging to the transcription. -> 404."""

    status_code = 404
    code = "summary_not_found"


class ContextTooLongError(DomainError):
    """Context exceeds budget even after summary-first truncation. -> 413."""

    status_code = 413
    code = "context_too_long"


class ModelError(DomainError):
    """OpenAI returned a model/API error or invalid response. -> 502."""

    status_code = 502
    code = "model_error"


class ModelTimeoutError(DomainError):
    """Timeout talking to OpenAI. -> 504."""

    status_code = 504
    code = "model_timeout"
