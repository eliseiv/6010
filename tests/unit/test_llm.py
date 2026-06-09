"""Unit tests for LLMClient: retry/backoff and error mapping (cases 9, 10).

OpenAI SDK boundary is mocked — no real network. asyncio.sleep is patched so
backoff does not add real wall-clock delay.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
)

from app.core.config import Settings
from app.core.errors import ModelError, ModelTimeoutError
from app.services import llm as llm_module
from app.services.llm import LLMClient

pytestmark = pytest.mark.asyncio


def _settings() -> Settings:
    return Settings(
        API_KEY="k",
        OPENAI_API_KEY="sk-test",
        DATABASE_URL="postgresql+asyncpg://x/y",
    )


def _ok_response(content: str = "ответ"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Patch backoff sleep to a no-op so retries don't add real delay."""
    sleeps: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(llm_module.asyncio, "sleep", _fake_sleep)
    return sleeps


def _patch_create(client: LLMClient, mock: AsyncMock) -> None:
    client._client.chat.completions.create = mock  # type: ignore[attr-defined]


async def test_complete_returns_content_on_success() -> None:
    client = LLMClient(_settings())
    _patch_create(client, AsyncMock(return_value=_ok_response("привет")))
    result = await client.complete([{"role": "user", "content": "hi"}])
    assert result == "привет"


async def test_timeout_retries_once_then_504(_no_sleep) -> None:
    client = LLMClient(_settings())
    mock = AsyncMock(side_effect=APITimeoutError(request=SimpleNamespace()))
    _patch_create(client, mock)

    with pytest.raises(ModelTimeoutError):
        await client.complete([{"role": "user", "content": "hi"}])

    # initial attempt + 1 retry = 2 calls; 1 backoff sleep between them.
    assert mock.await_count == 2
    assert len(_no_sleep) == 1


async def test_connection_error_retries_then_502(_no_sleep) -> None:
    client = LLMClient(_settings())
    mock = AsyncMock(side_effect=APIConnectionError(request=SimpleNamespace()))
    _patch_create(client, mock)

    with pytest.raises(ModelError):
        await client.complete([{"role": "user", "content": "hi"}])

    assert mock.await_count == 2
    assert len(_no_sleep) == 1


async def test_retry_succeeds_on_second_attempt(_no_sleep) -> None:
    client = LLMClient(_settings())
    mock = AsyncMock(
        side_effect=[APITimeoutError(request=SimpleNamespace()), _ok_response("ok")]
    )
    _patch_create(client, mock)

    result = await client.complete([{"role": "user", "content": "hi"}])
    assert result == "ok"
    assert mock.await_count == 2


async def test_empty_content_maps_to_model_error() -> None:
    client = LLMClient(_settings())
    _patch_create(client, AsyncMock(return_value=_ok_response("   ")))
    with pytest.raises(ModelError):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_no_choices_maps_to_model_error() -> None:
    client = LLMClient(_settings())
    _patch_create(client, AsyncMock(return_value=SimpleNamespace(choices=[])))
    with pytest.raises(ModelError):
        await client.complete([{"role": "user", "content": "hi"}])
