"""ChatMessage ORM model (04-data-model.md)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_QUICK_COMMANDS_SQL = (
    "'extract_tasks','make_summary','main_idea','weekly_plan',"
    "'follow_up_message','decisions','risks_questions','checklist',"
    "'content_note','translate_or_adapt'"
)


class ChatMessage(Base):
    """A single chat message in a transcription's thread."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="ck_chat_messages_role"),
        CheckConstraint(
            f"quick_command_type IS NULL OR quick_command_type IN ({_QUICK_COMMANDS_SQL})",
            name="ck_chat_messages_quick_command_type",
        ),
        Index("ix_chat_messages_transcription_id", "transcription_id"),
        Index(
            "ix_chat_messages_thread_order",
            "transcription_id",
            "created_at",
            "id",
        ),
        Index("ix_chat_messages_summary_id", "summary_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    transcription_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("transcriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("summaries.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    selected_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quick_command_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_blocks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
