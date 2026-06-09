"""Schemas for the chat endpoints (02-api-contracts.md)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.prompts import QuickCommand


class ChatMessageRequest(BaseModel):
    """POST /api/chat/messages request body."""

    transcription_id: uuid.UUID
    message: str = Field(..., description="User message (required, non-empty).")
    selected_text: str | None = Field(default=None, description="Optional selected fragment.")
    quick_command_type: QuickCommand | None = Field(
        default=None, description="Optional quick command."
    )
    summary_id: uuid.UUID | None = Field(default=None, description="Optional summary id.")


class ChatMessageResponse(BaseModel):
    """POST /api/chat/messages 201 response body."""

    message_id: uuid.UUID
    transcription_id: uuid.UUID
    role: Literal["assistant"] = "assistant"
    content: str
    created_at: datetime
    quick_command_type: QuickCommand | None = None
    structured_blocks: list[dict[str, Any]] | None = None
    context_truncated: bool = False
    context_mode: Literal["full", "summary_first", "truncated"]


class ChatMessageItem(BaseModel):
    """A single message in the history listing."""

    message_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    selected_text: str | None = None
    quick_command_type: QuickCommand | None = None
    structured_blocks: list[dict[str, Any]] | None = None
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """GET /api/transcriptions/{id}/messages 200 response body."""

    transcription_id: uuid.UUID
    total: int
    limit: int
    offset: int
    messages: list[ChatMessageItem]
