"""add news_intelligence_items table

Revision ID: 0006_news_intelligence_items
Revises: 0005_journal_entries
Create Date: 2026-08-12

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_news_intelligence_items"
down_revision: Union[str, None] = "0005_journal_entries"
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None

_TICKER_MAX_LENGTH = 15
_NEWS_PROVIDER_MAX_LENGTH = 50
_PROVIDER_NEWS_ID_MAX_LENGTH = 100
_SOURCE_MAX_LENGTH = 200
_URL_MAX_LENGTH = 2000
_RELEVANCE_MAX_LENGTH = 10
_RELATIONSHIP_MAX_LENGTH = 10
_LLM_PROVIDER_MAX_LENGTH = 50
_LLM_MODEL_MAX_LENGTH = 100
_LLM_VERSION_MAX_LENGTH = 50


def upgrade() -> None:
    op.create_table(
        "news_intelligence_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("ticker", sa.String(length=_TICKER_MAX_LENGTH), nullable=False),
        sa.Column("news_provider", sa.String(length=_NEWS_PROVIDER_MAX_LENGTH), nullable=False),
        sa.Column(
            "provider_news_id", sa.String(length=_PROVIDER_NEWS_ID_MAX_LENGTH), nullable=False
        ),
        sa.Column("headline_original", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=_SOURCE_MAX_LENGTH), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("url", sa.String(length=_URL_MAX_LENGTH), nullable=False),
        sa.Column("enriched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary_ru", sa.Text(), nullable=True),
        sa.Column("why_it_matters", sa.Text(), nullable=True),
        sa.Column("relevance", sa.String(length=_RELEVANCE_MAX_LENGTH), nullable=True),
        sa.Column("relationship", sa.String(length=_RELATIONSHIP_MAX_LENGTH), nullable=True),
        sa.Column("impact_hypothesis", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(length=_LLM_PROVIDER_MAX_LENGTH), nullable=True),
        sa.Column("llm_model", sa.String(length=_LLM_MODEL_MAX_LENGTH), nullable=True),
        sa.Column("llm_prompt_version", sa.String(length=_LLM_VERSION_MAX_LENGTH), nullable=True),
        sa.Column("llm_schema_version", sa.String(length=_LLM_VERSION_MAX_LENGTH), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "ticker",
            "news_provider",
            "provider_news_id",
            name="uq_news_intelligence_ticker_provider_item",
        ),
    )
    op.create_index(
        "ix_news_intelligence_ticker_published_at",
        "news_intelligence_items",
        ["ticker", "published_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_news_intelligence_ticker_published_at", table_name="news_intelligence_items"
    )
    op.drop_table("news_intelligence_items")
