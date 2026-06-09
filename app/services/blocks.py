"""Extraction of structured_blocks from the model's markdown answer (TD-006).

Strategy: locate a fenced ```json block in the answer, parse it, and validate
each item against the block schemas for the given command. On any failure
(missing block, invalid JSON, schema mismatch) fall back to an empty list — the
answer is still returned with HTTP 201 (02-api-contracts / 03-architecture).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.core.logging import get_logger
from app.core.prompts import QuickCommand, is_list_command
from app.schemas.blocks import (
    DecisionBlock,
    QuestionBlock,
    RiskBlock,
    StructuredBlock,
    TaskBlock,
)

logger = get_logger(__name__)

_FENCED_JSON_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL | re.IGNORECASE)

# Allowed block types per command (02-api-contracts.md).
_ALLOWED_TYPES: dict[QuickCommand, set[str]] = {
    QuickCommand.EXTRACT_TASKS: {"task"},
    QuickCommand.CHECKLIST: {"task"},
    QuickCommand.DECISIONS: {"decision"},
    QuickCommand.RISKS_QUESTIONS: {"risk", "question"},
}

_BLOCK_ADAPTER: TypeAdapter[StructuredBlock] = TypeAdapter(StructuredBlock)


def extract_structured_blocks(
    content: str,
    command: QuickCommand | None,
) -> list[dict[str, Any]] | None:
    """Return validated structured_blocks for list commands, else None.

    Non-list commands -> None. List commands -> a (possibly empty) list of
    validated block dicts. Invalid/missing model JSON -> [] (TD-006).
    """
    if not is_list_command(command):
        return None
    assert command is not None  # narrowed by is_list_command

    raw_items = _parse_fenced_json(content)
    if raw_items is None:
        logger.info("structured_blocks: no valid JSON block found, falling back to []")
        return []

    allowed = _ALLOWED_TYPES[command]
    blocks: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if item.get("type") not in allowed:
            continue
        try:
            validated = _BLOCK_ADAPTER.validate_python(item)
        except ValidationError:
            continue
        blocks.append(_dump(validated))
    return blocks


def _parse_fenced_json(content: str) -> list[Any] | None:
    """Find and parse the first fenced ```json array in the content."""
    match = _FENCED_JSON_RE.search(content)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return parsed
    return None


def _dump(block: TaskBlock | DecisionBlock | RiskBlock | QuestionBlock) -> dict[str, Any]:
    """Serialize a validated block model to a plain dict."""
    return block.model_dump()
