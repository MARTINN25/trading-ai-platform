"""Backend live-market SSE delivery — thin transport layer only (ADR-0002, §17).

Phase 2C.3: wires the already-implemented, provider-agnostic
`LiveMarketManager` (Phase 2C.2) into a client-facing Server-Sent
Events stream for one validated instrument at a time.

Target flow (task scope §3):

    Twelve Data WebSocket / REST fallback
            -> LiveMarketManager
            -> canonical InstrumentLiveState
            -> this SSE endpoint
            -> future frontend EventSource consumer (not built this slice)

This module never serializes a raw Twelve Data payload, the provider
WebSocket URL, or the API key — only the normalized
`market_data.live_state.InstrumentLiveState` contract, through the
`LiveMarketEventPayload` DTO below (task scope §3, §12, §24).

SSE, not a second WebSocket stack (task scope §4): the browser only
needs server -> client updates here, `EventSource` gives simple
built-in reconnect semantics, and the provider API key never has to
reach the browser either way — a bidirectional channel buys nothing
for this use case. No concrete SSE blocker was found while reading
`DATA_FLOWS.md`, `MODULE_BOUNDARIES.md`, `TARGET_INTELLIGENCE_CONTEXT.md`,
`TECHNOLOGY_EVALUATION.md`, `ADR-0006`, `ADR-0011`, or `ADR-0012` — none
of them mention a transport constraint for this kind of client
delivery at all; `ADR-0012` (Черновик) governs *background* monitoring
polling, a different concern from this already-running manager's
client-facing fan-out.

Reconnect / replay (task scope §20-§21): `EventSource` reconnects
automatically. This endpoint does not implement historical replay —
`Last-Event-ID` is intentionally never read, and every (re)connection
always subscribes fresh and emits a brand-new `snapshot` event from
current manager state. The SSE `id:` field is populated with the
manager's own revision purely for duplicate-detection/debugging, not
as a promise of replay.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from trading_ai.market_data.live_manager import LiveMarketManager
from trading_ai.market_data.live_state import (
    DEFAULT_FRESHNESS_POLICY,
    Bar,
    ConnectionState,
    FreshnessState,
    InstrumentLiveState,
    MarketState,
    VolumeQuality,
    derive_freshness_state,
)
from trading_ai.watchlist.domain import normalize_ticker

logger = logging.getLogger(__name__)

router = APIRouter()

_SCHEMA_VERSION = 1

# Deliberately distinct from the provider's own 10s heartbeat
# requirement (`twelve_data_stream.HEARTBEAT_INTERVAL_SECONDS`, task
# scope §15: "do not use provider 10s requirement as an automatic
# browser heartbeat interval without justification") — this is a
# browser/proxy keepalive concern, not a provider-connection concern.
# Named constant, not scattered magic (task scope §15).
BROWSER_SSE_HEARTBEAT_INTERVAL_SECONDS = 15.0


class LiveBarPayload(BaseModel):
    """Current/last-closed bar shape (task scope §13) — never fabricated
    when no live event has produced one yet (`current_bar`/
    `last_closed_bar` stay `None` on the envelope instead)."""

    interval_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    close_at: datetime
    volume: int | None = None
    volume_quality: VolumeQuality
    is_closed: bool


class LiveMarketEventPayload(BaseModel):
    """Versioned, normalized SSE payload (task scope §12) — the *only*
    shape ever sent to the browser. `market_state`/`connection_state`/
    `freshness_state` are `live_state.py`'s own `str, Enum` types, which
    Pydantic serializes as their plain string `.value` (never a Python
    repr, task scope §12). `Decimal` fields serialize as strings
    (Pydantic v2 default, already the project's existing convention —
    see `api.routes.instruments`'s DTOs); `datetime` fields serialize as
    ISO 8601 UTC.
    """

    schema_version: int = _SCHEMA_VERSION
    event: str
    symbol: str
    revision: int
    last_price: Decimal | None = None
    last_price_as_of: datetime | None = None
    market_state: MarketState
    connection_state: ConnectionState
    freshness_state: FreshnessState
    current_bar: LiveBarPayload | None = None
    last_closed_bar: LiveBarPayload | None = None
    source: str | None = None
    server_time: datetime


def _bar_payload(bar: Bar | None) -> LiveBarPayload | None:
    if bar is None:
        return None
    return LiveBarPayload(
        interval_start=bar.interval_start,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        close_at=bar.close_at,
        volume=bar.volume,
        volume_quality=bar.volume_quality,
        is_closed=bar.is_closed,
    )


def serialize_live_state(
    *, event: str, state: InstrumentLiveState, revision: int, now: datetime
) -> LiveMarketEventPayload:
    """The dedicated serializer (task scope §22) — the only place an
    `InstrumentLiveState` is turned into wire format. `freshness_state`
    is derived here (never stored, same rule `live_state.py` itself
    already enforces) using the domain's own default policy, since this
    task does not introduce a per-request/per-deployment override.
    """
    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, now)
    return LiveMarketEventPayload(
        event=event,
        symbol=state.instrument,
        revision=revision,
        last_price=state.last_price,
        last_price_as_of=state.last_price_as_of,
        market_state=state.market_state,
        connection_state=state.connection_state,
        freshness_state=freshness,
        current_bar=_bar_payload(state.current_bar),
        last_closed_bar=_bar_payload(state.last_closed_bar),
        source=state.last_update_source,
        server_time=now,
    )


def _format_sse_event(event_name: str, payload: LiveMarketEventPayload) -> str:
    """`id:` carries the manager's own revision (task scope §19, §21) —
    useful for client-side duplicate detection/debugging only; this
    endpoint never reads `Last-Event-ID` back (task scope §21: no replay
    is implemented or implied)."""
    return f"id: {payload.revision}\nevent: {event_name}\ndata: {payload.model_dump_json()}\n\n"


def _format_sse_heartbeat() -> str:
    """A plain SSE comment line (task scope §15) — ignored by
    `EventSource`'s `onmessage`, exists only so proxies/load balancers
    do not kill an otherwise-quiet connection during closed-market
    periods."""
    return ": heartbeat\n\n"


def get_live_market_manager(request: Request) -> LiveMarketManager:
    """Same optional-feature pattern as `api.routes.instruments
    .get_market_data_gateway` (task scope §5, §14): no
    `TRADING_AI_MARKET_DATA_API_KEY` -> no manager constructed at
    startup -> a controlled 503 here, never a crash and never a silent
    hang."""
    manager = getattr(request.app.state, "live_market_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="live market data is not configured",
        )
    return manager  # type: ignore[no-any-return]


async def _live_event_stream(
    manager: LiveMarketManager, ticker: str, request: Request
) -> AsyncGenerator[str, None]:
    """The SSE body generator (task scope §9, §16, §17, §18).

    Subscribe lifecycle: `manager.subscribe()` happens once, right
    before the first (`snapshot`) event; `manager.unsubscribe()` happens
    exactly once in `finally`, guaranteeing it runs on a normal client
    disconnect, a dead network, an exception raised anywhere in this
    generator, or the ASGI request task being cancelled — Python's
    `finally` semantics already cover all four (task scope §9: "no
    leaked refcounts").

    No tight polling loop and no unbounded per-client queue (task scope
    §10, §11, §18): each iteration calls
    `LiveMarketManager.wait_for_change`, which suspends on an
    `asyncio.Event` and returns only the *latest* state once the
    revision has actually moved — coalescing is therefore automatic, not
    something this generator has to implement itself.
    """
    await manager.subscribe(ticker)
    try:
        current = manager.get_state_with_revision(ticker)
        if current is None:
            # Structurally shouldn't happen — `subscribe()` above just
            # created/incremented this exact entry, and our own
            # reference keeps it alive until our own `unsubscribe()`
            # below. Handled defensively rather than assumed, per the
            # project's existing "never crash on an internal
            # impossibility" convention.
            logger.warning(
                "live_market operation=stream symbol=%s status=missing_subscription_after_subscribe",
                ticker,
            )
            return
        state, revision = current
        now = datetime.now(timezone.utc)
        yield _format_sse_event(
            "snapshot", serialize_live_state(event="snapshot", state=state, revision=revision, now=now)
        )

        while True:
            if await request.is_disconnected():
                break
            result = await manager.wait_for_change(
                ticker, revision, timeout=BROWSER_SSE_HEARTBEAT_INTERVAL_SECONDS
            )
            if result is None:
                if await request.is_disconnected():
                    break
                yield _format_sse_heartbeat()
                continue
            state, revision = result
            now = datetime.now(timezone.utc)
            yield _format_sse_event(
                "update", serialize_live_state(event="update", state=state, revision=revision, now=now)
            )
    finally:
        await manager.unsubscribe(ticker)


@router.get("/instruments/{ticker}/live-stream")
async def stream_instrument_live_state(
    ticker: str,
    request: Request,
    manager: Annotated[LiveMarketManager, Depends(get_live_market_manager)],
) -> StreamingResponse:
    """`GET /instruments/{ticker}/live-stream` — one instrument's
    canonical live state as `text/event-stream` (task scope §7).

    Ticker validation happens here, synchronously, *before*
    `StreamingResponse` is constructed (task scope §8): `normalize_ticker`
    raises `InvalidTickerError` for an invalid symbol, already mapped to
    a normal `422` by the existing global handler
    (`api.routes.watchlist.register_watchlist_exception_handlers`) —
    the client gets a standard JSON validation error, never a stream
    that opens and then immediately errors.

    Availability (task scope §14): a fully unconfigured feature (no
    `TRADING_AI_MARKET_DATA_API_KEY`, so no manager was constructed at
    all) is a `503` *before* the stream begins — via
    `get_live_market_manager` above, the same convention already used by
    `api.routes.instruments.get_market_data_gateway`. A *configured* but
    currently degraded/no-data/disconnected/market-closed feature is
    never a `503` — it is a truthful initial `snapshot` event
    (`freshness_state`/`connection_state` reflect exactly what is true),
    since the manager may still recover without the client having to
    reconnect (task scope §23).
    """
    normalized_ticker = normalize_ticker(ticker)

    return StreamingResponse(
        _live_event_stream(manager, normalized_ticker, request),
        media_type="text/event-stream",
        headers={
            # No caching of a live stream (task scope §25). No other,
            # proxy-specific headers added — this deployment's actual
            # reverse-proxy/CDN configuration was not part of this
            # task's required reading, so nothing beyond the standard
            # SSE contract is assumed about it (task scope §25: "do not
            # add proxy-specific headers unless justified").
            "Cache-Control": "no-cache",
        },
    )
