"""Chat orchestration service: the main /api/chat/messages flow.

Steps (03-architecture.md):
1. Validate transcription exists and is non-empty; validate message non-empty.
2. Resolve summary (by summary_id or latest) and recent history.
3. Build context (summary-first).
4. Persist the user message and commit it (its own transaction).
5. Call OpenAI (timeout / 1 retry handled in LLMClient).
6. Extract structured_blocks for list commands.
7. Persist the assistant message, commit, and return it.

On LLM failure (502/504) the already-committed user message remains; no
assistant message is created (02-api-contracts.md).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    EmptyTranscriptionError,
    SummaryNotFoundError,
    TranscriptionNotFoundError,
)
from app.core.logging import get_logger
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.transcriptions import TranscriptionRepository
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.blocks import extract_structured_blocks
from app.services.context import ContextInputs, HistoryMessage, build_context
from app.services.llm import LLMClient

logger = get_logger(__name__)


class ChatService:
    """Orchestrates a single chat message turn."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        transcription_repo: TranscriptionRepository,
        message_repo: ChatMessageRepository,
        llm: LLMClient,
        model: str,
        token_budget: int,
        history_limit: int,
    ) -> None:
        self._session = session
        self._transcriptions = transcription_repo
        self._messages = message_repo
        self._llm = llm
        self._model = model
        self._token_budget = token_budget
        self._history_limit = history_limit

    async def handle(self, payload: ChatMessageRequest) -> ChatMessageResponse:
        """Process a chat message and return the assistant response."""
        if not payload.message or not payload.message.strip():
            raise EmptyTranscriptionError("message must be a non-empty string.")

        transcription = await self._transcriptions.get_transcription(payload.transcription_id)
        if transcription is None:
            raise TranscriptionNotFoundError("Transcription not found.")
        if not transcription.full_text or not transcription.full_text.strip():
            raise EmptyTranscriptionError("Transcription has no text.")

        summary_text, summary_id = await self._resolve_summary(payload)

        history_rows = await self._messages.list_recent(
            payload.transcription_id,
            limit=self._history_limit,
        )
        history = [HistoryMessage(role=row.role, content=row.content) for row in history_rows]

        context = build_context(
            ContextInputs(
                model=self._model,
                token_budget=self._token_budget,
                message=payload.message,
                full_text=transcription.full_text,
                summary=summary_text,
                selected_text=payload.selected_text,
                quick_command=payload.quick_command_type,
                language=transcription.language,
                history=history,
            )
        )

        # Persist the user message and COMMIT it in its own transaction before
        # calling the model. This guarantees the user message stays in history
        # even if the LLM call fails: get_db_session.rollback() on the LLM error
        # has nothing to undo for the user message (02-api-contracts.md:124,
        # 03-architecture steps 5-8).
        await self._messages.add_message(
            transcription_id=payload.transcription_id,
            role="user",
            content=payload.message,
            summary_id=summary_id,
            selected_text=payload.selected_text,
            quick_command_type=(
                payload.quick_command_type.value if payload.quick_command_type else None
            ),
        )
        await self._session.commit()

        # Call OpenAI. On failure, ModelError/ModelTimeoutError propagate; the
        # already-committed user message stays, no assistant message is created.
        content = await self._llm.complete(context.messages)

        structured_blocks = extract_structured_blocks(content, payload.quick_command_type)

        assistant = await self._messages.add_message(
            transcription_id=payload.transcription_id,
            role="assistant",
            content=content,
            summary_id=summary_id,
            quick_command_type=(
                payload.quick_command_type.value if payload.quick_command_type else None
            ),
            structured_blocks=structured_blocks,
        )
        await self._session.commit()

        return ChatMessageResponse(
            message_id=assistant.id,
            transcription_id=payload.transcription_id,
            content=content,
            created_at=assistant.created_at,
            quick_command_type=payload.quick_command_type,
            structured_blocks=structured_blocks,
            context_truncated=context.context_truncated,
            context_mode=context.context_mode,
        )

    async def _resolve_summary(
        self,
        payload: ChatMessageRequest,
    ) -> tuple[str | None, uuid.UUID | None]:
        """Resolve summary text and id from summary_id or the latest summary."""
        if payload.summary_id is not None:
            summary = await self._transcriptions.get_summary(payload.summary_id)
            if summary is None or summary.transcription_id != payload.transcription_id:
                raise SummaryNotFoundError("Summary not found for this transcription.")
            return summary.summary_text, summary.id

        latest = await self._transcriptions.get_latest_summary(payload.transcription_id)
        if latest is None:
            return None, None
        return latest.summary_text, latest.id
