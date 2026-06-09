"""OpenAI integration: a single chat completion call with timeout and one retry.

Maps OpenAI/client failures to domain errors:
  - timeout                  -> ModelTimeoutError (504)
  - API/connection/other     -> ModelError (502)

The OpenAI client is constructed with the configured per-request timeout. We add
one retry with exponential backoff for transient failures (we disable the SDK's
built-in retries to keep retry/backoff explicit and bounded). API keys are never
logged.
"""

from __future__ import annotations

import asyncio

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
)

from app.core.config import Settings
from app.core.errors import ModelError, ModelTimeoutError
from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_ATTEMPTS = 2  # initial attempt + 1 retry
_BACKOFF_BASE_SECONDS = 0.5


class LLMClient:
    """Thin wrapper over AsyncOpenAI chat completions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=0,
        )

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Run a chat completion, returning the assistant message content.

        Retries once on timeout/connection errors with exponential backoff.
        Raises ModelTimeoutError (504) on timeout and ModelError (502) otherwise.
        """
        last_timeout: Exception | None = None
        last_error: Exception | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._settings.OPENAI_MODEL,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=self._settings.MAX_OUTPUT_TOKENS,
                )
            except APITimeoutError as exc:
                last_timeout = exc
                logger.warning("OpenAI timeout on attempt %d/%d", attempt, _MAX_ATTEMPTS)
            except (APIConnectionError, APIStatusError) as exc:
                last_error = exc
                logger.warning(
                    "OpenAI API error on attempt %d/%d: %s",
                    attempt,
                    _MAX_ATTEMPTS,
                    type(exc).__name__,
                )
            except OpenAIError as exc:
                # Non-transient client error: do not retry.
                logger.warning("OpenAI client error: %s", type(exc).__name__)
                raise ModelError("OpenAI returned a model/API error.") from exc
            else:
                content = self._extract_content(response)
                if content is None:
                    raise ModelError("OpenAI returned an empty/invalid response.")
                return content

            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * attempt)

        if last_timeout is not None:
            raise ModelTimeoutError("OpenAI request timed out.") from last_timeout
        raise ModelError("OpenAI returned a model/API error.") from last_error

    @staticmethod
    def _extract_content(response: object) -> str | None:
        """Safely extract the first choice message content from a response."""
        choices = getattr(response, "choices", None)
        if not choices:
            return None
        message = getattr(choices[0], "message", None)
        if message is None:
            return None
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            return None
        return content
