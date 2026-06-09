"""FastAPI dependency providers wiring repositories, services and the LLM client."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.transcriptions import TranscriptionRepository
from app.services.chat import ChatService
from app.services.ingest import IngestService
from app.services.llm import LLMClient

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_transcription_repo(session: SessionDep) -> TranscriptionRepository:
    """Provide a TranscriptionRepository bound to the request session."""
    return TranscriptionRepository(session)


def get_message_repo(session: SessionDep) -> ChatMessageRepository:
    """Provide a ChatMessageRepository bound to the request session."""
    return ChatMessageRepository(session)


def get_ingest_service(
    repo: Annotated[TranscriptionRepository, Depends(get_transcription_repo)],
) -> IngestService:
    """Provide the ingest service."""
    return IngestService(repo)


def get_llm_client(settings: SettingsDep) -> LLMClient:
    """Provide the OpenAI LLM client."""
    return LLMClient(settings)


def get_chat_service(
    session: SessionDep,
    transcription_repo: Annotated[TranscriptionRepository, Depends(get_transcription_repo)],
    message_repo: Annotated[ChatMessageRepository, Depends(get_message_repo)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
    settings: SettingsDep,
) -> ChatService:
    """Provide the chat orchestration service."""
    return ChatService(
        session=session,
        transcription_repo=transcription_repo,
        message_repo=message_repo,
        llm=llm,
        model=settings.OPENAI_MODEL,
        token_budget=settings.CONTEXT_TOKEN_BUDGET,
        history_limit=settings.HISTORY_MESSAGE_LIMIT,
    )
