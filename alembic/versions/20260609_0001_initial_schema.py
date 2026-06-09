"""initial schema: transcriptions, summaries, chat_messages

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-09

Implements the canonical DDL from docs/modules/ai-chat/04-data-model.md.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_QUICK_COMMANDS = (
    "'extract_tasks','make_summary','main_idea','weekly_plan',"
    "'follow_up_message','decisions','risks_questions','checklist',"
    "'content_note','translate_or_adapt'"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "transcriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "summaries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("transcription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["transcription_id"],
            ["transcriptions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_summaries_transcription_id", "summaries", ["transcription_id"])

    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("transcription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=True),
        sa.Column("quick_command_type", sa.Text(), nullable=True),
        sa.Column("structured_blocks", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["transcription_id"],
            ["transcriptions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["summary_id"],
            ["summaries.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_chat_messages_role"),
        sa.CheckConstraint(
            f"quick_command_type IS NULL OR quick_command_type IN ({_QUICK_COMMANDS})",
            name="ck_chat_messages_quick_command_type",
        ),
    )
    op.create_index("ix_chat_messages_transcription_id", "chat_messages", ["transcription_id"])
    op.create_index(
        "ix_chat_messages_thread_order",
        "chat_messages",
        ["transcription_id", "created_at", "id"],
    )
    op.create_index("ix_chat_messages_summary_id", "chat_messages", ["summary_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_summary_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_thread_order", table_name="chat_messages")
    op.drop_index("ix_chat_messages_transcription_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_summaries_transcription_id", table_name="summaries")
    op.drop_table("summaries")
    op.drop_table("transcriptions")
