"""Unit tests for token counting and prompt/command selection."""

from __future__ import annotations

from app.core.prompts import (
    COMMAND_PROMPTS,
    LIST_COMMANDS,
    QuickCommand,
    command_instruction,
    is_list_command,
)
from app.core.tokens import count_messages_tokens, count_tokens

MODEL = "gpt-4o-mini"


def test_count_tokens_empty_is_zero() -> None:
    assert count_tokens("", MODEL) == 0


def test_count_tokens_monotonic() -> None:
    assert count_tokens("a", MODEL) < count_tokens("a much longer string here", MODEL)


def test_count_messages_tokens_includes_overhead() -> None:
    msgs = [{"role": "user", "content": "hi"}]
    total = count_messages_tokens(msgs, MODEL)
    # per-message overhead (4) + content tokens + framing (2) > raw content count.
    assert total > count_tokens("hi", MODEL)


def test_unknown_model_falls_back_without_error() -> None:
    # Should not raise; uses fallback encoding.
    assert count_tokens("hello", "totally-unknown-model-xyz") > 0


def test_is_list_command_matches_only_list_commands() -> None:
    for cmd in LIST_COMMANDS:
        assert is_list_command(cmd) is True
    assert is_list_command(QuickCommand.MAKE_SUMMARY) is False
    assert is_list_command(None) is False


def test_list_commands_exact_set() -> None:
    assert LIST_COMMANDS == frozenset(
        {
            QuickCommand.EXTRACT_TASKS,
            QuickCommand.CHECKLIST,
            QuickCommand.DECISIONS,
            QuickCommand.RISKS_QUESTIONS,
        }
    )


def test_every_command_has_a_prompt() -> None:
    for cmd in QuickCommand:
        assert cmd in COMMAND_PROMPTS
        assert COMMAND_PROMPTS[cmd].strip()


def test_translate_adds_language_hint() -> None:
    instruction = command_instruction(QuickCommand.TRANSLATE_OR_ADAPT, language="en")
    assert "en" in instruction


def test_translate_without_language_has_no_hint_suffix() -> None:
    instruction = command_instruction(QuickCommand.TRANSLATE_OR_ADAPT, language=None)
    assert instruction == COMMAND_PROMPTS[QuickCommand.TRANSLATE_OR_ADAPT]
