"""Deterministic tests for `market_data/twelve_data_stream.py` (Phase 2C.2).

Normalization functions are pure and tested directly with no network
and no real `websockets` connection. `TwelveDataStreamClient`'s message
shape/URL/error-translation behavior is tested via an injected fake
connector (mirrors `test_market_data_gateway.py`'s `httpx.MockTransport`
pattern for the REST gateway) — never a real socket.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
import websockets.exceptions
from websockets import http11
from websockets.datastructures import Headers

from trading_ai.market_data.live_provider import LiveProviderCapabilityError
from trading_ai.market_data.live_state import MarketState, UpdateKind
from trading_ai.market_data.twelve_data_stream import (
    HEARTBEAT_INTERVAL_SECONDS,
    FrameKind,
    TwelveDataStreamClient,
    classify_frame,
    market_state_from_quote,
    parse_price_event,
)
from trading_ai.market_data.types import MarketDataMalformedResponseError

_FAKE_API_KEY = "test-secret-ws-key-should-never-leak"


# --- classify_frame ----------------------------------------------------


def test_classify_frame_price_event() -> None:
    assert classify_frame({"event": "price", "symbol": "AAPL"}) is FrameKind.PRICE


def test_classify_frame_subscribe_status() -> None:
    assert classify_frame({"event": "subscribe-status"}) is FrameKind.SUBSCRIBE_STATUS


def test_classify_frame_unknown_event_name() -> None:
    assert classify_frame({"event": "something-else"}) is FrameKind.UNKNOWN


def test_classify_frame_non_dict_is_unknown() -> None:
    assert classify_frame("not a dict") is FrameKind.UNKNOWN
    assert classify_frame(None) is FrameKind.UNKNOWN
    assert classify_frame([1, 2, 3]) is FrameKind.UNKNOWN


def test_classify_frame_missing_event_key_is_unknown() -> None:
    assert classify_frame({"symbol": "AAPL", "price": 100}) is FrameKind.UNKNOWN


# --- parse_price_event: happy path / task scope §24 items 1-3 ----------


def test_parse_price_event_maps_provider_payload_to_price_update_event() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": 303.94, "timestamp": 1_754_812_800}

    event = parse_price_event(raw)

    assert event is not None
    assert event.symbol == "AAPL"
    assert event.price == Decimal("303.94")
    assert event.timestamp == datetime.fromtimestamp(1_754_812_800, tz=timezone.utc)
    assert event.timestamp.tzinfo is not None
    assert event.kind is UpdateKind.PROVISIONAL
    assert event.source == "twelvedata_ws"


def test_parse_price_event_preserves_decimal_precision() -> None:
    """task scope §24 item 2 — a string price avoids float rounding
    entirely; even a numeric JSON value is immediately routed through
    `Decimal(str(...))`, not kept as a Python float."""
    raw = {"event": "price", "symbol": "AAPL", "price": "303.9401", "timestamp": 1_754_812_800}

    event = parse_price_event(raw)

    assert event is not None
    assert event.price == Decimal("303.9401")
    assert isinstance(event.price, Decimal)


def test_parse_price_event_non_price_event_returns_none() -> None:
    assert parse_price_event({"event": "subscribe-status", "status": "ok"}) is None


def test_parse_price_event_non_dict_returns_none() -> None:
    assert parse_price_event("garbage") is None
    assert parse_price_event(None) is None


# --- UTC timestamp normalization: task scope §11, §24 items 3-4 ---------


def test_parse_price_event_seconds_epoch_timestamp() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": "100", "timestamp": 1_754_812_800}

    event = parse_price_event(raw)

    assert event is not None
    assert event.timestamp == datetime(2025, 8, 10, 8, 0, tzinfo=timezone.utc)


def test_parse_price_event_millisecond_scale_timestamp_is_rejected_not_misinterpreted() -> None:
    """task scope §11: a millisecond-epoch value must never be silently
    misread as seconds (which would land the date ~year 57588) — the
    sanity-bound check fails it safely as malformed instead."""
    ms_scale_timestamp = 1_754_812_800_000  # what the same instant would look like in ms

    raw = {"event": "price", "symbol": "AAPL", "price": "100", "timestamp": ms_scale_timestamp}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_malformed_timestamp_string_rejected() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": "100", "timestamp": "not-a-timestamp"}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_missing_timestamp_rejected() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": "100"}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_negative_timestamp_rejected() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": "100", "timestamp": -5}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


# --- ambiguous/unproven volume: task scope §10, §24 item 5 --------------


def test_parse_price_event_never_populates_volume_hint_from_day_volume() -> None:
    """Even when the (non-officially-confirmed) `day_volume` field is
    present, `volume_hint` must stay `None` — Twelve Data's own docs
    describe this as daily volume, never proven incremental."""
    raw = {
        "event": "price",
        "symbol": "AAPL",
        "price": "100",
        "timestamp": 1_754_812_800,
        "day_volume": 38279,
    }

    event = parse_price_event(raw)

    assert event is not None
    assert event.volume_hint is None


# --- malformed / unknown frames: task scope §19, §24 items 18-19 --------


def test_parse_price_event_missing_symbol_rejected() -> None:
    raw = {"event": "price", "price": "100", "timestamp": 1_754_812_800}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_missing_price_rejected() -> None:
    raw = {"event": "price", "symbol": "AAPL", "timestamp": 1_754_812_800}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_invalid_numeric_price_rejected() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": "not-a-number", "timestamp": 1_754_812_800}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_non_finite_price_rejected() -> None:
    raw = {"event": "price", "symbol": "AAPL", "price": "NaN", "timestamp": 1_754_812_800}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


def test_parse_price_event_empty_symbol_rejected() -> None:
    raw = {"event": "price", "symbol": "  ", "price": "100", "timestamp": 1_754_812_800}

    with pytest.raises(MarketDataMalformedResponseError):
        parse_price_event(raw)


# --- market_state_from_quote: task scope §12 -----------------------------


def test_market_state_from_quote_true_maps_to_open() -> None:
    assert market_state_from_quote(True) is MarketState.OPEN


def test_market_state_from_quote_false_maps_to_unknown_not_closed() -> None:
    """task scope §12: a bare `False` cannot be proven to mean fully
    closed rather than an extended-hours session the boolean can't
    express — must not be guessed as `CLOSED`."""
    assert market_state_from_quote(False) is MarketState.UNKNOWN


def test_market_state_from_quote_none_maps_to_unknown() -> None:
    assert market_state_from_quote(None) is MarketState.UNKNOWN


# --- TwelveDataStreamClient: message shapes (officially confirmed) ------


class _FakeConnection:
    def __init__(self, recv_queue: list[str] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self._recv_queue = list(recv_queue or [])
        self.closed = False

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def recv(self) -> str:
        if not self._recv_queue:
            raise websockets.exceptions.ConnectionClosedOK(None, None)
        return self._recv_queue.pop(0)

    async def close(self) -> None:
        self.closed = True


def _client_with_fake_connection(
    connection: _FakeConnection | None = None,
) -> tuple[TwelveDataStreamClient, list[str]]:
    connection = connection or _FakeConnection()
    seen_urls: list[str] = []

    async def fake_connector(url: str) -> _FakeConnection:
        seen_urls.append(url)
        return connection

    client = TwelveDataStreamClient(_FAKE_API_KEY, connector=fake_connector)
    return client, seen_urls


@pytest.mark.anyio
async def test_connect_sends_api_key_as_documented_query_param() -> None:
    client, seen_urls = _client_with_fake_connection()

    await client.connect()

    assert len(seen_urls) == 1
    assert seen_urls[0] == f"wss://ws.twelvedata.com/v1/quotes/price?apikey={_FAKE_API_KEY}"


@pytest.mark.anyio
async def test_subscribe_sends_documented_action_json() -> None:
    connection = _FakeConnection()
    client, _ = _client_with_fake_connection(connection)
    await client.connect()

    await client.subscribe(["AAPL", "MSFT"])

    assert connection.sent == [{"action": "subscribe", "params": {"symbols": "AAPL,MSFT"}}]


@pytest.mark.anyio
async def test_unsubscribe_sends_documented_action_json() -> None:
    connection = _FakeConnection()
    client, _ = _client_with_fake_connection(connection)
    await client.connect()

    await client.unsubscribe(["AAPL"])

    assert connection.sent == [{"action": "unsubscribe", "params": {"symbols": "AAPL"}}]


@pytest.mark.anyio
async def test_send_heartbeat_sends_documented_action_json() -> None:
    connection = _FakeConnection()
    client, _ = _client_with_fake_connection(connection)
    await client.connect()

    await client.send_heartbeat()

    assert connection.sent == [{"action": "heartbeat"}]


def test_heartbeat_interval_matches_documented_value() -> None:
    assert HEARTBEAT_INTERVAL_SECONDS == 10.0


@pytest.mark.anyio
async def test_receive_decodes_json_frame() -> None:
    connection = _FakeConnection(recv_queue=[json.dumps({"event": "price", "symbol": "AAPL"})])
    client, _ = _client_with_fake_connection(connection)
    await client.connect()

    frame = await client.receive()

    assert frame == {"event": "price", "symbol": "AAPL"}


@pytest.mark.anyio
async def test_receive_non_json_frame_raises_malformed_error() -> None:
    connection = _FakeConnection(recv_queue=["not json at all {{{"])
    client, _ = _client_with_fake_connection(connection)
    await client.connect()

    with pytest.raises(MarketDataMalformedResponseError):
        await client.receive()


@pytest.mark.anyio
async def test_close_is_idempotent_before_connect() -> None:
    client = TwelveDataStreamClient(_FAKE_API_KEY)

    await client.close()  # must not raise


@pytest.mark.anyio
async def test_close_closes_the_underlying_connection() -> None:
    connection = _FakeConnection()
    client, _ = _client_with_fake_connection(connection)
    await client.connect()

    await client.close()

    assert connection.closed is True


# --- capability failure translation: task scope §7, §24 item 20 ---------


def _invalid_status(status_code: int) -> websockets.exceptions.InvalidStatus:
    response = http11.Response(status_code, "reason", Headers(), b"")
    return websockets.exceptions.InvalidStatus(response)


@pytest.mark.anyio
@pytest.mark.parametrize("status_code", [401, 403])
async def test_connect_translates_auth_rejection_to_capability_error(status_code: int) -> None:
    async def rejecting_connector(_url: str) -> Any:
        raise _invalid_status(status_code)

    client = TwelveDataStreamClient(_FAKE_API_KEY, connector=rejecting_connector)

    with pytest.raises(LiveProviderCapabilityError):
        await client.connect()


@pytest.mark.anyio
async def test_connect_other_http_status_is_not_treated_as_capability_error() -> None:
    """A 500 (transient provider-side error) must not be permanently
    treated as "no WebSocket access" — only 401/403 are."""

    async def failing_connector(_url: str) -> Any:
        raise _invalid_status(500)

    client = TwelveDataStreamClient(_FAKE_API_KEY, connector=failing_connector)

    with pytest.raises(websockets.exceptions.InvalidStatus):
        await client.connect()


# --- secret safety: task scope §24 item 24 --------------------------------


@pytest.mark.anyio
async def test_repr_never_contains_api_key() -> None:
    client, _ = _client_with_fake_connection()
    await client.connect()

    assert _FAKE_API_KEY not in repr(client)


def test_repr_never_contains_api_key_before_connect() -> None:
    client = TwelveDataStreamClient(_FAKE_API_KEY)

    assert _FAKE_API_KEY not in repr(client)


@pytest.mark.anyio
async def test_connect_log_message_never_contains_api_key(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = _client_with_fake_connection()

    with caplog.at_level("DEBUG"):
        await client.connect()

    for record in caplog.records:
        assert _FAKE_API_KEY not in record.getMessage()
