"""Token estimation via tiktoken (ADR-004).

Encoding is chosen by the configured model; falls back to o200k_base then
cl100k_base for unknown models.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken

_FALLBACK_ENCODINGS = ("o200k_base", "cl100k_base")


@lru_cache(maxsize=8)
def _get_encoding(model: str) -> tiktoken.Encoding:
    """Resolve a tiktoken encoding for the given model with fallbacks."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        pass
    for name in _FALLBACK_ENCODINGS:
        try:
            return tiktoken.get_encoding(name)
        except (KeyError, ValueError):
            continue
    # Last resort: cl100k_base is always bundled with tiktoken.
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str) -> int:
    """Estimate the number of tokens in `text` for `model`."""
    if not text:
        return 0
    return len(_get_encoding(model).encode(text))


def count_messages_tokens(messages: list[dict[str, str]], model: str) -> int:
    """Estimate tokens for a list of chat messages.

    Adds a small per-message overhead to approximate the chat format framing,
    keeping the estimate conservative (ADR-004).
    """
    per_message_overhead = 4
    total = 0
    for message in messages:
        total += per_message_overhead
        for value in message.values():
            total += count_tokens(value, model)
    return total + 2
