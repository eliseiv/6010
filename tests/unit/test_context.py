"""Unit tests for context assembly (summary-first, truncation, 413)."""

from __future__ import annotations

import pytest

from app.core.errors import ContextTooLongError
from app.core.prompts import SYSTEM_PROMPT, QuickCommand
from app.core.tokens import count_tokens
from app.services.context import (
    TRUNCATION_NOTE,
    ContextInputs,
    HistoryMessage,
    build_context,
)

MODEL = "gpt-4o-mini"
# Budget just above the system-prompt floor: minimal context fits, but heavy
# parts (full_text/summary) must be truncated. Derived from SYSTEM_PROMPT so it
# survives prompt edits (e.g. ADR-007 language-mirroring) rather than hardcoding.
TIGHT_BUDGET = count_tokens(SYSTEM_PROMPT, MODEL) + 30


def test_small_context_is_full_mode() -> None:
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=100_000,
            message="вопрос",
            full_text="небольшой текст",
        )
    )
    assert result.context_mode == "full"
    assert result.context_truncated is False
    assert result.token_count <= 100_000
    # System prompt without truncation note.
    assert TRUNCATION_NOTE not in result.messages[0]["content"]


def test_long_text_with_summary_drops_full_text() -> None:
    long_text = "длинный кусок текста " * 2000
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=TIGHT_BUDGET,
            message="вопрос",
            full_text=long_text,
            summary="короткое summary",
        )
    )
    assert result.context_mode in ("summary_first", "truncated")
    assert result.context_truncated is True
    assert result.token_count <= TIGHT_BUDGET
    assert TRUNCATION_NOTE in result.messages[0]["content"]
    # full_text must not appear verbatim in any message.
    joined = "\n".join(m["content"] for m in result.messages)
    assert long_text not in joined


def test_long_text_without_summary_truncates_full_text() -> None:
    long_text = "слово " * 3000
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=TIGHT_BUDGET,
            message="вопрос",
            full_text=long_text,
        )
    )
    assert result.context_truncated is True
    assert result.token_count <= TIGHT_BUDGET


def test_minimal_context_over_budget_raises_413() -> None:
    huge_message = "очень длинное сообщение " * 5000
    with pytest.raises(ContextTooLongError):
        build_context(
            ContextInputs(
                model=MODEL,
                token_budget=50,
                message=huge_message,
                full_text="t",
            )
        )


def test_history_included_in_full_mode() -> None:
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=100_000,
            message="now",
            full_text="text",
            history=[
                HistoryMessage(role="user", content="prev-q"),
                HistoryMessage(role="assistant", content="prev-a"),
            ],
        )
    )
    contents = [m["content"] for m in result.messages]
    assert "prev-q" in contents
    assert "prev-a" in contents


def test_quick_command_instruction_in_user_turn() -> None:
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=100_000,
            message="",
            full_text="text",
            quick_command=QuickCommand.EXTRACT_TASKS,
        )
    )
    user_turn = result.messages[-1]
    assert user_turn["role"] == "user"
    assert "action items" in user_turn["content"]


def test_selected_text_present_in_context() -> None:
    result = build_context(
        ContextInputs(
            model=MODEL,
            token_budget=100_000,
            message="q",
            full_text="text",
            selected_text="ВАЖНЫЙ ФРАГМЕНТ",
        )
    )
    joined = "\n".join(m["content"] for m in result.messages)
    assert "ВАЖНЫЙ ФРАГМЕНТ" in joined
