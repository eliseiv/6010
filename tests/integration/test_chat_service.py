"""Service-level integration for ChatService.handle against the test DB.

Complements the HTTP tests in test_chat.py and exercises the orchestration flow
(persist user msg -> LLM -> structured_blocks -> persist assistant msg) directly,
which also makes coverage measurement reliable for the async service body.
OpenAI is replaced by a fake client (no real calls).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.errors import (
    EmptyTranscriptionError,
    ModelError,
    SummaryNotFoundError,
    TranscriptionNotFoundError,
)
from app.core.prompts import QuickCommand
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.transcriptions import TranscriptionRepository
from app.schemas.chat import ChatMessageRequest
from app.services.chat import ChatService

pytestmark = pytest.mark.asyncio


class _FakeLLM:
    def __init__(self, content="ответ ассистента", exc=None):
        self._content = content
        self._exc = exc
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages):
        self.calls.append(messages)
        if self._exc is not None:
            raise self._exc
        return self._content


def _service(session, llm, *, budget=100_000):
    return ChatService(
        session=session,
        transcription_repo=TranscriptionRepository(session),
        message_repo=ChatMessageRepository(session),
        llm=llm,
        model="gpt-4o-mini",
        token_budget=budget,
        history_limit=20,
    )


async def _make_transcription(session, full_text="Полный текст.", summary=None):
    repo = TranscriptionRepository(session)
    t = await repo.create_transcription(full_text=full_text, language="ru")
    sid = None
    if summary is not None:
        s = await repo.create_summary(transcription_id=t.id, summary_text=summary)
        sid = s.id
    await session.commit()
    return t.id, sid


async def test_handle_persists_user_and_assistant(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session)
    llm = _FakeLLM("Привет!")
    service = _service(db_session, llm)

    resp = await service.handle(
        ChatMessageRequest(transcription_id=transcription_id, message="hi")
    )
    assert resp.role == "assistant"
    assert resp.content == "Привет!"
    assert resp.context_mode == "full"

    repo = ChatMessageRepository(db_session)
    rows = await repo.list_paginated(transcription_id, limit=50, offset=0, order="asc")
    assert [r.role for r in rows] == ["user", "assistant"]
    assert llm.calls  # LLM was invoked once


async def test_handle_resolves_summary_by_id(db_session) -> None:
    transcription_id, summary_id = await _make_transcription(
        db_session, summary="Summary текст."
    )
    service = _service(db_session, _FakeLLM())
    resp = await service.handle(
        ChatMessageRequest(
            transcription_id=transcription_id, message="q", summary_id=summary_id
        )
    )
    assert resp.role == "assistant"


async def test_handle_uses_latest_summary_when_no_id(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session, summary="Latest summary.")
    llm = _FakeLLM()
    service = _service(db_session, llm)
    await service.handle(ChatMessageRequest(transcription_id=transcription_id, message="q"))
    # The summary text must be present in the assembled context.
    joined = "\n".join(m["content"] for m in llm.calls[0])
    assert "Latest summary." in joined


async def test_handle_list_command_persists_structured_blocks(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session)
    content = 'Задачи.\n```json\n[{"type": "task", "text": "T"}]\n```'
    service = _service(db_session, _FakeLLM(content))
    resp = await service.handle(
        ChatMessageRequest(
            transcription_id=transcription_id,
            message="выполни",
            quick_command_type=QuickCommand.EXTRACT_TASKS,
        )
    )
    assert resp.structured_blocks == [
        {"type": "task", "text": "T", "owner": None, "due": None, "done": False}
    ]


async def test_handle_empty_message_raises(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session)
    service = _service(db_session, _FakeLLM())
    with pytest.raises(EmptyTranscriptionError):
        await service.handle(
            ChatMessageRequest(transcription_id=transcription_id, message="   ")
        )


async def test_handle_unknown_transcription_raises(db_session) -> None:
    service = _service(db_session, _FakeLLM())
    with pytest.raises(TranscriptionNotFoundError):
        await service.handle(
            ChatMessageRequest(transcription_id=uuid.uuid4(), message="hi")
        )


async def test_handle_empty_transcription_text_raises(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session, full_text="   ")
    service = _service(db_session, _FakeLLM())
    with pytest.raises(EmptyTranscriptionError):
        await service.handle(
            ChatMessageRequest(transcription_id=transcription_id, message="hi")
        )


async def test_handle_wrong_summary_raises(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session)
    service = _service(db_session, _FakeLLM())
    with pytest.raises(SummaryNotFoundError):
        await service.handle(
            ChatMessageRequest(
                transcription_id=transcription_id,
                message="hi",
                summary_id=uuid.uuid4(),
            )
        )


async def test_handle_llm_error_keeps_user_message_only(db_session) -> None:
    transcription_id, _ = await _make_transcription(db_session)
    service = _service(db_session, _FakeLLM(exc=ModelError("boom")))
    with pytest.raises(ModelError):
        await service.handle(
            ChatMessageRequest(transcription_id=transcription_id, message="вопрос")
        )
    # User message committed before the LLM call remains; no assistant message.
    repo = ChatMessageRepository(db_session)
    rows = await repo.list_paginated(transcription_id, limit=50, offset=0, order="asc")
    assert [r.role for r in rows] == ["user"]
