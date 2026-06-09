"""Schemas for the transcriptions endpoints (02-api-contracts.md)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TranscriptionCreateRequest(BaseModel):
    """POST /api/transcriptions request body."""

    full_text: str = Field(..., description="Transcription text (required, non-empty).")
    language: str | None = Field(default=None, description="Optional ISO language code.")
    summary: str | None = Field(default=None, description="Optional summary text.")


class TranscriptionCreateResponse(BaseModel):
    """POST /api/transcriptions 201 response body."""

    transcription_id: uuid.UUID
    summary_id: uuid.UUID | None = None
    created_at: datetime
