"""Chat history endpoint — acceptance cases 8, 11, 12 (pagination, order, selected_text)."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _post_message(client, headers, transcription_id, message, **extra):
    return await client.post(
        "/api/chat/messages",
        headers=headers,
        json={"transcription_id": transcription_id, "message": message, **extra},
    )


async def test_history_404_when_transcription_absent(client, auth_headers) -> None:
    resp = await client.get(
        f"/api/transcriptions/{uuid.uuid4()}/messages", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "transcription_not_found"


async def test_history_pagination_and_total(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest()
    for i in range(3):
        r = await _post_message(client, auth_headers, transcription_id, f"вопрос {i}")
        assert r.status_code == 201

    # 3 user + 3 assistant messages = 6 total.
    resp = await client.get(
        f"/api/transcriptions/{transcription_id}/messages",
        headers=auth_headers,
        params={"limit": 2, "offset": 0, "order": "asc"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 6
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["messages"]) == 2

    page2 = await client.get(
        f"/api/transcriptions/{transcription_id}/messages",
        headers=auth_headers,
        params={"limit": 2, "offset": 2, "order": "asc"},
    )
    assert len(page2.json()["messages"]) == 2
    # No overlap between page 1 and page 2.
    ids1 = {m["message_id"] for m in body["messages"]}
    ids2 = {m["message_id"] for m in page2.json()["messages"]}
    assert ids1.isdisjoint(ids2)


async def test_history_order_asc_and_desc(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest()
    for i in range(2):
        await _post_message(client, auth_headers, transcription_id, f"q{i}")

    asc = await client.get(
        f"/api/transcriptions/{transcription_id}/messages",
        headers=auth_headers,
        params={"order": "asc"},
    )
    desc = await client.get(
        f"/api/transcriptions/{transcription_id}/messages",
        headers=auth_headers,
        params={"order": "desc"},
    )
    asc_times = [m["created_at"] for m in asc.json()["messages"]]
    desc_times = [m["created_at"] for m in desc.json()["messages"]]
    assert asc_times == sorted(asc_times)
    assert desc_times == sorted(desc_times, reverse=True)
    # asc first == desc last.
    assert asc.json()["messages"][0]["message_id"] == desc.json()["messages"][-1]["message_id"]


async def test_selected_text_persisted_on_user_message(
    client, auth_headers, ingest, use_fake_llm
) -> None:
    transcription_id, _ = await ingest()
    r = await _post_message(
        client,
        auth_headers,
        transcription_id,
        "поясни",
        selected_text="важный фрагмент",
    )
    assert r.status_code == 201

    history = await client.get(
        f"/api/transcriptions/{transcription_id}/messages",
        headers=auth_headers,
        params={"order": "asc"},
    )
    user_msg = history.json()["messages"][0]
    assert user_msg["role"] == "user"
    assert user_msg["selected_text"] == "важный фрагмент"


async def test_history_invalid_limit_returns_422(client, auth_headers, ingest) -> None:
    transcription_id, _ = await ingest()
    resp = await client.get(
        f"/api/transcriptions/{transcription_id}/messages",
        headers=auth_headers,
        params={"limit": 0},
    )
    assert resp.status_code == 422
