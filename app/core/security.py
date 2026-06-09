"""API-key authentication. Constant-time comparison (05-security.md, ADR-003)."""

from __future__ import annotations

import secrets

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import UnauthorizedError

API_KEY_HEADER = "X-API-Key"


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    """FastAPI dependency enforcing a valid X-API-Key.

    Uses secrets.compare_digest for constant-time comparison to avoid timing
    attacks. Applied to all /api/* routers; /health is excluded.
    """
    expected = get_settings().API_KEY
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise UnauthorizedError("Missing or invalid API key.")
