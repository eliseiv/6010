"""FastAPI application: app factory, error handlers, router registration.

Maps domain errors and Pydantic validation errors to the API error contract
(02-api-contracts.md). Stack traces go to logs only.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import DomainError
from app.core.logging import configure_logging, get_logger
from app.routers import chat, health, transcriptions

logger = get_logger(__name__)


def _error_body(code: str, message: str, details: object | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()
    app = FastAPI(title="AI-Chat over Transcriptions", version="0.1.0")

    app.include_router(health.router)
    app.include_router(transcriptions.router)
    app.include_router(chat.router)

    @app.exception_handler(DomainError)
    async def _domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        logger.info("Domain error %s (%d): %s", exc.code, exc.status_code, exc.message)
        return JSONResponse(status_code=exc.status_code, content=exc.to_body())

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "validation_error",
                "Request validation failed.",
                jsonable_errors(exc),
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        # Log full detail (incl. type) but never leak stack trace to the client.
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "Internal server error."),
        )

    return app


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """Return a JSON-serializable view of Pydantic validation errors."""
    cleaned: list[dict[str, object]] = []
    for err in exc.errors():
        cleaned.append(
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return cleaned


app = create_app()
