"""LLM failure resilience — acceptance case 10 + 02-api-contracts:124.

On model error -> 502, on timeout -> 504. The user message must remain in
history; the assistant message must NOT be created.
"""

from __future__ import annotations

import pytest

from app.core.errors import ModelError, ModelTimeoutError

pytestmark = pytest.mark.asyncio


class FailingLLM:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def complete(self, messages: list[dict[str, str]]) -> str:
        raise self._exc


@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (ModelError("boom"), 502, "model_error"),
        (ModelTimeoutError("slow"), 504, "model_timeout"),
    ],
)
async def test_llm_failure_maps_to_status_and_persists_user_message(
    client, auth_headers, ingest, app, exc, expected_status, expected_code
) -> None:
    from app.dependencies import get_llm_client

    app.dependency_overrides[get_llm_client] = lambda: FailingLLM(exc)

    transcription_id, _ = await ingest()
    resp = await client.post(
        "/api/chat/messages",
        headers=auth_headers,
        json={"transcription_id": transcription_id, "message": "вопрос"},
    )
    assert resp.status_code == expected_status
    assert resp.json()["error"]["code"] == expected_code

    # History: user message stays, assistant message absent.
    history = await client.get(
        f"/api/transcriptions/{transcription_id}/messages", headers=auth_headers
    )
    assert history.status_code == 200
    messages = history.json()["messages"]
    roles = [m["role"] for m in messages]
    assert roles == ["user"]
    assert messages[0]["content"] == "вопрос"
