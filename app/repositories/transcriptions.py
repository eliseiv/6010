"""Repository for transcriptions and summaries."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.summary import Summary
from app.models.transcription import Transcription


class TranscriptionRepository:
    """Async data access for transcriptions and summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_transcription(
        self,
        *,
        full_text: str,
        language: str | None,
    ) -> Transcription:
        """Insert a transcription and flush to obtain server-generated id."""
        transcription = Transcription(full_text=full_text, language=language)
        self._session.add(transcription)
        await self._session.flush()
        await self._session.refresh(transcription)
        return transcription

    async def create_summary(
        self,
        *,
        transcription_id: uuid.UUID,
        summary_text: str,
    ) -> Summary:
        """Insert a summary for a transcription."""
        summary = Summary(transcription_id=transcription_id, summary_text=summary_text)
        self._session.add(summary)
        await self._session.flush()
        await self._session.refresh(summary)
        return summary

    async def get_transcription(self, transcription_id: uuid.UUID) -> Transcription | None:
        """Fetch a transcription by id."""
        return await self._session.get(Transcription, transcription_id)

    async def get_summary(self, summary_id: uuid.UUID) -> Summary | None:
        """Fetch a summary by id."""
        return await self._session.get(Summary, summary_id)

    async def get_latest_summary(self, transcription_id: uuid.UUID) -> Summary | None:
        """Fetch the most recent summary for a transcription, if any."""
        stmt = (
            select(Summary)
            .where(Summary.transcription_id == transcription_id)
            .order_by(Summary.created_at.desc(), Summary.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
