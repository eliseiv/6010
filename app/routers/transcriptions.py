"""Transcriptions router: ingest and chat history endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import TranscriptionNotFoundError
from app.core.security import require_api_key
from app.dependencies import get_ingest_service, get_message_repo, get_transcription_repo
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.transcriptions import TranscriptionRepository
from app.schemas.chat import ChatHistoryResponse, ChatMessageItem
from app.schemas.transcriptions import (
    TranscriptionCreateRequest,
    TranscriptionCreateResponse,
)
from app.services.ingest import IngestService

router = APIRouter(
    prefix="/api",
    tags=["transcriptions"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "/transcriptions",
    response_model=TranscriptionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transcription(
    payload: TranscriptionCreateRequest,
    service: Annotated[IngestService, Depends(get_ingest_service)],
) -> TranscriptionCreateResponse:
    """Ingest a transcription (and optional summary)."""
    return await service.ingest(payload)


@router.get(
    "/transcriptions/{transcription_id}/messages",
    response_model=ChatHistoryResponse,
)
async def list_messages(
    transcription_id: uuid.UUID,
    transcription_repo: Annotated[TranscriptionRepository, Depends(get_transcription_repo)],
    message_repo: Annotated[ChatMessageRepository, Depends(get_message_repo)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Literal["asc", "desc"] = "asc",
) -> ChatHistoryResponse:
    """Return the transcription's chat history (paginated, ordered)."""
    transcription = await transcription_repo.get_transcription(transcription_id)
    if transcription is None:
        raise TranscriptionNotFoundError("Transcription not found.")

    total = await message_repo.count(transcription_id)
    rows = await message_repo.list_paginated(
        transcription_id,
        limit=limit,
        offset=offset,
        order=order,
    )
    messages = [
        ChatMessageItem(
            message_id=row.id,
            role=row.role,
            content=row.content,
            selected_text=row.selected_text,
            quick_command_type=row.quick_command_type,
            structured_blocks=row.structured_blocks,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ChatHistoryResponse(
        transcription_id=transcription_id,
        total=total,
        limit=limit,
        offset=offset,
        messages=messages,
    )
