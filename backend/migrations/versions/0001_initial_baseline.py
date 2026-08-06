"""initial baseline (no business tables)

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-08-05

"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_initial_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], str, None] = None
depends_on: Union[Sequence[str], str, None] = None


def upgrade() -> None:
    """Intentionally empty.

    This bootstrap does not define any business table (trading
    positions, insights, users, news, market data, LLM data, or
    otherwise) — see the task scope. This revision only establishes a
    working baseline for the migration chain.
    """


def downgrade() -> None:
    """Intentionally empty — nothing was created to reverse."""
