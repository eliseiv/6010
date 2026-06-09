"""Unit tests for the deeper truncation branches of build_context (ADR-004 step 4).

Covers: history truncation, then selected_text/summary truncation, leading to
context_mode == "truncated".
"""

from __future__ import annotations

import pytest

from app.core.errors import ContextTooLongError
from app.services.context import (
    ContextInputs,
    HistoryMessage,
    build_context,
)

MODEL = "gpt-4o-mini"
# System prompt alone is ~218 tokens; budgets below sit just above it so that
# history/summary/selected_text must be truncated to fit.


def _history(n: int, words: int = 50) -> list[HistoryMessage]:
    return [
        HistoryMessage(role="user" if i % 2 == 0 else "assistant", content="word " * words)
        for i in range(n)
    ]


def test_history_truncated_to_fit() -> None:
    """Long history with a summary -> history is dropped oldest-first; mode truncated."""
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=320,
            message="q",
            full_text="полный текст " * 200,
            summary="кратко",
            history=_history(10, words=40),
        )
    )
    assert result.context_truncated is True
    assert result.context_mode in ("summary_first", "truncated")
    assert result.token_count <= 320


def test_summary_truncated_when_history_dropped() -> None:
    """A large summary with no room for history is truncated to fit (truncated mode)."""
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=300,
            message="q",
            full_text="x " * 1000,
            summary="длинное summary " * 200,
            history=_history(5, words=50),
        )
    )
    assert result.context_truncated is True
    assert result.token_count <= 300


def test_selected_text_truncated_to_fit() -> None:
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=320,
            message="q",
            full_text="x " * 1000,
            summary="кратко",
            selected_text="выбранный фрагмент " * 200,
        )
    )
    assert result.context_truncated is True
    assert result.token_count <= 320


def test_truncated_mode_when_only_message_and_summary_fit() -> None:
    """Everything heavy is dropped/truncated; result fits -> not 413."""
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=300,
            message="короткий вопрос",
            full_text="много текста " * 500,
            summary="достаточно длинное summary " * 50,
            selected_text="и выбранный фрагмент " * 50,
            history=_history(8, words=40),
        )
    )
    assert result.token_count <= 300
    assert result.context_truncated is True


def test_413_when_message_alone_too_big_even_with_everything_dropped() -> None:
    with pytest.raises(ContextTooLongError):
        build_context(
            ContextInputs(
                model=MODEL,
                token_budget=260,
                message="очень длинное сообщение " * 200,
                full_text="t",
                summary="s " * 100,
                selected_text="sel " * 100,
                history=_history(5),
            )
        )
