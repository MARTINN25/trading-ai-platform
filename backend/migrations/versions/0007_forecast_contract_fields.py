"""add forecast contract fields to insights

Revision ID: 0007_forecast_contract_fields
Revises: 0006_news_intelligence_items
Create Date: 2026-08-12

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_forecast_contract_fields"
down_revision: Union[str, None] = "0006_news_intelligence_items"
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None

_HORIZON_MAX_LENGTH = 10
_FORECAST_STATE_MAX_LENGTH = 20
_DIRECTIONAL_VIEW_MAX_LENGTH = 20


def upgrade() -> None:
    # Every column below is nullable — a deliberate, additive-only
    # change (task scope §16, ADR-0004 §20: `insights` is append-only,
    # existing rows are never rewritten/backfilled). A row saved before
    # this migration simply has every one of these columns `NULL`,
    # which `insights.repository._to_domain` reads back as `None`/`()`
    # — no data loss, no forced re-migration of historical rows.
    op.add_column(
        "insights", sa.Column("horizon", sa.String(length=_HORIZON_MAX_LENGTH), nullable=True)
    )
    op.add_column(
        "insights",
        sa.Column("forecast_state", sa.String(length=_FORECAST_STATE_MAX_LENGTH), nullable=True),
    )
    op.add_column(
        "insights",
        sa.Column(
            "directional_view", sa.String(length=_DIRECTIONAL_VIEW_MAX_LENGTH), nullable=True
        ),
    )
    op.add_column("insights", sa.Column("concise_verdict", sa.Text(), nullable=True))
    op.add_column("insights", sa.Column("base_case", sa.Text(), nullable=True))
    op.add_column("insights", sa.Column("bullish_case", sa.Text(), nullable=True))
    op.add_column("insights", sa.Column("bearish_case", sa.Text(), nullable=True))
    op.add_column(
        "insights", sa.Column("catalysts", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "insights",
        sa.Column("invalidation_conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "insights", sa.Column("what_to_watch_next", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "insights", sa.Column("check_after", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("insights", sa.Column("uncertainty", sa.Text(), nullable=True))
    op.add_column(
        "insights",
        sa.Column("context_categories_used", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("insights", "context_categories_used")
    op.drop_column("insights", "uncertainty")
    op.drop_column("insights", "check_after")
    op.drop_column("insights", "what_to_watch_next")
    op.drop_column("insights", "invalidation_conditions")
    op.drop_column("insights", "catalysts")
    op.drop_column("insights", "bearish_case")
    op.drop_column("insights", "bullish_case")
    op.drop_column("insights", "base_case")
    op.drop_column("insights", "concise_verdict")
    op.drop_column("insights", "directional_view")
    op.drop_column("insights", "forecast_state")
    op.drop_column("insights", "horizon")
