"""add insight_evaluations table

Revision ID: 0004_insight_evaluations
Revises: 0003_insights
Create Date: 2026-08-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_insight_evaluations"
down_revision: Union[str, None] = "0003_insights"
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None

_RATING_MAX_LENGTH = 30


def upgrade() -> None:
    op.create_table(
        "insight_evaluations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "insight_id",
            sa.BigInteger(),
            sa.ForeignKey("insights.id"),
            nullable=False,
        ),
        sa.Column("rating", sa.String(length=_RATING_MAX_LENGTH), nullable=True),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome_note", sa.Text(), nullable=True),
        sa.Column("outcome_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("insight_id", name="uq_insight_evaluations_insight_id"),
    )


def downgrade() -> None:
    op.drop_table("insight_evaluations")
