"""Trade journal application use cases.

`CreateJournalEntry`/`UpdateJournalEntry` verify an optionally-supplied
`insight_id` actually exists via `_InsightLookup` (implemented by
`trading_ai.insights.repository.InsightRepository`, only its read-only
`get_by_id` — MODULE_BOUNDARIES.md §13: "insights — только для
ссылки"). Neither use case ever reads or writes insight *content* —
only existence is checked, so there is no path by which a caller could
smuggle in altered insight text/provenance through this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from trading_ai.insights.domain import InsightNotFoundError
from trading_ai.journal.domain import (
    JournalEntry,
    JournalEntryEdit,
    JournalEntryNotFoundError,
    NewJournalEntry,
    TradeDirection,
    TradeResultStatus,
    normalize_result_note,
)
from trading_ai.watchlist.domain import normalize_ticker


class _InsightLookup(Protocol):
    async def get_by_id(self, insight_id: int) -> object | None: ...


class _JournalRepositoryLike(Protocol):
    async def add(self, entry: NewJournalEntry) -> JournalEntry: ...

    async def list_recent(self) -> list[JournalEntry]: ...

    async def get_by_id(self, entry_id: int) -> JournalEntry | None: ...

    async def update(
        self, entry_id: int, edit: JournalEntryEdit, updated_at: datetime
    ) -> JournalEntry | None: ...


async def _require_insight_if_supplied(
    insight_lookup: _InsightLookup, insight_id: int | None
) -> None:
    if insight_id is None:
        return
    insight = await insight_lookup.get_by_id(insight_id)
    if insight is None:
        raise InsightNotFoundError(insight_id)


class CreateJournalEntry:
    def __init__(
        self, repository: _JournalRepositoryLike, insight_lookup: _InsightLookup
    ) -> None:
        self._repository = repository
        self._insight_lookup = insight_lookup

    async def execute(
        self,
        raw_ticker: str,
        direction: TradeDirection,
        result_status: TradeResultStatus,
        result_note: str | None,
        insight_id: int | None,
    ) -> JournalEntry:
        ticker = normalize_ticker(raw_ticker)
        note = normalize_result_note(result_note)
        await _require_insight_if_supplied(self._insight_lookup, insight_id)
        return await self._repository.add(
            NewJournalEntry(
                ticker=ticker,
                direction=direction,
                result_status=result_status,
                result_note=note,
                insight_id=insight_id,
            )
        )


class ListJournalEntries:
    def __init__(self, repository: _JournalRepositoryLike) -> None:
        self._repository = repository

    async def execute(self) -> list[JournalEntry]:
        return await self._repository.list_recent()


class GetJournalEntry:
    def __init__(self, repository: _JournalRepositoryLike) -> None:
        self._repository = repository

    async def execute(self, entry_id: int) -> JournalEntry:
        entry = await self._repository.get_by_id(entry_id)
        if entry is None:
            raise JournalEntryNotFoundError(entry_id)
        return entry


class UpdateJournalEntry:
    def __init__(
        self, repository: _JournalRepositoryLike, insight_lookup: _InsightLookup
    ) -> None:
        self._repository = repository
        self._insight_lookup = insight_lookup

    async def execute(
        self,
        entry_id: int,
        raw_ticker: str,
        direction: TradeDirection,
        result_status: TradeResultStatus,
        result_note: str | None,
        insight_id: int | None,
    ) -> JournalEntry:
        ticker = normalize_ticker(raw_ticker)
        note = normalize_result_note(result_note)
        await _require_insight_if_supplied(self._insight_lookup, insight_id)
        updated = await self._repository.update(
            entry_id,
            JournalEntryEdit(
                ticker=ticker,
                direction=direction,
                result_status=result_status,
                result_note=note,
                insight_id=insight_id,
            ),
            datetime.now(UTC),
        )
        if updated is None:
            raise JournalEntryNotFoundError(entry_id)
        return updated
