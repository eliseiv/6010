"""Health endpoint (public, no API key). Optionally checks DB availability."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.logging import get_logger
from app.dependencies import SessionDep

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health")
async def health(session: SessionDep, response: Response) -> dict[str, str]:
    """Return service health. Does not call OpenAI.

    Checks DB reachability; on failure returns 503 {"status": "degraded"}.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Health check: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded"}
    return {"status": "ok"}
