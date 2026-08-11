"""Concrete journal repository — no generic repository abstraction.

Owns no transaction boundary: whoever obtained the `AsyncSession`
(`trading_ai.infrastructure.database.session.session_scope`) decides
when to commit or roll back — this repository never calls `commit()`
(same rule as `insights.repository.InsightRepository`/
`evaluations.repository.EvaluationRepository`).

Only `add`/`list_recent`/`get_by_id`/`update` exist — no `delete`
(Product Owner: editable, no delete, task scope §15).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_ai.journal.domain import (
    JournalEntry,
    JournalEntryEdit,
    MAX_JOURNAL_ITEMS,
    NewJournalEntry,
    TradeDirection,
    TradeResultStatus,
)
from trading_ai.journal.models import JournalEntryModel


def _to_domain(model: JournalEntryModel) -> JournalEntry:
    return JournalEntry(
        id=model.id,
        ticker=model.ticker,
        direction=TradeDirection(model.direction),
        result_status=TradeResultStatus(model.result_status),
        result_note=model.result_note,
        insight_id=model.insight_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class JournalRepository:
    """Concrete repository for `journal_entries` — no generic base class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entry: NewJournalEntry) -> JournalEntry:
        model = JournalEntryModel(
            ticker=entry.ticker,
            direction=entry.direction.value,
            result_status=entry.result_status.value,
            result_note=entry.result_note,
            insight_id=entry.insight_id,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_domain(model)

    async def list_recent(self, limit: int = MAX_JOURNAL_ITEMS) -> list[JournalEntry]:
        """Newest-first, bounded (task scope §11/§13)."""
        result = await self._session.execute(
            select(JournalEntryModel)
            .order_by(desc(JournalEntryModel.created_at), desc(JournalEntryModel.id))
            .limit(limit)
        )
        return [_to_domain(model) for model in result.scalars()]

    async def get_by_id(self, entry_id: int) -> JournalEntry | None:
        result = await self._session.execute(
            select(JournalEntryModel).where(JournalEntryModel.id == entry_id)
        )
        model = result.scalar_one_or_none()
        return _to_domain(model) if model is not None else None

    async def update(
        self, entry_id: int, edit: JournalEntryEdit, updated_at: datetime
    ) -> JournalEntry | None:
        result = await self._session.execute(
            select(JournalEntryModel).where(JournalEntryModel.id == entry_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.ticker = edit.ticker
        model.direction = edit.direction.value
        model.result_status = edit.result_status.value
        model.result_note = edit.result_note
        model.insight_id = edit.insight_id
        model.updated_at = updated_at
        await self._session.flush()
        return _to_domain(model)
