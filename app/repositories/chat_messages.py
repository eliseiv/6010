"""Repository for chat messages."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage


class ChatMessageRepository:
    """Async data access for chat messages (single thread per transcription)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_message(
        self,
        *,
        transcription_id: uuid.UUID,
        role: str,
        content: str,
        summary_id: uuid.UUID | None = None,
        selected_text: str | None = None,
        quick_command_type: str | None = None,
        structured_blocks: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """Insert a chat message and flush to obtain server-generated fields."""
        message = ChatMessage(
            transcription_id=transcription_id,
            role=role,
            content=content,
            summary_id=summary_id,
            selected_text=selected_text,
            quick_command_type=quick_command_type,
            structured_blocks=structured_blocks,
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def list_recent(
        self,
        transcription_id: uuid.UUID,
        limit: int,
    ) -> list[ChatMessage]:
        """Return the most recent `limit` messages (chronological order asc).

        Fetches newest-first then reverses, so the result is oldest->newest of
        the most recent window — ready for context assembly.
        """
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.transcription_id == transcription_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        rows.reverse()
        return rows

    async def list_paginated(
        self,
        transcription_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        order: str,
    ) -> list[ChatMessage]:
        """Return a page of thread messages ordered by created_at (asc|desc)."""
        ordering = (
            (ChatMessage.created_at.asc(), ChatMessage.id.asc())
            if order == "asc"
            else (ChatMessage.created_at.desc(), ChatMessage.id.desc())
        )
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.transcription_id == transcription_id)
            .order_by(*ordering)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, transcription_id: uuid.UUID) -> int:
        """Count messages in a transcription's thread."""
        stmt = (
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.transcription_id == transcription_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())
