"""Shared pytest fixtures: test settings, Postgres test DB, app + httpx client.

Test DB: a dedicated PostgreSQL 16 instance (06-testing-strategy.md "Тестовая БД").
The DSN is taken from TEST_DATABASE_URL if set, otherwise defaults to the
disposable container started by qa (host port 55432). Schema is created once per
session from the ORM metadata; per-test isolation is achieved by TRUNCATEing all
tables before each test.

OpenAI is NEVER called for real. The default chat fixture overrides the LLMClient
dependency with a fake; resilience/retry tests patch the SDK boundary explicitly.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TEST_API_KEY = "test-api-key-32-bytes-aaaaaaaaaaaa"
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://test:test@127.0.0.1:55432/test",
)

# Required settings must exist before app.core.config is imported by app modules.
os.environ.setdefault("API_KEY", TEST_API_KEY)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
# Keep token budget modest so summary-first/413 tests are fast and deterministic.
os.environ.setdefault("CONTEXT_TOKEN_BUDGET", "100000")

# Import the models package so all ORM tables register on Base.metadata.
import app.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db_session  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


# Schema is created once per test session. The flag avoids re-running DDL for
# every function-scoped engine. Function-scoped engines keep each test on its own
# event loop (asyncpg requires the connection and the loop to match).
_SCHEMA_READY = {"done": False}


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator:
    """Function-scoped async engine bound to the test database.

    Created per test so the asyncpg connection lives on the test's event loop.
    On first use it (re)creates the schema; afterwards it only truncates.
    """
    eng = create_async_engine(TEST_DATABASE_URL, future=True)
    async with eng.begin() as conn:
        # gen_random_uuid() is core in PG13+, but pgcrypto guarantees it.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        if not _SCHEMA_READY["done"]:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            _SCHEMA_READY["done"] = True
        # Per-test isolation: start from empty tables.
        await conn.execute(
            text("TRUNCATE chat_messages, summaries, transcriptions RESTART IDENTITY CASCADE")
        )
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """A raw session for direct DB arrange/assert in tests."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def app(session_factory):
    """Build the FastAPI app with the DB dependency overridden to the test DB.

    A fresh session is opened per request (mirrors prod get_db_session: commit on
    success, rollback on error).
    """
    from app.main import create_app

    application = create_app()

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_db_session] = _override_session
    return application


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient bound to the ASGI app (06-testing-strategy: ASGITransport)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    """Ensure settings reflect the test env (single cached instance)."""
    get_settings.cache_clear()
    get_settings()


# --- LLM overrides (OpenAI must never be called for real) -------------------


class FakeLLMClient:
    """Stand-in for LLMClient: returns a canned answer and records the context."""

    def __init__(self, content: str = "Ответ ассистента.") -> None:
        self._content = content
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self._content


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


@pytest.fixture
def use_fake_llm(app, fake_llm):
    """Override the chat service's LLM dependency with the fake client."""
    from app.dependencies import get_llm_client

    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    return fake_llm


@pytest_asyncio.fixture
async def ingest(client, auth_headers):
    """Helper: create a transcription (optionally with summary) via the API.

    Returns (transcription_id, summary_id|None).
    """

    async def _ingest(
        full_text: str = "Полный текст транскрибации для теста.",
        *,
        language: str | None = None,
        summary: str | None = None,
    ) -> tuple[str, str | None]:
        payload: dict[str, object] = {"full_text": full_text}
        if language is not None:
            payload["language"] = language
        if summary is not None:
            payload["summary"] = summary
        resp = await client.post("/api/transcriptions", headers=auth_headers, json=payload)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        return body["transcription_id"], body["summary_id"]

    return _ingest
