"""add journal_entries table

Revision ID: 0005_journal_entries
Revises: 0004_insight_evaluations
Create Date: 2026-08-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_journal_entries"
down_revision: Union[str, None] = "0004_insight_evaluations"
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None

_TICKER_MAX_LENGTH = 15
_DIRECTION_MAX_LENGTH = 10
_RESULT_STATUS_MAX_LENGTH = 20


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("ticker", sa.String(length=_TICKER_MAX_LENGTH), nullable=False),
        sa.Column("direction", sa.String(length=_DIRECTION_MAX_LENGTH), nullable=False),
        sa.Column("result_status", sa.String(length=_RESULT_STATUS_MAX_LENGTH), nullable=False),
        sa.Column("result_note", sa.Text(), nullable=True),
        sa.Column(
            "insight_id",
            sa.BigInteger(),
            sa.ForeignKey("insights.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_journal_entries_created_at", "journal_entries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_journal_entries_created_at", table_name="journal_entries")
    op.drop_table("journal_entries")
