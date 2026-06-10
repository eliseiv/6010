"""Unit tests for the language-mirroring system prompt contract (ADR-007).

These tests are deterministic and do NOT exercise a live model: the actual
language detection is performed by the LLM (which is mocked elsewhere). Here we
only assert the contract that IS deterministic in our code:

1. SYSTEM_PROMPT encodes the language-mirroring rule (answer in the language of
   the current user message; context language must not influence it) and the
   translate_or_adapt exception.
2. The "owner/due not specified" placeholder is phrased relative to the answer's
   language (``не указано`` for RU, ``not specified`` for EN), not as an
   unconditional ``не указано``.
3. The pre-existing prompt rules (grounding, binding to the transcription) are
   preserved by the ADR-007 edit.
4. structured_blocks extraction is independent of any placeholder language — it
   is built from JSON null fields, never from human-readable placeholder text.
"""

from __future__ import annotations

from app.core.prompts import SYSTEM_PROMPT, QuickCommand
from app.services.blocks import extract_structured_blocks


# --- 1. Language-mirroring rule present ------------------------------------


def test_prompt_states_answer_in_current_message_language() -> None:
    """The prompt must instruct answering in the current message's language."""
    assert "на том же языке" in SYSTEM_PROMPT
    assert "текущего" in SYSTEM_PROMPT  # «текущего сообщения / вопроса»


def test_prompt_states_context_language_does_not_influence_answer() -> None:
    """Transcription/summary/history language must be declared non-influential."""
    # Explicit statement that context language does not drive the answer language.
    assert "на язык ответа не влияет" in SYSTEM_PROMPT
    assert "даже если" in SYSTEM_PROMPT and "другом языке" in SYSTEM_PROMPT


def test_prompt_has_translate_or_adapt_exception() -> None:
    """translate_or_adapt is the documented exception to language-mirroring."""
    assert "Исключение" in SYSTEM_PROMPT
    assert "перевод" in SYSTEM_PROMPT  # «команды перевода/адаптации»


# --- 2. Placeholder phrased relative to the answer language -----------------


def test_placeholder_is_relative_to_answer_language_not_unconditional() -> None:
    """The owner/due placeholder must be tied to the answer's language.

    Both the RU and EN variants must be present, introduced by a phrase that
    binds them to the answer language — i.e. NOT an unconditional `не указано`.
    """
    assert "на языке твоего ответа" in SYSTEM_PROMPT
    assert "не указано" in SYSTEM_PROMPT  # RU variant (as an example)
    assert "not specified" in SYSTEM_PROMPT  # EN variant (as an example)


def test_placeholder_rule_mentions_both_language_examples_together() -> None:
    """RU/EN examples must appear inside the answer-language-relative clause."""
    anchor = "на языке твоего ответа"
    idx = SYSTEM_PROMPT.find(anchor)
    assert idx != -1
    tail = SYSTEM_PROMPT[idx:]
    # The concrete examples follow the answer-language anchor (parenthetical).
    assert "не указано" in tail
    assert "not specified" in tail


# --- 3. Pre-existing prompt rules preserved --------------------------------


def test_prompt_preserves_grounding_rule() -> None:
    """Grounding: do not invent facts outside the provided text."""
    assert "Не выдумывай факты" in SYSTEM_PROMPT
    assert "Если ответа нет" in SYSTEM_PROMPT  # honesty fallback


def test_prompt_preserves_transcription_binding_rule() -> None:
    """Binding: stay tied to the source transcription, no generic advice."""
    assert "транскрибации" in SYSTEM_PROMPT
    assert "привязку к исходной транскрибации" in SYSTEM_PROMPT
    assert "общие советы" in SYSTEM_PROMPT


def test_prompt_preserves_role_and_capabilities() -> None:
    """Role intro and the assistant's documented capabilities are intact."""
    assert "AI-ассистент" in SYSTEM_PROMPT
    assert "summary" in SYSTEM_PROMPT
    assert "action items" in SYSTEM_PROMPT


# --- 4. structured_blocks independence from placeholder language ------------


def test_structured_blocks_built_from_null_fields_english_markdown() -> None:
    """English markdown + JSON nulls -> blocks parse, owner/due are None.

    Reproduces the language-mirroring scenario: the model answered in English
    (so any placeholder text would be `not specified`), but the machine block
    uses JSON null. Extraction must rely on null, not on placeholder wording.
    """
    content = (
        "Here are the action items:\n\n"
        "- Ship the report (owner: not specified, due: not specified)\n\n"
        "```json\n"
        '[{"type": "task", "text": "Ship the report", '
        '"owner": null, "due": null, "done": false}]\n'
        "```"
    )
    blocks = extract_structured_blocks(content, QuickCommand.EXTRACT_TASKS)
    assert blocks == [
        {
            "type": "task",
            "text": "Ship the report",
            "owner": None,
            "due": None,
            "done": False,
        }
    ]


def test_structured_blocks_ignore_placeholder_text_in_any_language() -> None:
    """Placeholder words in prose must never leak into parsed block fields."""
    # Russian prose placeholder, but JSON nulls -> still None, no crash.
    content_ru = (
        "Задачи (владелец: не указано, срок: не указано):\n"
        "```json\n"
        '[{"type": "task", "text": "Отправить отчёт", "owner": null, "due": null}]\n'
        "```"
    )
    blocks_ru = extract_structured_blocks(content_ru, QuickCommand.CHECKLIST)
    assert blocks_ru is not None and len(blocks_ru) == 1
    assert blocks_ru[0]["owner"] is None
    assert blocks_ru[0]["due"] is None
    # The literal placeholder string must not have been copied into a field.
    assert "не указано" not in (blocks_ru[0]["text"])


def test_structured_blocks_parse_does_not_depend_on_prose_language() -> None:
    """Same JSON, different surrounding prose language -> identical blocks."""
    json_block = (
        "```json\n"
        '[{"type": "task", "text": "T", "owner": null, "due": null, "done": false}]\n'
        "```"
    )
    en = "Action items below.\n" + json_block
    ru = "Список задач ниже.\n" + json_block
    blocks_en = extract_structured_blocks(en, QuickCommand.EXTRACT_TASKS)
    blocks_ru = extract_structured_blocks(ru, QuickCommand.EXTRACT_TASKS)
    assert blocks_en == blocks_ru
    assert blocks_en == [
        {"type": "task", "text": "T", "owner": None, "due": None, "done": False}
    ]
