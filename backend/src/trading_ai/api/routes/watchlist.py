"""Watchlist HTTP endpoints — thin transport layer only (ADR-0002, §17).

Route handlers call application use cases and translate the result (or
a domain error) to HTTP. They never touch SQL, the engine, or the
repository directly, and never receive a raw ORM instance back
(ADR-0002, §17, §27 criteria 2 and 4).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading_ai.infrastructure.database.session import session_scope
from trading_ai.watchlist.domain import (
    DuplicateTickerError,
    InvalidTickerError,
    WatchlistItem,
)
from trading_ai.watchlist.repository import WatchlistRepository
from trading_ai.watchlist.use_cases import AddWatchlistItem, ListWatchlistItems

router = APIRouter()


class WatchlistItemRequest(BaseModel):
    """Transport DTO — deliberately not the domain model (ADR-0002, §18.2).

    No format constraints here beyond "a string": trim/uppercase/empty/
    length/charset rules are business validation and live in
    `trading_ai.watchlist.domain.normalize_ticker`, not in this DTO.
    """

    ticker: str


class WatchlistItemResponse(BaseModel):
    """Transport DTO returned to the client — not the ORM model."""

    id: int
    ticker: str
    created_at: datetime


def _to_response(item: WatchlistItem) -> WatchlistItemResponse:
    return WatchlistItemResponse(id=item.id, ticker=item.ticker, created_at=item.created_at)


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the session factory created by the lifespan, or fail controlled.

    Mirrors `trading_ai.api.routes.ready.get_database_engine`: a
    generic 503 if `TRADING_AI_DATABASE_URL` is not configured, no
    configuration detail leaked.
    """
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
    """One session per request, one short transaction (ADR-0004 §25).

    Commits after a successful request, rolls back on any error
    (including a translated domain error) — see
    `trading_ai.infrastructure.database.session.session_scope`.
    """
    async with session_scope(factory) as session:
        yield session


def get_watchlist_repository(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WatchlistRepository:
    return WatchlistRepository(session)


def get_add_watchlist_item_use_case(
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> AddWatchlistItem:
    return AddWatchlistItem(repository)


def get_list_watchlist_items_use_case(
    repository: Annotated[WatchlistRepository, Depends(get_watchlist_repository)],
) -> ListWatchlistItems:
    return ListWatchlistItems(repository)


@router.post(
    "/watchlist",
    status_code=status.HTTP_201_CREATED,
    response_model=WatchlistItemResponse,
)
async def add_watchlist_item(
    payload: WatchlistItemRequest,
    use_case: Annotated[AddWatchlistItem, Depends(get_add_watchlist_item_use_case)],
) -> WatchlistItemResponse:
    item = await use_case.execute(payload.ticker)
    return _to_response(item)


@router.get("/watchlist", response_model=list[WatchlistItemResponse])
async def list_watchlist_items(
    use_case: Annotated[ListWatchlistItems, Depends(get_list_watchlist_items_use_case)],
) -> list[WatchlistItemResponse]:
    items = await use_case.execute()
    return [_to_response(item) for item in items]


def register_watchlist_exception_handlers(app: FastAPI) -> None:
    """Map watchlist domain errors to safe, controlled HTTP responses.

    Registered once from `create_app()` — the official FastAPI pattern
    (ADR-0002, §32) instead of scattering try/except in route handlers.
    No internal exception detail is included in the response body.
    """

    @app.exception_handler(DuplicateTickerError)
    async def _handle_duplicate_ticker(
        _request: Request, _exc: DuplicateTickerError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "ticker already in watchlist"},
        )

    @app.exception_handler(InvalidTickerError)
    async def _handle_invalid_ticker(
        _request: Request, exc: InvalidTickerError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.reason},
        )
