"""Integration tests: language directive in the request actually sent to OpenAI.

Cases 15 & 16 (06-testing-strategy.md). These tests prove the REAL server
mechanism end-to-end through the HTTP endpoint:

* Layer A (FakeLLMClient): the assistant flow assembles `messages[]` and we assert
  the trailing message captured by the fake client.
* Layer B (respx): the actual `LLMClient` runs and respx intercepts the HTTP
  request to OpenAI; we assert the directive in the intercepted request body.
  This is the strongest form of case 15 — "the intercepted request to OpenAI
  contains 'Respond ONLY in English' as the last message".

OpenAI is NEVER called for real (FakeLLMClient or respx).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

pytestmark = pytest.mark.asyncio

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _openai_response(content: str = "Ответ.") -> httpx.Response:
    """A minimal valid OpenAI chat.completion JSON the SDK can parse."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


# --- Layer A: assembled messages via the fake client (cases 15/16) ----------


async def test_en_question_ru_context_directive_is_last_message(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    """EN message + RU transcription -> last assembled message requires English."""
    transcription_id, _ = await ingest("Полный текст транскрибации на русском.", language="ru")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "What tasks were discussed?",
        },
    )
    assert resp.status_code == 201, resp.text

    # Inspect the messages the service actually sent to the (fake) LLM.
    assert len(use_fake_llm.calls) == 1
    sent = use_fake_llm.calls[0]
    last = sent[-1]
    assert last["role"] == "system"
    assert "Respond ONLY in English" in last["content"]


async def test_ru_question_directive_requires_russian(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    """RU message -> last assembled message requires Russian."""
    transcription_id, _ = await ingest("Full transcription text in English.", language="en")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "Какие задачи обсуждали на встрече?",
        },
    )
    assert resp.status_code == 201, resp.text
    last = use_fake_llm.calls[0][-1]
    assert last["role"] == "system"
    assert "Respond ONLY in Russian" in last["content"]


async def test_translate_or_adapt_has_no_language_directive(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    """translate_or_adapt -> no mirroring directive; last message is the user turn."""
    transcription_id, _ = await ingest("Полный текст.", language="ru")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "переведи на английский",
            "quick_command_type": "translate_or_adapt",
        },
    )
    assert resp.status_code == 201, resp.text
    sent = use_fake_llm.calls[0]
    assert sent[-1]["role"] == "user"
    assert not any("Respond ONLY in" in m["content"] for m in sent)


async def test_directive_survives_truncation_via_endpoint(
    client, auth_headers, ingest, use_fake_llm, monkeypatch
) -> None:
    """With a tight budget (context_mode=truncated) the directive stays last."""
    # Shrink the service token budget so summary-first/truncation kicks in but the
    # minimal context (system + note + user + directive) still fits (no 413).
    from app.core.config import get_settings
    from app.core.prompts import LANGUAGE_DIRECTIVE_TEMPLATE, SYSTEM_PROMPT
    from app.core.tokens import count_messages_tokens
    from app.services.context import TRUNCATION_NOTE

    model = get_settings().OPENAI_MODEL
    directive = LANGUAGE_DIRECTIVE_TEMPLATE.format(language_name="English")
    minimal_floor = count_messages_tokens(
        [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{TRUNCATION_NOTE}"},
            {"role": "user", "content": "What was decided in the end?"},
            {"role": "system", "content": directive},
        ],
        model,
    )
    # +20 lets a tiny summary be kept while the huge full_text/history are dropped.
    settings = get_settings()
    monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", minimal_floor + 20, raising=False)

    long_ru = "Очень длинный русский текст транскрибации. " * 500
    transcription_id, _ = await ingest(long_ru, language="ru", summary="Краткое summary.")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "What was decided in the end?",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["context_truncated"] is True
    assert body["context_mode"] in ("summary_first", "truncated")
    last = use_fake_llm.calls[0][-1]
    assert last["role"] == "system"
    assert "Respond ONLY in English" in last["content"]


# --- Layer B: real LLMClient, request intercepted by respx (case 15) --------


@respx.mock
async def test_intercepted_openai_request_has_english_directive_last(
    client, auth_headers, ingest
) -> None:
    """Strongest case 15: the actual HTTP request to OpenAI is intercepted and
    its LAST message is the system directive 'Respond ONLY in English'.

    No get_llm_client override here: the real LLMClient runs; respx stops the
    request at the OpenAI boundary (no network).
    """
    route = respx.post(_OPENAI_URL).mock(return_value=_openai_response("OK"))

    transcription_id, _ = await ingest("Полный текст транскрибации на русском.", language="ru")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "What tasks were discussed?",
        },
    )
    assert resp.status_code == 201, resp.text

    assert route.called
    request_body = json.loads(route.calls.last.request.content)
    messages = request_body["messages"]
    last = messages[-1]
    assert last["role"] == "system"
    assert "Respond ONLY in English" in last["content"]
    # And the model name went through as configured (sanity on the real client).
    assert request_body["model"] == "gpt-4o-mini"


@respx.mock
async def test_intercepted_openai_request_has_russian_directive_last(
    client, auth_headers, ingest
) -> None:
    """RU message -> intercepted OpenAI request ends with a Russian directive."""
    route = respx.post(_OPENAI_URL).mock(return_value=_openai_response("OK"))

    transcription_id, _ = await ingest("Full English transcription text.", language="en")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "Какие задачи обсуждали?",
        },
    )
    assert resp.status_code == 201, resp.text

    assert route.called
    messages = json.loads(route.calls.last.request.content)["messages"]
    assert messages[-1]["role"] == "system"
    assert "Respond ONLY in Russian" in messages[-1]["content"]


@respx.mock
async def test_intercepted_translate_request_has_no_language_directive(
    client, auth_headers, ingest
) -> None:
    """translate_or_adapt -> intercepted OpenAI request has no mirroring directive."""
    route = respx.post(_OPENAI_URL).mock(return_value=_openai_response("OK"))

    transcription_id, _ = await ingest("Полный текст.", language="ru")
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={
            "transcription_id": transcription_id,
            "message": "переведи на английский",
            "quick_command_type": "translate_or_adapt",
        },
    )
    assert resp.status_code == 201, resp.text

    assert route.called
    messages = json.loads(route.calls.last.request.content)["messages"]
    assert messages[-1]["role"] == "user"
    assert not any("Respond ONLY in" in m["content"] for m in messages)
