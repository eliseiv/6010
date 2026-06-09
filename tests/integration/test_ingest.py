"""Ingest endpoint integration tests — acceptance case 1, 4 (empty)."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_ingest_returns_transcription_id(client, auth_headers) -> None:
    resp = await client.post(
        "/api/transcriptions",
        headers=auth_headers,
        json={"full_text": "Полный текст встречи.", "language": "ru"},
    )
    assert resp.status_code == 201
    body = resp.json()
    # transcription_id present and a valid UUID; no summary -> summary_id null.
    uuid.UUID(body["transcription_id"])
    assert body["summary_id"] is None
    assert "created_at" in body


async def test_ingest_with_summary_returns_summary_id(client, auth_headers) -> None:
    resp = await client.post(
        "/api/transcriptions",
        headers=auth_headers,
        json={"full_text": "Полный текст.", "summary": "Краткое summary."},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["summary_id"] is not None
    uuid.UUID(body["summary_id"])


async def test_ingest_blank_summary_yields_null_summary_id(client, auth_headers) -> None:
    """summary present but only whitespace -> summary_id stays null."""
    resp = await client.post(
        "/api/transcriptions",
        headers=auth_headers,
        json={"full_text": "Текст.", "summary": "   "},
    )
    assert resp.status_code == 201
    assert resp.json()["summary_id"] is None


async def test_ingest_empty_full_text_returns_400(client, auth_headers) -> None:
    resp = await client.post(
        "/api/transcriptions",
        headers=auth_headers,
        json={"full_text": "   "},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "empty_transcription"


async def test_ingest_missing_full_text_returns_422(client, auth_headers) -> None:
    resp = await client.post("/api/transcriptions", headers=auth_headers, json={})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
