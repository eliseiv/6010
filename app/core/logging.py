"""Structured-ish logging setup. Secrets and full transcription text must never
be logged at INFO (only DEBUG, disabled in prod)."""

from __future__ import annotations

import logging

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure root logging using LOG_LEVEL from settings."""
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
