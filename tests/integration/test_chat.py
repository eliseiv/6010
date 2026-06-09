"""Chat endpoint integration tests — happy path, quick commands, errors.

Covers acceptance cases 5, 6, 7, plus the contract for structured_blocks.
OpenAI is replaced by FakeLLMClient (no real calls).
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


# --- Happy path (case 6) ----------------------------------------------------


async def test_chat_happy_path_returns_201(client, auth_headers, ingest, use_fake_llm) -> None:
    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id, "message": "О чём встреча?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    uuid.UUID(body["message_id"])
    assert body["transcription_id"] == transcription_id
    assert body["role"] == "assistant"
    assert body["content"] == "Ответ ассистента."
    assert "created_at" in body
    assert body["context_mode"] == "full"
    # Non-list command -> structured_blocks null.
    assert body["structured_blocks"] is None


async def test_chat_context_full_mode_for_small_text(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest("Короткий текст.")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id, "message": "hi"},
    )
    body = resp.json()
    assert body["context_mode"] == "full"
    assert body["context_truncated"] is False


# --- Quick commands / structured_blocks (case 4) ----------------------------

_TASK_JSON = (
    'Текст ответа.\n```json\n[{"type": "task", "text": "Сделать отчёт", '
    '"owner": "Аня", "due": "пятница", "done": false}]\n```'
)
_DECISION_JSON = (
    'Решения.\n```json\n[{"type": "decision", "text": "Запускаем", '
    '"rationale": "Готовы"}]\n```'
)
_RISKS_JSON = (
    'Риски.\n```json\n[{"type": "risk", "text": "Срыв сроков", "severity": "high"}, '
    '{"type": "question", "text": "Кто отвечает?"}]\n```'
)


@pytest.mark.parametrize(
    ("command", "content", "expected_type"),
    [
        ("extract_tasks", _TASK_JSON, "task"),
        ("checklist", _TASK_JSON, "task"),
        ("decisions", _DECISION_JSON, "decision"),
        ("risks_questions", _RISKS_JSON, "risk"),
    ],
)
async def test_list_command_returns_structured_blocks(
    client, auth_headers, ingest, app, fake_llm, command, content, expected_type
) -> None:
    from app.dependencies import get_llm_client

    fake_llm._content = content
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            # message kept non-empty: fixed rule "empty message -> 400"
            # (03-architecture.md:76) applies even with a quick command.
            "message": "выполни команду",
            "quick_command_type": command,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["quick_command_type"] == command
    blocks = body["structured_blocks"]
    assert isinstance(blocks, list) and len(blocks) >= 1
    assert blocks[0]["type"] == expected_type


async def test_list_command_invalid_json_yields_empty_blocks_still_201(
    client, auth_headers, ingest, app, fake_llm
) -> None:
    from app.dependencies import get_llm_client

    fake_llm._content = "Ответ без валидного json блока. ```json {не json} ```"
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "выполни команду",
            "quick_command_type": "extract_tasks",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["structured_blocks"] == []


async def test_non_list_command_blocks_null(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "сделай summary",
            "quick_command_type": "make_summary",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["structured_blocks"] is None


# --- Errors (case 5) --------------------------------------------------------


async def test_empty_message_returns_400(client, auth_headers, ingest, use_fake_llm) -> None:
    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id, "message": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "empty_transcription"


async def test_nonexistent_transcription_returns_404(
    client, auth_headers, use_fake_llm
) -> None:
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": str(uuid.uuid4()), "message": "hi"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "transcription_not_found"


async def test_nonexistent_summary_returns_404(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "hi",
            "summary_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "summary_not_found"


async def test_summary_of_other_transcription_returns_404(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    """summary_id that belongs to a different transcription -> 404 summary_not_found."""
    t1, _ = await ingest("Текст 1.")
    _, other_summary_id = await ingest("Текст 2.", summary="Summary второй.")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": t1,
            "message": "hi",
            "summary_id": other_summary_id,
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "summary_not_found"


async def test_missing_message_field_returns_422(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
