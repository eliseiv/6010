"""Deterministic unit tests for the language directive in the assembled messages.

Case 14 (06-testing-strategy.md): in the assembled request the LAST message must
be a `system` message carrying the language directive with the correct
`{language_name}`, and that directive must NOT be truncated/dropped under
summary-first/truncation. For `translate_or_adapt` the directive is absent
(ChatService passes `language_directive=None`), so the last message is the user
turn.

These tests check the REAL assembled `messages[]` (the array that is later sent to
OpenAI), not merely the presence of a string somewhere in a prompt. No LLM runs.
"""

from __future__ import annotations

from app.core.prompts import LANGUAGE_DIRECTIVE_TEMPLATE, QuickCommand
from app.core.tokens import count_tokens
from app.services.chat import ChatService
from app.services.context import ContextInputs, HistoryMessage, build_context

MODEL = "gpt-4o-mini"


def _directive_for(language_name: str) -> str:
    return LANGUAGE_DIRECTIVE_TEMPLATE.format(language_name=language_name)


# --- Directive is the last system message with the right language -----------


def test_directive_is_last_system_message_english() -> None:
    """EN directive -> last message is a system message requiring English."""
    inputs = ContextInputs(
        model=MODEL,
        token_budget=100_000,
        message="What tasks were discussed?",
        full_text="Полный текст транскрибации на русском.",
        language="ru",
        language_directive=_directive_for("English"),
    )
    result = build_context(inputs)
    last = result.messages[-1]
    assert last["role"] == "system"
    assert "English" in last["content"]
    assert "Respond ONLY in English" in last["content"]
    # And it is genuinely the *trailing* message (recency), after the user turn.
    assert result.messages[-2]["role"] == "user"


def test_directive_is_last_system_message_russian() -> None:
    """RU directive -> last message requires Russian."""
    inputs = ContextInputs(
        model=MODEL,
        token_budget=100_000,
        message="Какие задачи обсуждали?",
        full_text="Full transcription text in English.",
        language="en",
        language_directive=_directive_for("Russian"),
    )
    result = build_context(inputs)
    last = result.messages[-1]
    assert last["role"] == "system"
    assert "Russian" in last["content"]
    assert "Respond ONLY in Russian" in last["content"]


def test_no_directive_means_last_message_is_user() -> None:
    """language_directive=None (translate_or_adapt) -> no trailing system directive."""
    inputs = ContextInputs(
        model=MODEL,
        token_budget=100_000,
        message="Translate this",
        full_text="Полный текст.",
        quick_command=QuickCommand.TRANSLATE_OR_ADAPT,
        language="ru",
        language_directive=None,
    )
    result = build_context(inputs)
    assert result.messages[-1]["role"] == "user"
    # No system message carries the mirroring directive at all.
    assert not any(
        "Respond ONLY in" in m["content"] for m in result.messages if m["role"] == "system"
    )


# --- Directive survives summary-first and hard truncation -------------------


def test_directive_survives_summary_first() -> None:
    """Under summary-first the directive stays the last (system) message."""
    directive = _directive_for("English")
    # Budget tight enough to force dropping full_text (summary-first), but the
    # directive is always counted and preserved.
    from app.core.prompts import SYSTEM_PROMPT

    budget = count_tokens(SYSTEM_PROMPT, MODEL) + count_tokens(directive, MODEL) + 60
    long_text = "длинный текст транскрибации " * 3000
    inputs = ContextInputs(
        model=MODEL,
        token_budget=budget,
        message="What was decided?",
        full_text=long_text,
        summary="Краткое summary.",
        language="ru",
        language_directive=directive,
    )
    result = build_context(inputs)
    assert result.context_mode in ("summary_first", "truncated")
    assert result.context_truncated is True
    last = result.messages[-1]
    assert last["role"] == "system"
    assert "English" in last["content"]
    # full_text must have been dropped, but the directive must remain.
    assert long_text not in "\n".join(m["content"] for m in result.messages)


def test_directive_survives_hard_history_truncation() -> None:
    """Under heavy history truncation the directive remains last and intact."""
    directive = _directive_for("Russian")
    from app.core.prompts import SYSTEM_PROMPT

    budget = count_tokens(SYSTEM_PROMPT, MODEL) + count_tokens(directive, MODEL) + 40
    history = [
        HistoryMessage(role="user", content="старое сообщение " * 200) for _ in range(10)
    ]
    inputs = ContextInputs(
        model=MODEL,
        token_budget=budget,
        message="Что в итоге?",
        full_text="текст " * 2000,
        summary="summary " * 200,
        language="ru",
        history=history,
        language_directive=directive,
    )
    result = build_context(inputs)
    assert result.context_truncated is True
    last = result.messages[-1]
    assert last["role"] == "system"
    assert "Russian" in last["content"]
    assert result.token_count <= budget


# --- ChatService._build_language_directive selection logic -------------------


def _make_service() -> ChatService:
    # Only _build_language_directive is exercised; collaborators are unused here.
    return ChatService(
        session=None,  # type: ignore[arg-type]
        transcription_repo=None,  # type: ignore[arg-type]
        message_repo=None,  # type: ignore[arg-type]
        llm=None,  # type: ignore[arg-type]
        model=MODEL,
        token_budget=100_000,
        history_limit=20,
    )


class _Payload:
    """Minimal stand-in for ChatMessageRequest for the directive builder."""

    def __init__(self, message: str, quick_command_type: QuickCommand | None) -> None:
        self.message = message
        self.quick_command_type = quick_command_type


def test_service_builds_english_directive_for_en_message_over_ru_context() -> None:
    service = _make_service()
    directive = service._build_language_directive(
        _Payload("What tasks were discussed?", None),  # type: ignore[arg-type]
        "ru",
    )
    assert directive is not None
    assert "English" in directive
    assert "Respond ONLY in English" in directive


def test_service_builds_russian_directive_for_ru_message() -> None:
    service = _make_service()
    directive = service._build_language_directive(
        _Payload("Какие задачи?", None),  # type: ignore[arg-type]
        "en",
    )
    assert directive is not None
    assert "Russian" in directive


def test_service_skips_directive_for_translate_or_adapt() -> None:
    service = _make_service()
    directive = service._build_language_directive(
        _Payload("translate to spanish", QuickCommand.TRANSLATE_OR_ADAPT),  # type: ignore[arg-type]
        "ru",
    )
    assert directive is None
