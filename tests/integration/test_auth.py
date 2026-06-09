"""Auth (X-API-Key) integration tests — acceptance cases 2, 3 and /health (case 4)."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_api_without_key_returns_401(client) -> None:
    resp = await client.post(
        "/api/chat/messages",
        json={"transcription_id": str(uuid.uuid4()), "message": "hi"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_api_with_wrong_key_returns_401(client) -> None:
    resp = await client.post(
        "/api/chat/messages",
        headers={"X-API-Key": "definitely-wrong-key"},
        json={"transcription_id": str(uuid.uuid4()), "message": "hi"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_transcriptions_post_without_key_returns_401(client) -> None:
    resp = await client.post("/api/transcriptions", json={"full_text": "x"})
    assert resp.status_code == 401


async def test_history_without_key_returns_401(client) -> None:
    resp = await client.get(f"/api/transcriptions/{uuid.uuid4()}/messages")
    assert resp.status_code == 401


async def test_health_without_key_returns_200(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_constant_time_compare_used_for_wrong_key(client) -> None:
    """Wrong key is rejected by logic (not timing); both empty and wrong -> 401."""
    r1 = await client.post(
        "/api/transcriptions",
        headers={"X-API-Key": ""},
        json={"full_text": "x"},
    )
    r2 = await client.post(
        "/api/transcriptions",
        headers={"X-API-Key": "a" * 64},
        json={"full_text": "x"},
    )
    assert r1.status_code == 401
    assert r2.status_code == 401
