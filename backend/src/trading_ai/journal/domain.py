"""Trade journal domain model (MODULE_BOUNDARIES.md §13 "journal").

Implements FR-030 ("Пользователь может вручную зафиксировать сделку
(инструмент, направление, результат) в дневнике") and UJ-017's optional
link to a previously-formed insight. **Not** a broker/order/portfolio
subsystem (task scope §26) — deliberately no entry/exit price, quantity,
commission, leverage, stop-loss/take-profit, order id, execution venue,
or realized P&L, since FR-030 does not require any of them.

Depends on `trading_ai.insights` only for existence-checking an
optionally-referenced insight id (MODULE_BOUNDARIES.md §13: "insights —
только для ссылки") — this module never reads or writes insight
*content*, and never touches `ai`/`llm_gateway`/`market_data` directly
(explicitly forbidden dependencies for `journal`).

**Product Owner decisions** (documents left these open, resolved via
`AskUserQuestion` rather than invented silently):
- **Mutability — editable, no delete**: an entry may be corrected after
  creation (`updated_at` records that it was), but there is no delete
  endpoint/UI in this slice and no soft-delete flag — a mistake is
  fixed by editing, not removed from history.
- **Result format — categorical status + optional free text**:
  `TradeResultStatus` is a small, stable, machine-value enum
  (profit/loss/breakeven/open — "open" covers a trade logged before it
  closes, since entries are now editable and can be updated once the
  outcome is known), plus an optional bounded `result_note` for
  context — never a numeric P&L field, which FR-030 does not require.
- **Direction format — categorical enum**: `TradeDirection`
  (long/short), not free text — a trade's direction is a stable,
  queryable fact, not prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

_MAX_RESULT_NOTE_LENGTH = 2000


class TradeDirection(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradeResultStatus(str, Enum):
    PROFIT = "profit"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    OPEN = "open"


class JournalError(Exception):
    """Base class for journal domain/application errors."""


class JournalEntryNotFoundError(JournalError):
    def __init__(self, entry_id: int) -> None:
        super().__init__(f"journal entry not found: {entry_id}")
        self.entry_id = entry_id


class InvalidJournalEntryError(JournalError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)


def normalize_result_note(raw: str | None) -> str | None:
    """`None`/blank both mean "no note" — `result_note` is optional
    (task scope §5), so an empty string is not an error, just nothing."""
    if raw is None:
        return None
    note = raw.strip()
    if not note:
        return None
    if len(note) > _MAX_RESULT_NOTE_LENGTH:
        raise InvalidJournalEntryError(
            f"result note must not exceed {_MAX_RESULT_NOTE_LENGTH} characters"
        )
    return note


@dataclass(frozen=True, slots=True)
class NewJournalEntry:
    ticker: str
    direction: TradeDirection
    result_status: TradeResultStatus
    result_note: str | None
    insight_id: int | None


@dataclass(frozen=True, slots=True)
class JournalEntryEdit:
    """Full-replace edit payload — every journal-owned field is
    resupplied, no partial-patch semantics (task scope §11: PUT, not
    PATCH, matching the `evaluations` module's precedent)."""

    ticker: str
    direction: TradeDirection
    result_status: TradeResultStatus
    result_note: str | None
    insight_id: int | None


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One journal entry — mutable at the row level (Product Owner:
    editable, no delete), but each read returns a fresh, frozen
    snapshot, same convention as `evaluations.domain.InsightEvaluation`."""

    id: int
    ticker: str
    direction: TradeDirection
    result_status: TradeResultStatus
    result_note: str | None
    insight_id: int | None
    created_at: datetime
    updated_at: datetime | None


# Bounded list (task scope §11/§13: no infinite scroll) — matches the
# established cap used for insight history.
MAX_JOURNAL_ITEMS = 50
