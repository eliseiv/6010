"""Unit tests for the deeper truncation branches of build_context (ADR-004 step 4).

Covers: history truncation, then selected_text/summary truncation, leading to
context_mode == "truncated".
"""

from __future__ import annotations

import pytest

from app.core.errors import ContextTooLongError
from app.core.prompts import SYSTEM_PROMPT
from app.core.tokens import count_tokens
from app.services.context import (
    ContextInputs,
    HistoryMessage,
    build_context,
)

MODEL = "gpt-4o-mini"
# These tests need a budget that sits JUST above the system-prompt floor: large
# enough that the minimal context (system + short message) fits, but small
# enough that history/summary/selected_text must be truncated. The floor moves
# whenever SYSTEM_PROMPT changes (e.g. ADR-007 language-mirroring), so derive it
# from the actual prompt instead of hardcoding a magic number.
_SYS_FLOOR = count_tokens(SYSTEM_PROMPT, MODEL)
# Headroom above the floor for the user turn + per-message framing; still far
# below what history/summary/selected_text would need, forcing truncation.
TIGHT_BUDGET = _SYS_FLOOR + 30


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
            token_budget=TIGHT_BUDGET,
            message="q",
            full_text="полный текст " * 200,
            summary="кратко",
            history=_history(10, words=40),
        )
    )
    assert result.context_truncated is True
    assert result.context_mode in ("summary_first", "truncated")
    assert result.token_count <= TIGHT_BUDGET


def test_summary_truncated_when_history_dropped() -> None:
    """A large summary with no room for history is truncated to fit (truncated mode)."""
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=TIGHT_BUDGET,
            message="q",
            full_text="x " * 1000,
            summary="длинное summary " * 200,
            history=_history(5, words=50),
        )
    )
    assert result.context_truncated is True
    assert result.token_count <= TIGHT_BUDGET


def test_selected_text_truncated_to_fit() -> None:
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=TIGHT_BUDGET,
            message="q",
            full_text="x " * 1000,
            summary="кратко",
            selected_text="выбранный фрагмент " * 200,
        )
    )
    assert result.context_truncated is True
    assert result.token_count <= TIGHT_BUDGET


def test_truncated_mode_when_only_message_and_summary_fit() -> None:
    """Everything heavy is dropped/truncated; result fits -> not 413."""
    # Slightly more headroom than TIGHT_BUDGET so that system + message + a
    # truncated summary still fit (this test asserts a fit, not a 413).
    budget = _SYS_FLOOR + 90
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=budget,
            message="короткий вопрос",
            full_text="много текста " * 500,
            summary="достаточно длинное summary " * 50,
            selected_text="и выбранный фрагмент " * 50,
            history=_history(8, words=40),
        )
    )
    assert result.token_count <= budget
    assert result.context_truncated is True


def test_413_when_message_alone_too_big_even_with_everything_dropped() -> None:
    with pytest.raises(ContextTooLongError):
        build_context(
            ContextInputs(
                model=MODEL,
                # Budget above the system-prompt floor, yet the message alone
                # overflows it -> 413 even after everything else is dropped.
                token_budget=TIGHT_BUDGET,
                message="очень длинное сообщение " * 200,
                full_text="t",
                summary="s " * 100,
                selected_text="sel " * 100,
                history=_history(5),
            )
        )
