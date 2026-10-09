"""Add chat history and citation snapshots.

Revision ID: 0003_chat_history
Revises: 0002_profiles
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_chat_history"
down_revision: str | Sequence[str] | None = "0002_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_chats_status"),
    )
    op.create_index(
        "ix_chats_owner_updated", "chats", ["user_id", "updated_at", "id"]
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("chat_id", sa.Integer(), sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker", sa.String(length=9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("speaker IN ('user', 'assistant')", name="ck_chat_messages_speaker"),
    )
    op.create_index("ix_chat_messages_chat_id", "chat_messages", ["chat_id", "id"])
    op.create_table(
        "chat_citations",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("citation_number", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("index_version", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("source_uri", sa.String(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("excerpt", sa.Text()),
        sa.CheckConstraint("citation_number > 0", name="ck_chat_citations_number"),
        sa.UniqueConstraint("message_id", "citation_number", name="uq_chat_citation_number"),
    )


def downgrade() -> None:
    op.drop_table("chat_citations")
    op.drop_index("ix_chat_messages_chat_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chats_owner_updated", table_name="chats")
    op.drop_table("chats")
