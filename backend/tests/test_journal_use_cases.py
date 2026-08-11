"""Use-case tests for `journal.use_cases` — fake repositories only, no
DB/HTTP (task scope §18)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.insights.domain import InsightNotFoundError
from trading_ai.journal.domain import (
    InvalidJournalEntryError,
    JournalEntry,
    JournalEntryEdit,
    JournalEntryNotFoundError,
    NewJournalEntry,
    TradeDirection,
    TradeResultStatus,
)
from trading_ai.journal.use_cases import (
    CreateJournalEntry,
    GetJournalEntry,
    ListJournalEntries,
    UpdateJournalEntry,
)
from trading_ai.watchlist.domain import InvalidTickerError

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


class _FakeInsight:
    def __init__(self, insight_id: int) -> None:
        self.id = insight_id


class FakeInsightLookup:
    def __init__(self, existing_ids: set[int]) -> None:
        self._existing_ids = existing_ids

    async def get_by_id(self, insight_id: int) -> _FakeInsight | None:
        return _FakeInsight(insight_id) if insight_id in self._existing_ids else None


class FakeJournalRepository:
    def __init__(self) -> None:
        self.added: list[NewJournalEntry] = []
        self._rows: dict[int, JournalEntry] = {}
        self._next_id = 1

    async def add(self, entry: NewJournalEntry) -> JournalEntry:
        self.added.append(entry)
        saved = JournalEntry(
            id=self._next_id,
            ticker=entry.ticker,
            direction=entry.direction,
            result_status=entry.result_status,
            result_note=entry.result_note,
            insight_id=entry.insight_id,
            created_at=_T,
            updated_at=None,
        )
        self._rows[self._next_id] = saved
        self._next_id += 1
        return saved

    async def list_recent(self) -> list[JournalEntry]:
        return list(self._rows.values())

    async def get_by_id(self, entry_id: int) -> JournalEntry | None:
        return self._rows.get(entry_id)

    async def update(
        self, entry_id: int, edit: JournalEntryEdit, updated_at: datetime
    ) -> JournalEntry | None:
        existing = self._rows.get(entry_id)
        if existing is None:
            return None
        updated = JournalEntry(
            id=existing.id,
            ticker=edit.ticker,
            direction=edit.direction,
            result_status=edit.result_status,
            result_note=edit.result_note,
            insight_id=edit.insight_id,
            created_at=existing.created_at,
            updated_at=updated_at,
        )
        self._rows[entry_id] = updated
        return updated


@pytest.mark.anyio
async def test_create_journal_entry_success() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup(set()))

    entry = await use_case.execute("AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None)

    assert entry.ticker == "AAPL"
    assert entry.direction is TradeDirection.LONG
    assert entry.result_status is TradeResultStatus.OPEN
    assert entry.insight_id is None
    assert len(repository.added) == 1


@pytest.mark.anyio
async def test_create_journal_entry_normalizes_ticker() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup(set()))

    entry = await use_case.execute("  aapl  ", TradeDirection.LONG, TradeResultStatus.OPEN, None, None)

    assert entry.ticker == "AAPL"


@pytest.mark.anyio
async def test_create_journal_entry_invalid_ticker_raises() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup(set()))

    with pytest.raises(InvalidTickerError):
        await use_case.execute("", TradeDirection.LONG, TradeResultStatus.OPEN, None, None)
    assert repository.added == []


@pytest.mark.anyio
async def test_create_journal_entry_with_valid_insight_link() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup({7}))

    entry = await use_case.execute(
        "AAPL", TradeDirection.LONG, TradeResultStatus.PROFIT, "Хорошая сделка.", 7
    )

    assert entry.insight_id == 7


@pytest.mark.anyio
async def test_create_journal_entry_unknown_insight_raises_before_persisting() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup(set()))

    with pytest.raises(InsightNotFoundError):
        await use_case.execute("AAPL", TradeDirection.LONG, TradeResultStatus.PROFIT, None, 999)
    assert repository.added == []


@pytest.mark.anyio
async def test_create_journal_entry_blank_note_becomes_none() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup(set()))

    entry = await use_case.execute("AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, "   ", None)

    assert entry.result_note is None


@pytest.mark.anyio
async def test_create_journal_entry_too_long_note_raises() -> None:
    repository = FakeJournalRepository()
    use_case = CreateJournalEntry(repository, FakeInsightLookup(set()))

    with pytest.raises(InvalidJournalEntryError):
        await use_case.execute("AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, "x" * 2001, None)
    assert repository.added == []


@pytest.mark.anyio
async def test_list_journal_entries_returns_repository_results() -> None:
    repository = FakeJournalRepository()
    await CreateJournalEntry(repository, FakeInsightLookup(set())).execute(
        "AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None
    )
    use_case = ListJournalEntries(repository)

    results = await use_case.execute()

    assert len(results) == 1
    assert results[0].ticker == "AAPL"


@pytest.mark.anyio
async def test_get_journal_entry_found() -> None:
    repository = FakeJournalRepository()
    created = await CreateJournalEntry(repository, FakeInsightLookup(set())).execute(
        "AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None
    )
    use_case = GetJournalEntry(repository)

    result = await use_case.execute(created.id)

    assert result.id == created.id


@pytest.mark.anyio
async def test_get_journal_entry_missing_raises() -> None:
    repository = FakeJournalRepository()
    use_case = GetJournalEntry(repository)

    with pytest.raises(JournalEntryNotFoundError):
        await use_case.execute(999)


@pytest.mark.anyio
async def test_update_journal_entry_success() -> None:
    repository = FakeJournalRepository()
    created = await CreateJournalEntry(repository, FakeInsightLookup(set())).execute(
        "AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None
    )
    use_case = UpdateJournalEntry(repository, FakeInsightLookup(set()))

    updated = await use_case.execute(
        created.id, "AAPL", TradeDirection.LONG, TradeResultStatus.PROFIT, "Закрыто с прибылью.", None
    )

    assert updated.result_status is TradeResultStatus.PROFIT
    assert updated.result_note == "Закрыто с прибылью."
    assert updated.updated_at is not None


@pytest.mark.anyio
async def test_update_journal_entry_missing_raises() -> None:
    repository = FakeJournalRepository()
    use_case = UpdateJournalEntry(repository, FakeInsightLookup(set()))

    with pytest.raises(JournalEntryNotFoundError):
        await use_case.execute(999, "AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None)


@pytest.mark.anyio
async def test_update_journal_entry_unknown_insight_raises() -> None:
    repository = FakeJournalRepository()
    created = await CreateJournalEntry(repository, FakeInsightLookup(set())).execute(
        "AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, None
    )
    use_case = UpdateJournalEntry(repository, FakeInsightLookup(set()))

    with pytest.raises(InsightNotFoundError):
        await use_case.execute(
            created.id, "AAPL", TradeDirection.LONG, TradeResultStatus.OPEN, None, 999
        )


@pytest.mark.anyio
async def test_use_cases_never_touch_insight_content() -> None:
    """Structural guard (task scope §6): `FakeInsightLookup` only ever
    exposes an id — there is no attribute path by which these use cases
    could read or forward insight text/provenance."""
    repository = FakeJournalRepository()
    lookup = FakeInsightLookup({7})
    assert not hasattr(_FakeInsight(7), "summary")
    assert not hasattr(_FakeInsight(7), "provider")
    await CreateJournalEntry(repository, lookup).execute(
        "AAPL", TradeDirection.LONG, TradeResultStatus.PROFIT, None, 7
    )
