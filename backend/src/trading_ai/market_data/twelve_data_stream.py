"""Twelve Data WebSocket transport + payload normalization (Phase 2C.2).

The only file in the codebase that knows Twelve Data's WebSocket URL,
message shapes, or field names (task scope §4, §20 — mirrors
`gateway.py`'s role as the sole REST boundary, same `ADR-0007 §20-21`
isolation pattern applied to streaming). `live_manager.py` depends only
on `live_provider.LiveStreamClientLike` and the pure functions here
that produce `market_data.live_state` domain types — it never sees a
raw Twelve Data frame.

Research basis (task scope §3 — official sources only, verified live
for this task, not from memory):

- WebSocket URL, subscribe/unsubscribe/reset/heartbeat message shapes,
  and the heartbeat interval are all **officially confirmed**, cross-
  checked against both the official support article and the official
  `twelvedata-python` SDK source:
  https://support.twelvedata.com/en/articles/5620516-how-to-stream-the-data
  https://support.twelvedata.com/en/articles/5194610-websocket-faq
  https://github.com/twelvedata/twelvedata-python (src/twelvedata/websocket.py)
- **Officially confirmed unavailable via WebSocket**: technical
  indicators, OHLC data, and bid/ask prices (websocket-faq article,
  verbatim) — this adapter never expects or parses any of those from a
  stream frame; OHLC aggregation happens entirely client-side via
  `market_data.live_state.apply_price_update`.
- **NOT officially confirmed** (no official schema/example found for
  either): the exact literal field names inside a `price` event, and
  the unit (seconds vs. milliseconds) of its `timestamp`. The one
  concrete example found (`{'event': 'price', 'symbol': 'BTC/USD',
  'timestamp': 1600595462, 'price': 10964.8, 'day_volume': 38279, ...}`)
  is from a non-official, explicitly-flagged community source
  (dev.to), used here only because it is internally consistent with
  the official support article's prose description ("brief meta
  information, UNIX timestamp, and the price itself. The daily volume
  will be also returned where available") and because *some* concrete
  field mapping is required to implement anything at all. Every
  field access below is defensive (missing/wrong-type → a caught,
  counted `MarketDataMalformedResponseError`, never a crash) precisely
  because this mapping is not officially guaranteed. **This should be
  verified against a real live connection before this adapter is
  trusted in production** — recorded as a known limitation in the
  final report, not silently assumed correct.
- Volume (`day_volume` in the only example found) is officially
  described only as "daily volume... returned where available" — never
  described as incremental. `parse_price_event` below therefore never
  populates `PriceUpdateEvent.volume_hint` from it (task scope §10).
- `is_market_open` (REST `/quote`) is officially confirmed as a plain
  boolean, with no separate pre-market/after-hours field anywhere
  (`/market_state` has the same limitation) — `market_state_from_quote`
  below reflects this honestly (task scope §12).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

import websockets
import websockets.exceptions

from trading_ai.market_data.live_provider import LiveProviderCapabilityError
from trading_ai.market_data.live_state import MarketState, PriceUpdateEvent, UpdateKind
from trading_ai.market_data.types import MarketDataMalformedResponseError

logger = logging.getLogger(__name__)

# Officially confirmed (see module docstring) — one unified endpoint
# for all asset classes, auth via the documented `apikey` query
# parameter (the provider's own convention for this endpoint, not a
# choice this adapter makes — contrast with `gateway.py`'s REST calls,
# which use a header specifically *because* REST offered that choice).
_WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"

# "Advised to be sent every 10 seconds to make sure that your
# connection stays alive" — support.twelvedata.com articles above,
# verbatim, both cross-checked.
HEARTBEAT_INTERVAL_SECONDS = 10.0

SOURCE = "twelvedata_ws"

# A wide, static sanity bound — not a unit-detection heuristic (task
# scope §11 explicitly forbids guessing seconds-vs-milliseconds by
# magnitude). This only rejects values that cannot possibly be a
# plausible trading-related UNIX-seconds timestamp in either direction
# (including a millisecond-scale value fed in by mistake, which would
# land far past 2100 if misread as seconds) — a defensive floor/ceiling,
# the same class of check as `live_state`'s own "price must be
# positive/finite", not a claim about which unit the provider actually
# uses.
_MIN_REASONABLE_TIMESTAMP = datetime(2000, 1, 1, tzinfo=timezone.utc)
_MAX_REASONABLE_TIMESTAMP = datetime(2100, 1, 1, tzinfo=timezone.utc)


class FrameKind(str, Enum):
    """Classifies a raw, already-JSON-decoded WS frame — used by the
    connection manager to decide how to log/handle it (task scope §19:
    "known harmless provider/status frames should be handled
    explicitly"). Only `event: "price"` and `event: "subscribe-status"`
    are officially named event types (websocket-faq article) — anything
    else, or a frame that isn't even a JSON object, is `UNKNOWN` and is
    always safely ignored, never raised as an error.
    """

    PRICE = "price"
    SUBSCRIBE_STATUS = "subscribe_status"
    UNKNOWN = "unknown"


def classify_frame(raw: object) -> FrameKind:
    if not isinstance(raw, dict):
        return FrameKind.UNKNOWN
    event = raw.get("event")
    if event == "price":
        return FrameKind.PRICE
    if event == "subscribe-status":
        return FrameKind.SUBSCRIBE_STATUS
    return FrameKind.UNKNOWN


def parse_price_event(raw: object) -> PriceUpdateEvent | None:
    """Pure. `None` for a frame that isn't a `price` event at all (not
    an error — the caller should simply not forward it to the live-state
    domain). Raises `MarketDataMalformedResponseError` (reused from the
    REST error taxonomy — this is still "the market data provider gave
    us something malformed", task scope §23: avoid an unjustified new
    exception class) for a frame that *is* a `price` event but is
    missing or has an unparseable required field — the caller
    (`live_manager.py`) is responsible for catching this, counting it,
    and continuing (task scope §19), never crashing the receive loop.

    `volume_hint` is always `None` on the returned event — see module
    docstring: Twelve Data's own daily-volume semantics are not proven
    incremental, so this adapter never guesses a per-tick contribution
    (task scope §10).
    """
    if not isinstance(raw, dict) or raw.get("event") != "price":
        return None

    try:
        symbol = raw["symbol"]
        if not isinstance(symbol, str) or not symbol.strip():
            raise MarketDataMalformedResponseError("price event missing a usable symbol")

        price = Decimal(str(raw["price"]))
        if not price.is_finite():
            raise MarketDataMalformedResponseError("price event price is not finite")

        timestamp = _parse_stream_timestamp(raw["timestamp"])
    except KeyError as exc:
        raise MarketDataMalformedResponseError(
            f"price event missing required field: {exc}"
        ) from exc
    except (InvalidOperation, TypeError, ValueError, OverflowError, OSError) as exc:
        raise MarketDataMalformedResponseError(
            "price event field could not be parsed"
        ) from exc

    return PriceUpdateEvent(
        symbol=symbol.strip(),
        price=price,
        timestamp=timestamp,
        source=SOURCE,
        kind=UpdateKind.PROVISIONAL,
        volume_hint=None,
    )


def _parse_stream_timestamp(raw_timestamp: object) -> datetime:
    """See module docstring: seconds-based, consistent with the
    already-proven REST timestamp convention (`gateway.py`) and the one
    concrete (non-official) example found — never a magnitude-based
    seconds-vs-milliseconds heuristic. Out-of-bounds values (including
    a millisecond-scale value, which would land far outside this range
    if misread as seconds) fail safely as malformed rather than
    producing a silently-wrong date (task scope §11).
    """
    timestamp = datetime.fromtimestamp(int(raw_timestamp), tz=timezone.utc)  # type: ignore[call-overload]
    if not (_MIN_REASONABLE_TIMESTAMP <= timestamp <= _MAX_REASONABLE_TIMESTAMP):
        raise MarketDataMalformedResponseError(
            f"price event timestamp out of plausible range: {raw_timestamp!r}"
        )
    return timestamp


def market_state_from_quote(is_market_open: bool | None) -> MarketState:
    """Twelve Data's `/quote` and `/market_state` both expose only a
    plain boolean (confirmed live, task scope §12/§14) — there is no
    separate pre-market/after-hours field to map from anywhere in the
    provider's documented contract. `True` is a positive, provable
    signal (`OPEN`). `False` and `None` both honestly map to `UNKNOWN`
    rather than `CLOSED`: a `False` value cannot be proven to mean the
    market is fully closed rather than in an extended-hours session
    this single boolean has no way to express (task scope §12: "if
    extended-hours distinction cannot be known, keep
    MarketState.UNKNOWN rather than guessing").
    """
    if is_market_open is True:
        return MarketState.OPEN
    return MarketState.UNKNOWN


class TwelveDataStreamClient:
    """Concrete `LiveStreamClientLike` for Twelve Data (structural typing
    — no explicit inheritance needed, `live_provider.LiveStreamClientLike`
    is a `Protocol`). Holds one connection at a time; the caller
    (`LiveMarketManager`) owns reconnect/retry policy, this class only
    knows how to open, use, and close a single connection attempt.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _WS_URL,
        connector: Callable[[str], Awaitable[Any]] = websockets.connect,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        # Injectable only for tests — mirrors `gateway.py`'s own
        # `transport: httpx.AsyncBaseTransport | None` seam; `None`/the
        # default means the real `websockets.connect`, unchanged in
        # production.
        self._connector = connector
        self._connection: Any = None

    async def connect(self) -> None:
        url = f"{self._base_url}?apikey={self._api_key}"
        # Never log `url` — it carries the API key as a query parameter
        # (the provider's own documented convention for this endpoint,
        # task scope §6). Only a redacted, key-free form is ever logged.
        logger.info("twelve_data_stream operation=connect url=%s", self._redacted_url())
        try:
            self._connection = await self._connector(url)
        except websockets.exceptions.InvalidStatus as exc:
            status_code = exc.response.status_code
            if status_code in (401, 403):
                # A *structural* capability failure (task scope §7),
                # not a transient one — translated into the
                # provider-agnostic `LiveProviderCapabilityError` so
                # `live_manager.py` never needs to know this is a
                # websockets-library-specific exception type at all
                # (task scope §20).
                raise LiveProviderCapabilityError(
                    f"provider rejected the WebSocket handshake (HTTP {status_code}) — "
                    "likely an account/plan without WebSocket access"
                ) from exc
            raise

    def __repr__(self) -> str:
        # Explicit override, not just relying on the default object
        # repr's lack of attribute access — makes the "never leaks the
        # API key" property an enforced, tested contract rather than
        # an accident of the default repr (task scope §24, item 24).
        return (
            f"TwelveDataStreamClient(base_url={self._base_url!r}, "
            f"connected={self._connection is not None})"
        )

    async def subscribe(self, symbols: Sequence[str]) -> None:
        await self._send({"action": "subscribe", "params": {"symbols": ",".join(symbols)}})

    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        await self._send({"action": "unsubscribe", "params": {"symbols": ",".join(symbols)}})

    async def send_heartbeat(self) -> None:
        await self._send({"action": "heartbeat"})

    async def receive(self) -> object:
        if self._connection is None:
            raise RuntimeError("TwelveDataStreamClient.receive() called before connect()")
        raw_text = await self._connection.recv()
        try:
            return json.loads(raw_text)
        except (ValueError, TypeError) as exc:
            raise MarketDataMalformedResponseError("provider sent a non-JSON WS frame") from exc

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    def _redacted_url(self) -> str:
        return f"{self._base_url}?apikey=***"

    async def _send(self, payload: dict[str, Any]) -> None:
        if self._connection is None:
            raise RuntimeError("TwelveDataStreamClient cannot send before connect()")
        await self._connection.send(json.dumps(payload))
