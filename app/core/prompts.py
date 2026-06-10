"""Prompts: verbatim system prompt and the 10 quick-command instructions.

The system prompt text is fixed (03-architecture.md); changing it requires a new
ADR. Commands marked with structured blocks instruct the model to also emit a
machine-readable JSON block (fenced ```json) that the service parses into
structured_blocks (TD-006).
"""

from __future__ import annotations

from enum import Enum


class QuickCommand(str, Enum):
    """Quick command enum (10 values) — matches the DB CHECK and API contract."""

    EXTRACT_TASKS = "extract_tasks"
    MAKE_SUMMARY = "make_summary"
    MAIN_IDEA = "main_idea"
    WEEKLY_PLAN = "weekly_plan"
    FOLLOW_UP_MESSAGE = "follow_up_message"
    DECISIONS = "decisions"
    RISKS_QUESTIONS = "risks_questions"
    CHECKLIST = "checklist"
    CONTENT_NOTE = "content_note"
    TRANSLATE_OR_ADAPT = "translate_or_adapt"


# Commands that must return structured_blocks (02-api-contracts.md).
LIST_COMMANDS: frozenset[QuickCommand] = frozenset(
    {
        QuickCommand.EXTRACT_TASKS,
        QuickCommand.CHECKLIST,
        QuickCommand.DECISIONS,
        QuickCommand.RISKS_QUESTIONS,
    }
)


# Verbatim system prompt — DO NOT change without a new ADR (03-architecture.md).
SYSTEM_PROMPT = (
    "Ты AI-ассистент внутри приложения для транскрибации. Работай только с "
    "контекстом текущей транскрибации, summary и выбранными пользователем "
    "фрагментами. Не выдумывай факты вне предоставленного текста. Если ответа нет "
    "в транскрибации, так и скажи и предложи, какой дополнительный контекст нужен.\n"
    "Отвечай на том же языке, на котором написано текущее сообщение пользователя. "
    "Язык транскрибации, summary и истории на язык ответа не влияет — даже если "
    "контекст на другом языке, отвечай на языке текущего вопроса. Исключение: для "
    "команды перевода/адаптации язык результата определяется самой командой (целевой "
    "язык из запроса пользователя).\n"
    "Твоя задача — помогать пользователю извлекать пользу из транскрибации: делать "
    "summary, выделять action items, решения, риски, открытые вопросы, планы, "
    "follow-up сообщения, чек-листы и структурированные заметки.\n"
    "Отвечай кратко и структурно. Если пользователь просит список задач, возвращай "
    "пункты с понятным действием, владельцем и сроком, если они есть в тексте. Если "
    "владельца или срока нет, помечай это на языке твоего ответа (`не указано` для "
    "русского, `not specified` для английского и т. п.).\n"
    "Всегда сохраняй привязку к исходной транскрибации и не уходи в общие советы, "
    "если пользователь прямо не просит этого."
)


# JSON-block instructions appended for list commands so the service can parse
# structured_blocks (TD-006: heuristic fenced-JSON + Pydantic validation).
_TASK_JSON = (
    "В конце ответа добавь машиночитаемый блок в fenced-формате ```json с массивом "
    'объектов вида {"type": "task", "text": "...", "owner": null, "due": null, '
    '"done": false}. Если владелец или срок не указаны в тексте — используй null.'
)
_DECISION_JSON = (
    "В конце ответа добавь машиночитаемый блок в fenced-формате ```json с массивом "
    'объектов вида {"type": "decision", "text": "...", "rationale": null}. Если '
    "обоснование не указано — используй null."
)
_RISKS_JSON = (
    "В конце ответа добавь машиночитаемый блок в fenced-формате ```json с массивом "
    'объектов: для рисков {"type": "risk", "text": "...", "severity": null}, для '
    'открытых вопросов {"type": "question", "text": "..."}. Severity, если не указан '
    "в тексте — null."
)


COMMAND_PROMPTS: dict[QuickCommand, str] = {
    QuickCommand.EXTRACT_TASKS: (
        "Извлеки из транскрибации список action items. Для каждого укажи действие, "
        "владельца и срок, если они есть в тексте; иначе помечай `не указано`. " + _TASK_JSON
    ),
    QuickCommand.MAKE_SUMMARY: (
        "Сделай краткое структурное summary транскрибации, сохраняя ключевые факты."
    ),
    QuickCommand.MAIN_IDEA: (
        "Сформулируй главную мысль (основную идею) транскрибации одним-двумя абзацами."
    ),
    QuickCommand.WEEKLY_PLAN: (
        "Составь план на неделю на основе содержания транскрибации, сгруппировав "
        "задачи по дням или приоритетам."
    ),
    QuickCommand.FOLLOW_UP_MESSAGE: (
        "Сгенерируй короткое follow-up сообщение по итогам транскрибации, пригодное "
        "для отправки участникам."
    ),
    QuickCommand.DECISIONS: (
        "Выдели принятые решения и их обоснования из транскрибации. " + _DECISION_JSON
    ),
    QuickCommand.RISKS_QUESTIONS: (
        "Выдели риски и открытые вопросы из транскрибации. " + _RISKS_JSON
    ),
    QuickCommand.CHECKLIST: (
        "Сформируй чек-лист конкретных действий на основе транскрибации. " + _TASK_JSON
    ),
    QuickCommand.CONTENT_NOTE: (
        "Составь структурированную заметку по содержанию транскрибации с заголовками " "и тезисами."
    ),
    QuickCommand.TRANSLATE_OR_ADAPT: (
        "Переведи или адаптируй текст. Целевой язык возьми из сообщения пользователя; "
        "если он не указан — попроси уточнить целевой язык."
    ),
}


def command_instruction(command: QuickCommand, *, language: str | None = None) -> str:
    """Return the command prompt instruction for a quick command.

    For translate_or_adapt, `language` (the transcription language) is added as a
    target-language hint when the user has not specified one (03-architecture.md:53,
    "целевой язык — из message/language").
    """
    instruction = COMMAND_PROMPTS[command]
    if command is QuickCommand.TRANSLATE_OR_ADAPT and language:
        instruction = (
            f"{instruction} Если целевой язык не указан в сообщении пользователя, "
            f"используй язык исходной транскрибации как ориентир: {language}."
        )
    return instruction


def is_list_command(command: QuickCommand | None) -> bool:
    """Whether the command should produce structured_blocks."""
    return command is not None and command in LIST_COMMANDS
