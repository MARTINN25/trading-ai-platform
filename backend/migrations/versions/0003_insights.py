"""add insights table

Revision ID: 0003_insights
Revises: 0002_watchlist_items
Create Date: 2026-08-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_insights"
down_revision: Union[str, None] = "0002_watchlist_items"
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None

_TICKER_MAX_LENGTH = 15
_PROVIDER_MAX_LENGTH = 50
_MODEL_MAX_LENGTH = 100
_VERSION_MAX_LENGTH = 50
_CONFIDENCE_MAX_LENGTH = 10


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("ticker", sa.String(length=_TICKER_MAX_LENGTH), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("price_context", sa.Text(), nullable=False),
        sa.Column("news_context", sa.Text(), nullable=False),
        sa.Column("key_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("insight_hypothesis", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=_CONFIDENCE_MAX_LENGTH), nullable=False),
        sa.Column("confidence_reason", sa.Text(), nullable=False),
        sa.Column("considerations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("key_drivers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data_freshness", sa.Text(), nullable=False),
        sa.Column("source_data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=_PROVIDER_MAX_LENGTH), nullable=False),
        sa.Column("model", sa.String(length=_MODEL_MAX_LENGTH), nullable=False),
        sa.Column("prompt_version", sa.String(length=_VERSION_MAX_LENGTH), nullable=False),
        sa.Column("schema_version", sa.String(length=_VERSION_MAX_LENGTH), nullable=False),
    )
    op.create_index(
        "ix_insights_ticker_created_at", "insights", ["ticker", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_insights_ticker_created_at", table_name="insights")
    op.drop_table("insights")
