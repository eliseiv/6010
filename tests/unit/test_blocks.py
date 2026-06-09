"""Unit tests for structured_blocks extraction (TD-006)."""

from __future__ import annotations

from app.core.prompts import QuickCommand
from app.services.blocks import extract_structured_blocks


def test_non_list_command_returns_none() -> None:
    assert extract_structured_blocks("anything", QuickCommand.MAKE_SUMMARY) is None
    assert extract_structured_blocks("anything", None) is None


def test_extract_tasks_parses_task_blocks() -> None:
    content = (
        'Задачи:\n```json\n[{"type": "task", "text": "A", "owner": "Аня", '
        '"due": "пн", "done": false}]\n```'
    )
    blocks = extract_structured_blocks(content, QuickCommand.EXTRACT_TASKS)
    assert blocks == [
        {"type": "task", "text": "A", "owner": "Аня", "due": "пн", "done": False}
    ]


def test_checklist_uses_task_type() -> None:
    content = '```json\n[{"type": "task", "text": "X"}]\n```'
    blocks = extract_structured_blocks(content, QuickCommand.CHECKLIST)
    assert blocks is not None and blocks[0]["type"] == "task"
    # Missing optional fields default per schema.
    assert blocks[0]["done"] is False
    assert blocks[0]["owner"] is None


def test_decisions_parses_decision_blocks() -> None:
    content = '```json\n[{"type": "decision", "text": "D", "rationale": "R"}]\n```'
    blocks = extract_structured_blocks(content, QuickCommand.DECISIONS)
    assert blocks == [{"type": "decision", "text": "D", "rationale": "R"}]


def test_risks_questions_parses_mixed_blocks() -> None:
    content = (
        '```json\n[{"type": "risk", "text": "R", "severity": "high"}, '
        '{"type": "question", "text": "Q"}]\n```'
    )
    blocks = extract_structured_blocks(content, QuickCommand.RISKS_QUESTIONS)
    types = [b["type"] for b in blocks]
    assert types == ["risk", "question"]


def test_invalid_json_falls_back_to_empty_list() -> None:
    content = "Ответ\n```json\n{это не валидный json}\n```"
    assert extract_structured_blocks(content, QuickCommand.EXTRACT_TASKS) == []


def test_no_json_block_falls_back_to_empty_list() -> None:
    assert extract_structured_blocks("просто текст", QuickCommand.EXTRACT_TASKS) == []


def test_wrong_block_type_filtered_out() -> None:
    """decision item in an extract_tasks answer is dropped (allowed types only)."""
    content = '```json\n[{"type": "decision", "text": "D"}, {"type": "task", "text": "T"}]\n```'
    blocks = extract_structured_blocks(content, QuickCommand.EXTRACT_TASKS)
    assert blocks == [{"type": "task", "text": "T", "owner": None, "due": None, "done": False}]


def test_non_dict_items_skipped() -> None:
    content = '```json\n["string", 123, {"type": "task", "text": "ok"}]\n```'
    blocks = extract_structured_blocks(content, QuickCommand.EXTRACT_TASKS)
    assert len(blocks) == 1
    assert blocks[0]["text"] == "ok"


def test_json_object_not_array_falls_back_to_empty() -> None:
    content = '```json\n{"type": "task", "text": "X"}\n```'
    assert extract_structured_blocks(content, QuickCommand.EXTRACT_TASKS) == []
