"""Context assembly with summary-first strategy and tiktoken budgeting (ADR-004).

Priority (highest to lowest):
    system_prompt > current message > selected_text > summary > full_text > history (new->old)

Algorithm (03-architecture.md / ADR-004):
1. Assemble full context, estimate tokens.
2. <= budget                -> context_mode "full".
3. Else drop full_text      -> "summary_first" (truncated=True). If no summary,
   truncate full_text (instead of dropping) to fit.
4. Still over budget        -> truncate history (oldest first), then summary/
   selected_text -> "truncated".
5. Minimal context still over budget -> ContextTooLong (413).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.errors import ContextTooLongError
from app.core.prompts import SYSTEM_PROMPT, QuickCommand, command_instruction
from app.core.tokens import count_messages_tokens, count_tokens

TRUNCATION_NOTE = "Ответ построен по сокращённому контексту (summary вместо полного текста)."

_FULL_TEXT_HEADER = "Полный текст транскрибации:\n"
_SUMMARY_HEADER = "Summary транскрибации:\n"
_SELECTED_HEADER = "Выбранный пользователем фрагмент:\n"


@dataclass(frozen=True)
class HistoryMessage:
    """A prior thread message used for context."""

    role: str
    content: str


@dataclass
class ContextInputs:
    """All raw inputs needed to assemble a request context."""

    model: str
    token_budget: int
    message: str
    full_text: str
    summary: str | None = None
    selected_text: str | None = None
    quick_command: QuickCommand | None = None
    language: str | None = None
    history: list[HistoryMessage] = field(default_factory=list)


@dataclass
class ContextResult:
    """Assembled context for the LLM plus mode metadata."""

    messages: list[dict[str, str]]
    context_mode: str  # "full" | "summary_first" | "truncated"
    context_truncated: bool
    token_count: int


def _user_message_text(inputs: ContextInputs) -> str:
    """Compose the trailing user turn: command instruction + user message."""
    if inputs.quick_command is not None:
        instruction = command_instruction(inputs.quick_command, language=inputs.language)
        if inputs.message.strip():
            return f"{instruction}\n\nУточнение пользователя: {inputs.message}"
        return instruction
    return inputs.message


def _build_messages(
    inputs: ContextInputs,
    *,
    full_text: str | None,
    summary: str | None,
    selected_text: str | None,
    history: list[HistoryMessage],
    truncated: bool,
) -> list[dict[str, str]]:
    """Assemble the chat messages array in priority order."""
    system_content = SYSTEM_PROMPT
    if truncated:
        system_content = f"{SYSTEM_PROMPT}\n\n{TRUNCATION_NOTE}"

    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    context_parts: list[str] = []
    if summary:
        context_parts.append(f"{_SUMMARY_HEADER}{summary}")
    if selected_text:
        context_parts.append(f"{_SELECTED_HEADER}{selected_text}")
    if full_text:
        context_parts.append(f"{_FULL_TEXT_HEADER}{full_text}")
    if context_parts:
        messages.append({"role": "system", "content": "\n\n".join(context_parts)})

    for item in history:
        messages.append({"role": item.role, "content": item.content})

    messages.append({"role": "user", "content": _user_message_text(inputs)})
    return messages


def _count(messages: list[dict[str, str]], model: str) -> int:
    return count_messages_tokens(messages, model)


def build_context(inputs: ContextInputs) -> ContextResult:
    """Build the context applying the summary-first strategy.

    Raises ContextTooLongError (413) when even the minimal context exceeds budget.
    """
    budget = inputs.token_budget
    model = inputs.model

    # Step 1-2: full context.
    full_messages = _build_messages(
        inputs,
        full_text=inputs.full_text,
        summary=inputs.summary,
        selected_text=inputs.selected_text,
        history=inputs.history,
        truncated=False,
    )
    tokens = _count(full_messages, model)
    if tokens <= budget:
        return ContextResult(
            messages=full_messages,
            context_mode="full",
            context_truncated=False,
            token_count=tokens,
        )

    # Step 3: summary-first (drop full_text). If no summary, truncate full_text.
    if inputs.summary:
        sf_full_text: str | None = None
    else:
        sf_full_text = _truncate_full_text_to_fit(inputs, budget)

    sf_messages = _build_messages(
        inputs,
        full_text=sf_full_text,
        summary=inputs.summary,
        selected_text=inputs.selected_text,
        history=inputs.history,
        truncated=True,
    )
    tokens = _count(sf_messages, model)
    if tokens <= budget:
        return ContextResult(
            messages=sf_messages,
            context_mode="summary_first",
            context_truncated=True,
            token_count=tokens,
        )

    # Step 4: truncate history (oldest first), then summary/selected_text.
    history = list(inputs.history)
    while history:
        history = history[1:]  # drop oldest
        candidate = _build_messages(
            inputs,
            full_text=sf_full_text,
            summary=inputs.summary,
            selected_text=inputs.selected_text,
            history=history,
            truncated=True,
        )
        tokens = _count(candidate, model)
        if tokens <= budget:
            return ContextResult(
                messages=candidate,
                context_mode="truncated",
                context_truncated=True,
                token_count=tokens,
            )

    # Drop full_text entirely (if any remained from truncation).
    candidate = _build_messages(
        inputs,
        full_text=None,
        summary=inputs.summary,
        selected_text=inputs.selected_text,
        history=[],
        truncated=True,
    )
    tokens = _count(candidate, model)
    if tokens <= budget:
        return ContextResult(
            messages=candidate,
            context_mode="truncated",
            context_truncated=True,
            token_count=tokens,
        )

    # ADR-004 step 4 / 03-architecture:67 — usечение summary/selected_text.
    # Prefer truncating each part to fit before discarding it entirely. Order
    # follows context priority (selected_text > summary): truncate selected_text
    # first (keep summary), then truncate summary (selected_text already gone).
    summary = inputs.summary
    selected_text = inputs.selected_text

    # 4a: truncate selected_text to fit (summary kept intact).
    if selected_text:
        truncated_selected = _truncate_part_to_fit(
            inputs,
            budget,
            summary=summary,
            selected_text=selected_text,
            target="selected_text",
        )
        candidate = _build_messages(
            inputs,
            full_text=None,
            summary=summary,
            selected_text=truncated_selected,
            history=[],
            truncated=True,
        )
        tokens = _count(candidate, model)
        if truncated_selected is not None and tokens <= budget:
            return ContextResult(
                messages=candidate,
                context_mode="truncated",
                context_truncated=True,
                token_count=tokens,
            )
        # selected_text cannot fit even truncated -> drop it for the next steps.
        selected_text = None

    # 4b: truncate summary to fit (selected_text dropped).
    if summary:
        truncated_summary = _truncate_part_to_fit(
            inputs,
            budget,
            summary=summary,
            selected_text=None,
            target="summary",
        )
        candidate = _build_messages(
            inputs,
            full_text=None,
            summary=truncated_summary,
            selected_text=None,
            history=[],
            truncated=True,
        )
        tokens = _count(candidate, model)
        if truncated_summary is not None and tokens <= budget:
            return ContextResult(
                messages=candidate,
                context_mode="truncated",
                context_truncated=True,
                token_count=tokens,
            )

    # 4c: drop selected_text, then summary entirely (last resort before 413).
    for drop_selected, drop_summary in ((True, False), (True, True)):
        candidate = _build_messages(
            inputs,
            full_text=None,
            summary=None if drop_summary else inputs.summary,
            selected_text=None if drop_selected else inputs.selected_text,
            history=[],
            truncated=True,
        )
        tokens = _count(candidate, model)
        if tokens <= budget:
            return ContextResult(
                messages=candidate,
                context_mode="truncated",
                context_truncated=True,
                token_count=tokens,
            )

    # Step 5: minimal context (system + message) still over budget.
    raise ContextTooLongError("Context exceeds the token budget after truncation.")


def _truncate_full_text_to_fit(inputs: ContextInputs, budget: int) -> str | None:
    """Truncate full_text so the assembled context fits the budget.

    Used only when there is no summary (ADR-004 step 3). Returns the truncated
    text, or None if even an empty full_text overflows (handled downstream).
    """
    model = inputs.model

    # Tokens consumed by everything except full_text.
    base_messages = _build_messages(
        inputs,
        full_text=None,
        summary=inputs.summary,
        selected_text=inputs.selected_text,
        history=inputs.history,
        truncated=True,
    )
    base_tokens = _count(base_messages, model)
    header_tokens = count_tokens(_FULL_TEXT_HEADER, model)
    # Reserve a small margin for join separators / framing so the assembled
    # context reliably fits at the summary-first step (ADR-004 step 3).
    safety_margin = 8
    available = budget - base_tokens - header_tokens - safety_margin
    if available <= 0:
        return None

    # Truncate by token slice on the full_text encoding.
    from app.core.tokens import _get_encoding  # local import to avoid cycle exposure

    encoding = _get_encoding(model)
    token_ids = encoding.encode(inputs.full_text)
    if len(token_ids) <= available:
        return inputs.full_text
    return encoding.decode(token_ids[:available])


def _truncate_part_to_fit(
    inputs: ContextInputs,
    budget: int,
    *,
    summary: str | None,
    selected_text: str | None,
    target: str,
) -> str | None:
    """Truncate the target context part (summary|selected_text) so context fits.

    full_text and history are already dropped at this stage (ADR-004 step 4).
    Returns the truncated text, or None if even an empty target overflows.
    """
    model = inputs.model
    if target == "summary":
        original = summary
        header = _SUMMARY_HEADER
        base_summary: str | None = None
        base_selected = selected_text
    else:
        original = selected_text
        header = _SELECTED_HEADER
        base_summary = summary
        base_selected = None
    if not original:
        return None

    # Tokens consumed by everything except the target part.
    base_messages = _build_messages(
        inputs,
        full_text=None,
        summary=base_summary,
        selected_text=base_selected,
        history=[],
        truncated=True,
    )
    base_tokens = _count(base_messages, model)
    header_tokens = count_tokens(header, model)
    # Reserve a small margin for join separators / framing (matches
    # _truncate_full_text_to_fit, ADR-004 step 4).
    safety_margin = 8
    available = budget - base_tokens - header_tokens - safety_margin
    if available <= 0:
        return None

    from app.core.tokens import _get_encoding  # local import to avoid cycle exposure

    encoding = _get_encoding(model)
    token_ids = encoding.encode(original)
    if len(token_ids) <= available:
        return original
    return encoding.decode(token_ids[:available])
