"""Unit tests for `journal.domain` — no DB, no HTTP (task scope §16)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from trading_ai.journal.domain import (
    InvalidJournalEntryError,
    JournalEntry,
    JournalEntryEdit,
    JournalEntryNotFoundError,
    NewJournalEntry,
    TradeDirection,
    TradeResultStatus,
    normalize_result_note,
)

_T = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def test_trade_direction_has_exactly_two_categorical_values() -> None:
    """Product Owner decision: categorical enum, not free text."""
    values = {member.value for member in TradeDirection}
    assert values == {"long", "short"}


def test_trade_result_status_has_exactly_four_categorical_values() -> None:
    """Product Owner decision: categorical status + optional text, 4
    values including "open" for a trade logged before it closes."""
    values = {member.value for member in TradeResultStatus}
    assert values == {"profit", "loss", "breakeven", "open"}


def test_direction_and_result_status_values_are_stable_machine_identifiers() -> None:
    for member in list(TradeDirection) + list(TradeResultStatus):
        assert member.value.islower()
        assert " " not in member.value
        assert not any(ch.isalpha() and ord(ch) > 127 for ch in member.value)


def test_new_journal_entry_allows_optional_insight_link() -> None:
    entry = NewJournalEntry(
        ticker="AAPL",
        direction=TradeDirection.LONG,
        result_status=TradeResultStatus.OPEN,
        result_note=None,
        insight_id=None,
    )
    assert entry.insight_id is None


def test_new_journal_entry_with_insight_link() -> None:
    entry = NewJournalEntry(
        ticker="AAPL",
        direction=TradeDirection.SHORT,
        result_status=TradeResultStatus.PROFIT,
        result_note="Сработало по плану.",
        insight_id=42,
    )
    assert entry.insight_id == 42
    assert entry.result_note == "Сработало по плану."


def test_normalize_result_note_none_stays_none() -> None:
    assert normalize_result_note(None) is None


def test_normalize_result_note_blank_becomes_none() -> None:
    assert normalize_result_note("   ") is None


def test_normalize_result_note_strips_whitespace() -> None:
    assert normalize_result_note("  текст  ") == "текст"


def test_normalize_result_note_too_long_raises() -> None:
    with pytest.raises(InvalidJournalEntryError):
        normalize_result_note("x" * 2001)


def test_normalize_result_note_at_limit_ok() -> None:
    note = "x" * 2000
    assert normalize_result_note(note) == note


def test_journal_entry_is_frozen() -> None:
    """Journal entries are editable at the row level (Product Owner:
    editable, no delete) but a returned Python object is never mutated
    in place — the same convention as `SavedInsight`/`InsightEvaluation`."""
    entry = JournalEntry(
        id=1,
        ticker="AAPL",
        direction=TradeDirection.LONG,
        result_status=TradeResultStatus.PROFIT,
        result_note=None,
        insight_id=None,
        created_at=_T,
        updated_at=None,
    )
    with pytest.raises((AttributeError, TypeError)):
        entry.ticker = "MSFT"  # type: ignore[misc]


def test_journal_entry_edit_carries_all_journal_owned_fields() -> None:
    edit = JournalEntryEdit(
        ticker="MSFT",
        direction=TradeDirection.SHORT,
        result_status=TradeResultStatus.LOSS,
        result_note="Не сработало.",
        insight_id=7,
    )
    assert edit.ticker == "MSFT"
    assert edit.insight_id == 7


def test_journal_entry_not_found_error_carries_id() -> None:
    error = JournalEntryNotFoundError(42)
    assert error.entry_id == 42


def test_journal_entry_never_has_broker_or_pnl_fields() -> None:
    """Structural guard (task scope §5/§26): no entry/exit price,
    quantity, commission, leverage, stop-loss/take-profit, order id,
    execution venue, or realized P&L field exists on the domain model."""
    fields = set(JournalEntry.__dataclass_fields__)
    forbidden = {
        "entry_price",
        "exit_price",
        "quantity",
        "commission",
        "leverage",
        "stop_loss",
        "take_profit",
        "order_id",
        "execution_venue",
        "realized_pnl",
        "pnl",
        "broker",
    }
    assert fields.isdisjoint(forbidden)
