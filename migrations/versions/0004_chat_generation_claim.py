"""Track active answer generation per chat.

Revision ID: 0004_chat_generation_claim
Revises: 0003_chat_history
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_chat_generation_claim"
down_revision: str | Sequence[str] | None = "0003_chat_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("generation_token", sa.String(length=36)))
    op.add_column("chats", sa.Column("generation_started_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("chats", "generation_started_at")
    op.drop_column("chats", "generation_token")
