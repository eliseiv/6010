"""Structured block schemas (02-api-contracts.md).

These are the machine projection of list-command outputs. Validation/fallback
on invalid model JSON is governed by TD-006.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class TaskBlock(BaseModel):
    """extract_tasks / checklist item."""

    type: Literal["task"] = "task"
    text: str
    owner: str | None = None
    due: str | None = None
    done: bool = False


class DecisionBlock(BaseModel):
    """decisions item."""

    type: Literal["decision"] = "decision"
    text: str
    rationale: str | None = None


class RiskBlock(BaseModel):
    """risks_questions risk item."""

    type: Literal["risk"] = "risk"
    text: str
    severity: str | None = None


class QuestionBlock(BaseModel):
    """risks_questions open-question item."""

    type: Literal["question"] = "question"
    text: str


StructuredBlock = Annotated[
    TaskBlock | DecisionBlock | RiskBlock | QuestionBlock,
    Field(discriminator="type"),
]
