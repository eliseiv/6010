"""Context / summary-first integration — acceptance cases 7, 9.

Uses a small CONTEXT_TOKEN_BUDGET so a long full_text triggers summary-first
truncation, and a minimal context that still overflows triggers 413.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def small_budget_app(app, fake_llm):
    """Run the chat service with a small token budget and the fake LLM.

    Budget 400 exceeds the system prompt (~218 tokens) + a short summary, so a
    summary-first context fits; a multi-thousand-token full_text or message does
    not. Overrides get_settings and get_llm_client so the real get_chat_service
    wiring builds a budget-constrained ChatService.
    """
    from app.core.config import get_settings
    from app.dependencies import get_llm_client

    base = get_settings()
    small = base.model_copy(update={"CONTEXT_TOKEN_BUDGET": 400})

    app.dependency_overrides[get_settings] = lambda: small
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    return app


@pytest.fixture
def attach_fake_llm(small_budget_app):
    """Kept for test-signature compatibility; budget app already wired the LLM."""
    return small_budget_app


async def test_long_text_with_summary_uses_summary_first(
    client, auth_headers, ingest, small_budget_app, attach_fake_llm
) -> None:
    long_text = "Очень длинный текст транскрибации. " * 500
    transcription_id, _ = await ingest(long_text, summary="Короткое summary встречи.")

    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id, "message": "о чём?"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["context_mode"] in ("summary_first", "truncated")
    assert body["context_truncated"] is True


async def test_minimal_context_over_budget_returns_413(
    client, auth_headers, ingest, small_budget_app, attach_fake_llm
) -> None:
    # A single huge message that cannot fit even after dropping everything else.
    huge_message = "слово " * 5000
    transcription_id, _ = await ingest("маленький текст")

    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id, "message": huge_message},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "context_too_long"
