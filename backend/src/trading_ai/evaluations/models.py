"""SQLAlchemy persistence model for `insight_evaluations`.

Kept separate from `trading_ai.evaluations.domain.InsightEvaluation`,
same split as `insights.models`/`insights.domain` (ADR-0002 §18.2).

`insight_id` is a foreign key to `insights.id` with a `UNIQUE`
constraint — enforced at the database level, not only in application
code (ADR-0004: "ограничения не запрещаются ради удобства"), matching
this module's "one evaluation record per insight" design decision
(`domain.py`).

No `ON DELETE CASCADE`/`SET NULL` — deliberately the database default
(`NO ACTION`). Insight deletion does not exist anywhere in this
codebase yet (task scope §6: "не вводить delete architecture без
необходимости"), so there is nothing concrete to cascade into; adding
a cascade clause now would be guessing at a future feature's semantics.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from trading_ai.infrastructure.database.base import Base

_RATING_MAX_LENGTH = 30


class InsightEvaluationModel(Base):
    __tablename__ = "insight_evaluations"
    __table_args__ = (UniqueConstraint("insight_id", name="uq_insight_evaluations_insight_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    insight_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("insights.id"), nullable=False
    )

    rating: Mapped[str | None] = mapped_column(String(_RATING_MAX_LENGTH), nullable=True)
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
