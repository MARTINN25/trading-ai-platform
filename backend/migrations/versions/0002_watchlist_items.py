"""add watchlist_items table

Revision ID: 0002_watchlist_items
Revises: 0001_initial_baseline
Create Date: 2026-08-07

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_watchlist_items"
down_revision: Union[str, None] = "0001_initial_baseline"
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None

_TICKER_MAX_LENGTH = 15


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("ticker", sa.String(length=_TICKER_MAX_LENGTH), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("ticker", name="uq_watchlist_items_ticker"),
    )


def downgrade() -> None:
    op.drop_table("watchlist_items")
