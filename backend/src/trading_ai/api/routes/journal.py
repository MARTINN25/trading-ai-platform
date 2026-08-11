"""Trade journal HTTP endpoints — thin transport layer only (ADR-0002
§17), same as `api.routes.watchlist`/`api.routes.instruments`/
`api.routes.evaluations`.

FR-030: a manual, single-user trade journal — never a broker/order/
portfolio subsystem. Request DTOs accept only journal-owned fields
(ticker, direction, result, optional insight link) — never insight
content/provenance (task scope §6).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading_ai.infrastructure.database.session import session_scope
from trading_ai.insights.repository import InsightRepository
from trading_ai.journal.domain import (
    InvalidJournalEntryError,
    JournalEntry,
    JournalEntryNotFoundError,
    TradeDirection,
    TradeResultStatus,
)
from trading_ai.journal.repository import JournalRepository
from trading_ai.journal.use_cases import (
    CreateJournalEntry,
    GetJournalEntry,
    ListJournalEntries,
    UpdateJournalEntry,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_RESULT_NOTE_LENGTH = 2000


class JournalEntryRequest(BaseModel):
    """Shared shape for both create (`POST /journal`) and full-replace
    edit (`PUT /journal/{id}`) — no partial-patch semantics. `extra="forbid"`
    so a client cannot smuggle in insight content/provenance or
    broker/order fields this endpoint never accepts (task scope §6, §26)."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    direction: TradeDirection
    result_status: TradeResultStatus
    result_note: str | None = Field(default=None, max_length=_MAX_RESULT_NOTE_LENGTH)
    insight_id: int | None = None


class JournalEntryResponse(BaseModel):
    id: int
    ticker: str
    direction: TradeDirection
    result_status: TradeResultStatus
    result_note: str | None
    insight_id: int | None
    created_at: datetime
    updated_at: datetime | None


class JournalEntriesResponse(BaseModel):
    items: list[JournalEntryResponse]


def _to_response(entry: JournalEntry) -> JournalEntryResponse:
    return JournalEntryResponse(
        id=entry.id,
        ticker=entry.ticker,
        direction=entry.direction,
        result_status=entry.result_status,
        result_note=entry.result_note,
        insight_id=entry.insight_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Duplicated (not imported) from `api.routes.watchlist`/
    `api.routes.instruments`/`api.routes.evaluations` — same reasoning
    as those modules' identical helper: this route module has no other
    reason to depend on any of them."""
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is not configured",
        )
    return factory  # type: ignore[no-any-return]


async def get_db_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """One session per request, one short transaction — same pattern as
    `api.routes.watchlist.get_db_session`."""
    async with session_scope(factory) as session:
        yield session


def get_journal_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JournalRepository:
    return JournalRepository(session)


def get_insight_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InsightRepository:
    return InsightRepository(session)


def get_create_journal_entry_use_case(
    journal_repository: Annotated[JournalRepository, Depends(get_journal_repository)],
    insight_repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> CreateJournalEntry:
    return CreateJournalEntry(journal_repository, insight_repository)


def get_list_journal_entries_use_case(
    journal_repository: Annotated[JournalRepository, Depends(get_journal_repository)],
) -> ListJournalEntries:
    return ListJournalEntries(journal_repository)


def get_journal_entry_use_case(
    journal_repository: Annotated[JournalRepository, Depends(get_journal_repository)],
) -> GetJournalEntry:
    return GetJournalEntry(journal_repository)


def get_update_journal_entry_use_case(
    journal_repository: Annotated[JournalRepository, Depends(get_journal_repository)],
    insight_repository: Annotated[InsightRepository, Depends(get_insight_repository)],
) -> UpdateJournalEntry:
    return UpdateJournalEntry(journal_repository, insight_repository)


@router.post("/journal", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    payload: JournalEntryRequest,
    use_case: Annotated[CreateJournalEntry, Depends(get_create_journal_entry_use_case)],
) -> JournalEntryResponse:
    started = time.monotonic()
    status_label = "error"
    entry: JournalEntry | None = None
    try:
        entry = await use_case.execute(
            payload.ticker,
            payload.direction,
            payload.result_status,
            payload.result_note,
            payload.insight_id,
        )
        status_label = "ok"
        return _to_response(entry)
    finally:
        logger.info(
            "operation=create_journal_entry journal_entry_id=%s ticker=%s status=%s latency_ms=%.1f",
            entry.id if entry is not None else "-",
            payload.ticker,
            status_label,
            (time.monotonic() - started) * 1000,
        )


@router.get("/journal", response_model=JournalEntriesResponse)
async def list_journal_entries(
    use_case: Annotated[ListJournalEntries, Depends(get_list_journal_entries_use_case)],
) -> JournalEntriesResponse:
    """Newest-first, bounded (task scope §11/§13) — a single global list,
    not scoped to one instrument (UJ-017: «Дневник сделок» is a
    standalone section, not per-ticker)."""
    entries = await use_case.execute()
    return JournalEntriesResponse(items=[_to_response(entry) for entry in entries])


@router.get("/journal/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: int,
    use_case: Annotated[GetJournalEntry, Depends(get_journal_entry_use_case)],
) -> JournalEntryResponse:
    entry = await use_case.execute(entry_id)
    return _to_response(entry)


@router.put("/journal/{entry_id}", response_model=JournalEntryResponse)
async def update_journal_entry(
    entry_id: int,
    payload: JournalEntryRequest,
    use_case: Annotated[UpdateJournalEntry, Depends(get_update_journal_entry_use_case)],
) -> JournalEntryResponse:
    """Full-replace edit (Product Owner: editable, no delete, task
    scope §15) — every journal-owned field is resupplied."""
    started = time.monotonic()
    status_label = "error"
    try:
        entry = await use_case.execute(
            entry_id,
            payload.ticker,
            payload.direction,
            payload.result_status,
            payload.result_note,
            payload.insight_id,
        )
        status_label = "ok"
        return _to_response(entry)
    finally:
        logger.info(
            "operation=update_journal_entry journal_entry_id=%s ticker=%s status=%s latency_ms=%.1f",
            entry_id,
            payload.ticker,
            status_label,
            (time.monotonic() - started) * 1000,
        )


def register_journal_exception_handlers(app: FastAPI) -> None:
    """`InsightNotFoundError` is already handled globally by
    `api.routes.instruments.register_insight_exception_handlers` (404) —
    not re-registered here."""

    @app.exception_handler(JournalEntryNotFoundError)
    async def _handle_journal_entry_not_found(
        _request: Request, _exc: JournalEntryNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "journal entry not found"},
        )

    @app.exception_handler(InvalidJournalEntryError)
    async def _handle_invalid_journal_entry(
        _request: Request, _exc: InvalidJournalEntryError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "invalid journal entry"},
        )
