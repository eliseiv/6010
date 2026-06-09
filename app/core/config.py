"""Application configuration loaded from environment / .env (pydantic-settings).

All secrets and tunables come exclusively from the environment. Defaults for
non-secret tunables follow ADR-002 / 07-deployment.md. Secrets (API_KEY,
OPENAI_API_KEY, DATABASE_URL) have no defaults and are required.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings sourced from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Secrets (required) ---
    API_KEY: str = Field(..., min_length=1, description="Service access key for X-API-Key.")
    OPENAI_API_KEY: str = Field(..., min_length=1, description="OpenAI API key.")
    DATABASE_URL: str = Field(
        ...,
        min_length=1,
        description="Async PostgreSQL DSN, e.g. postgresql+asyncpg://app:app@db:5432/app.",
    )

    # --- OpenAI tunables (ADR-002) ---
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI model name.")
    OPENAI_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, description="OpenAI request timeout.")
    CONTEXT_TOKEN_BUDGET: int = Field(default=100_000, gt=0, description="Context token budget.")
    MAX_OUTPUT_TOKENS: int = Field(default=2_000, gt=0, description="Max output tokens.")

    # --- History window for context assembly ---
    HISTORY_MESSAGE_LIMIT: int = Field(
        default=20,
        gt=0,
        description="Max recent thread messages included into context (newest first).",
    )

    # --- Observability ---
    LOG_LEVEL: str = Field(default="INFO", description="Logging level.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
