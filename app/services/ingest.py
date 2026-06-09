"""Ingest service: create a transcription and optional summary."""

from __future__ import annotations

from app.core.errors import EmptyTranscriptionError
from app.repositories.transcriptions import TranscriptionRepository
from app.schemas.transcriptions import (
    TranscriptionCreateRequest,
    TranscriptionCreateResponse,
)


class IngestService:
    """Business logic for transcription ingest."""

    def __init__(self, repo: TranscriptionRepository) -> None:
        self._repo = repo

    async def ingest(
        self,
        payload: TranscriptionCreateRequest,
    ) -> TranscriptionCreateResponse:
        """Create a transcription (and optional summary).

        Raises EmptyTranscriptionError (400) when full_text is empty/whitespace.
        """
        if not payload.full_text or not payload.full_text.strip():
            raise EmptyTranscriptionError("full_text must be a non-empty string.")

        transcription = await self._repo.create_transcription(
            full_text=payload.full_text,
            language=payload.language,
        )

        summary_id = None
        if payload.summary is not None and payload.summary.strip():
            summary = await self._repo.create_summary(
                transcription_id=transcription.id,
                summary_text=payload.summary,
            )
            summary_id = summary.id

        return TranscriptionCreateResponse(
            transcription_id=transcription.id,
            summary_id=summary_id,
            created_at=transcription.created_at,
        )
