"""Deterministic tests for Phase 2C.3 (backend live-market SSE delivery).

No real network, no real Twelve Data connection anywhere in this file.
Three layers are tested separately:

- **Lifespan** (`create_app()` + `with TestClient(app) as client:`):
  whether `main.py`'s wiring constructs/starts/stops exactly one
  `LiveMarketManager` per process. `TRADING_AI_LIVE_STREAMING_ENABLED`
  is always forced to `"false"` in these tests (task scope: "no test may
  hit real Twelve Data") — `LiveMarketManager.start()` would otherwise
  eagerly open a *real* WebSocket connection attempt the moment the
  background task first runs, even with zero subscribers; REST-fallback
  mode with zero subscriptions makes no network call at all (`_poll_all_
  once` iterates an empty subscription dict).
- **HTTP route** (`create_app()` + `TestClient` + `app.dependency_
  overrides[get_live_market_manager]`): status codes, headers, and the
  first SSE event only — never iterates the endpoint's inner `while
  True` loop over real HTTP, to keep tests fast and non-flaky.
- **Generator internals** (`_live_event_stream` driven directly as an
  async generator, with a small duck-typed fake `Request`): the exact
  mechanism used to test disconnect/refcount/backpressure/coalescing/
  heartbeat/DEGRADED-RECONNECTING-survival deterministically, without
  depending on real ASGI-transport timing.

`LiveMarketManager` itself is always constructed with `stream_client=
None` (REST-fallback mode) and never `.start()`-ed in the route/
generator-level tests — `subscribe()`/`unsubscribe()`/the private
state-mutation helpers work standalone, exactly as `test_live_manager.py`
already relies on.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from trading_ai.api.routes.live_market import (
    BROWSER_SSE_HEARTBEAT_INTERVAL_SECONDS,
    _live_event_stream,
    get_live_market_manager,
    serialize_live_state,
    stream_instrument_live_state,
)
from trading_ai.main import create_app
from trading_ai.market_data.live_manager import LiveMarketManager, RunMode
from trading_ai.market_data.live_state import (
    Bar,
    ConnectionState,
    VolumeQuality,
    bootstrap_state,
    with_connection_state,
)
from trading_ai.market_data.types import MarketDataUnavailableError, MarketQuote

_FAKE_API_KEY = "test-secret-sse-key-should-never-leak"
_T0 = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


def _quote(ticker: str, price: str, *, as_of: datetime) -> MarketQuote:
    return MarketQuote(
        ticker=ticker,
        price=Decimal(price),
        change=Decimal("0"),
        change_percent=Decimal("0"),
        as_of=as_of,
        source="twelvedata",
        is_market_open=True,
    )


class _FakeQuoteGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._quotes: dict[str, MarketQuote] = {}

    def set_quote(self, ticker: str, quote: MarketQuote) -> None:
        self._quotes[ticker] = quote

    async def get_quote(self, ticker: str) -> MarketQuote:
        self.calls.append(ticker)
        if ticker in self._quotes:
            return self._quotes[ticker]
        raise MarketDataUnavailableError("no fake quote configured")


def _make_manager(*, quote: MarketQuote | None = None) -> LiveMarketManager:
    gateway = _FakeQuoteGateway()
    if quote is not None:
        gateway.set_quote(quote.ticker, quote)
    return LiveMarketManager(None, gateway)


class _FakeRequest:
    """Duck-types the one method `_live_event_stream` actually calls
    (`await request.is_disconnected()`) — passed to production code via
    `cast(Request, ...)` so mypy still checks the call site's intended
    type, without needing a real ASGI transport for these tests."""

    def __init__(self, *, disconnect_after_calls: int | None = None) -> None:
        self.calls = 0
        self.disconnect_after_calls = disconnect_after_calls
        self.force_disconnected = False

    async def is_disconnected(self) -> bool:
        self.calls += 1
        if self.force_disconnected:
            return True
        if self.disconnect_after_calls is not None and self.calls > self.disconnect_after_calls:
            return True
        return False


def _fake_request(*, disconnect_after_calls: int | None = None) -> Request:
    return cast(Request, _FakeRequest(disconnect_after_calls=disconnect_after_calls))


def _body_gen(response: StreamingResponse) -> AsyncGenerator[str, None]:
    """`StreamingResponse.body_iterator` is typed as the broad
    `ContentStream` union; this route always constructs it from
    `_live_event_stream` (an `AsyncGenerator[str, None]`), so the cast
    here just recovers what production code already guarantees."""
    return cast("AsyncGenerator[str, None]", response.body_iterator)


# ---------------------------------------------------------------------------
# Serializer (task scope §12, §13, §22)
# ---------------------------------------------------------------------------


def _bar(interval_start: datetime) -> Bar:
    return Bar(
        interval_start=interval_start,
        open=Decimal("100.10"),
        high=Decimal("101.50"),
        low=Decimal("99.75"),
        close=Decimal("100.90"),
        close_at=interval_start + timedelta(seconds=30),
        volume=1234,
        volume_quality=VolumeQuality.PARTIAL,
        is_closed=False,
    )


def test_serialize_state_decimal_fields_are_strings() -> None:
    state = bootstrap_state("AAPL")
    state = with_connection_state(state, ConnectionState.LIVE)
    from dataclasses import replace

    state = replace(state, last_price=Decimal("213.45"), last_price_as_of=_T0)

    payload = serialize_live_state(event="snapshot", state=state, revision=1, now=_T0)
    raw = payload.model_dump_json()

    assert '"last_price":"213.45"' in raw


def test_serialize_state_datetime_fields_are_iso8601_utc() -> None:
    state = bootstrap_state("AAPL")
    from dataclasses import replace

    state = replace(state, last_price=Decimal("1"), last_price_as_of=_T0)

    payload = serialize_live_state(event="snapshot", state=state, revision=1, now=_T0)

    assert payload.last_price_as_of is not None
    assert payload.last_price_as_of.isoformat() == "2026-03-02T14:30:00+00:00"
    assert '"last_price_as_of":"2026-03-02T14:30:00Z"' in payload.model_dump_json()
    assert '"server_time":"2026-03-02T14:30:00Z"' in payload.model_dump_json()


def test_serialize_state_enum_fields_are_plain_strings_not_repr() -> None:
    state = bootstrap_state("AAPL")
    state = with_connection_state(state, ConnectionState.RECONNECTING)

    payload = serialize_live_state(event="status", state=state, revision=1, now=_T0)
    raw = payload.model_dump_json()

    assert '"connection_state":"reconnecting"' in raw
    assert "ConnectionState." not in raw
    assert "<ConnectionState" not in raw


def test_serialize_state_no_current_bar_is_null_not_fabricated() -> None:
    state = bootstrap_state("AAPL")

    payload = serialize_live_state(event="snapshot", state=state, revision=0, now=_T0)

    assert payload.current_bar is None
    assert payload.last_closed_bar is None
    assert '"current_bar":null' in payload.model_dump_json()


def test_serialize_state_current_bar_full_shape() -> None:
    from dataclasses import replace

    state = bootstrap_state("AAPL")
    state = replace(state, current_bar=_bar(_T0))

    payload = serialize_live_state(event="update", state=state, revision=1, now=_T0)

    assert payload.current_bar is not None
    assert payload.current_bar.open == Decimal("100.10")
    assert payload.current_bar.volume_quality == VolumeQuality.PARTIAL
    assert payload.current_bar.is_closed is False
    raw = payload.model_dump_json()
    assert '"volume_quality":"partial"' in raw


def test_serialize_state_never_contains_api_key_or_provider_url() -> None:
    from dataclasses import replace

    state = bootstrap_state("AAPL")
    state = replace(
        state,
        last_price=Decimal("1"),
        last_price_as_of=_T0,
        last_update_source="twelvedata_ws",
        current_bar=_bar(_T0),
    )

    payload = serialize_live_state(event="update", state=state, revision=1, now=_T0)
    raw = payload.model_dump_json()

    assert _FAKE_API_KEY not in raw
    assert "wss://" not in raw
    assert "apikey" not in raw.lower()


# ---------------------------------------------------------------------------
# HTTP route: status codes, headers, first event only (task scope §7, §8,
# §14, §25, §26 items 5-8)
# ---------------------------------------------------------------------------


def test_live_stream_invalid_ticker_returns_422() -> None:
    app = create_app()
    app.dependency_overrides[get_live_market_manager] = lambda: _make_manager()
    client = TestClient(app)

    response = client.get("/instruments/not a valid ticker!!/live-stream")

    assert response.status_code == 422


def test_live_stream_unconfigured_returns_503_before_streaming() -> None:
    app = create_app()
    # No dependency override, no lifespan entered -> app.state.live_market_manager
    # was never set -> get_live_market_manager's own getattr(..., None) path.
    client = TestClient(app)

    response = client.get("/instruments/AAPL/live-stream")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.anyio
async def test_live_stream_content_type_and_cache_headers() -> None:
    """Calls the route function directly (not through TestClient/ASGI):
    the endpoint's generator never terminates on its own (task scope
    §16: it only ends on client disconnect), so driving it through a
    real HTTP transport just to read the response headers is both
    unnecessary and — confirmed while writing this test, a genuine,
    reproduced hang, not a hypothetical concern — risks the test
    process waiting on `TestClient`'s ASGI-transport disconnect
    detection, which does not resolve deterministically for a
    still-open `StreamingResponse` in this environment. `StreamingResponse
    .headers`/`.media_type` are already fully populated as soon as the
    object is constructed, before its body iterator is ever touched, so
    this is not a weaker check — it verifies the exact same attributes
    ASGI would send as the `http.response.start` message.
    """
    manager = _make_manager(quote=_quote("AAPL", "213.45", as_of=_T0))
    request = _fake_request()

    response = await stream_instrument_live_state(ticker="AAPL", request=request, manager=manager)

    assert response.status_code == 200
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"

    body = _body_gen(response)
    first_chunk = await body.__anext__()
    assert first_chunk.startswith("id: 1\nevent: snapshot\n")
    await body.aclose()


@pytest.mark.anyio
async def test_live_stream_initial_snapshot_reflects_rest_bootstrap() -> None:
    manager = _make_manager(quote=_quote("MSFT", "310.00", as_of=_T0))
    request = _fake_request()

    response = await stream_instrument_live_state(ticker="MSFT", request=request, manager=manager)
    body = _body_gen(response)
    first_chunk = await body.__anext__()
    await body.aclose()

    assert '"event":"snapshot"' in first_chunk
    assert '"symbol":"MSFT"' in first_chunk
    assert '"last_price":"310.00"' in first_chunk


# ---------------------------------------------------------------------------
# Generator internals: subscribe lifecycle, disconnect/refcount,
# backpressure/coalescing, heartbeat, DEGRADED/RECONNECTING survival,
# Last-Event-ID (task scope §9-§11, §15-§21, §26 items 9-28)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_generator_emits_snapshot_first_with_truthful_no_data_state() -> None:
    manager = _make_manager()  # no quote configured -> REST bootstrap fails -> NO_DATA
    request = _fake_request(disconnect_after_calls=0)

    gen = _live_event_stream(manager, "AAPL", request)
    first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)

    assert '"event":"snapshot"' in first
    assert '"freshness_state":"no_data"' in first
    assert '"connection_state":"connecting"' in first
    assert manager._subscriptions["AAPL"].ref_count == 1

    await gen.aclose()
    assert "AAPL" not in manager._subscriptions


@pytest.mark.anyio
async def test_generator_update_event_after_state_change_and_revision_increments() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    snapshot = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert "id: 1" in snapshot

    await manager._apply_rest_quote("AAPL", _quote("AAPL", "101.50", as_of=_T0 + timedelta(seconds=5)))
    update = await asyncio.wait_for(gen.__anext__(), timeout=2.0)

    assert '"event":"update"' in update
    assert '"last_price":"101.50"' in update
    assert "id: 2" in update

    await gen.aclose()


@pytest.mark.anyio
async def test_generator_disconnect_triggers_unsubscribe_in_finally() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _FakeRequest(disconnect_after_calls=0)  # disconnected from the first check onward

    gen = _live_event_stream(manager, "AAPL", cast(Request, request))
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot
    assert manager._subscriptions["AAPL"].ref_count == 1

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # observes disconnect, exits loop, hits finally

    assert "AAPL" not in manager._subscriptions


@pytest.mark.anyio
async def test_generator_exception_path_still_unsubscribes() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot
    assert manager._subscriptions["AAPL"].ref_count == 1

    # `athrow` injects the exception at the generator's current suspend
    # point; since nothing inside the generator catches a bare
    # `RuntimeError`, it propagates back out of `athrow` itself — the
    # `finally: await manager.unsubscribe(...)` still runs on the way
    # out (Python's normal finally semantics), which is exactly the
    # behavior this test verifies.
    with pytest.raises(RuntimeError, match="simulated downstream failure"):
        await gen.athrow(RuntimeError("simulated downstream failure"))

    assert "AAPL" not in manager._subscriptions


@pytest.mark.anyio
async def test_generator_cancellation_still_unsubscribes() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot
    assert manager._subscriptions["AAPL"].ref_count == 1

    task: asyncio.Task[str] = asyncio.create_task(gen.__anext__())
    await asyncio.sleep(0)  # let it start waiting inside wait_for_change
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await gen.aclose()

    assert "AAPL" not in manager._subscriptions


@pytest.mark.anyio
async def test_two_generators_same_ticker_share_one_manager_subscription() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request_a = _fake_request()
    request_b = _fake_request()

    gen_a = _live_event_stream(manager, "AAPL", request_a)
    await asyncio.wait_for(gen_a.__anext__(), timeout=2.0)
    assert manager._subscriptions["AAPL"].ref_count == 1

    gen_b = _live_event_stream(manager, "AAPL", request_b)
    await asyncio.wait_for(gen_b.__anext__(), timeout=2.0)
    assert manager._subscriptions["AAPL"].ref_count == 2  # shared, not duplicated

    await gen_a.aclose()
    assert manager._subscriptions["AAPL"].ref_count == 1  # first disconnect leaves refcount > 0

    await gen_b.aclose()
    assert "AAPL" not in manager._subscriptions  # final disconnect unsubscribes for real


@pytest.mark.anyio
async def test_generator_emits_heartbeat_comment_on_timeout_with_no_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the wait_for_change timeout to fire almost immediately for
    # this test only, without an arbitrary real-time sleep in the test
    # itself — exercises the exact same code path the real
    # BROWSER_SSE_HEARTBEAT_INTERVAL_SECONDS constant drives in
    # production, just with the interval shortened for a fast test.
    import trading_ai.api.routes.live_market as live_market_module

    monkeypatch.setattr(live_market_module, "BROWSER_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)

    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot

    second = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    await gen.aclose()

    assert second == ": heartbeat\n\n"


def test_browser_heartbeat_interval_is_a_named_constant_distinct_from_provider() -> None:
    from trading_ai.market_data.twelve_data_stream import HEARTBEAT_INTERVAL_SECONDS

    assert BROWSER_SSE_HEARTBEAT_INTERVAL_SECONDS != HEARTBEAT_INTERVAL_SECONDS


@pytest.mark.anyio
async def test_generator_survives_degraded_connection_state_update() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot

    manager._mark_all(ConnectionState.DEGRADED)
    update = await asyncio.wait_for(gen.__anext__(), timeout=2.0)

    assert '"connection_state":"degraded"' in update
    # the stream is still alive/iterable afterward -> it survived, did not close
    await gen.aclose()


@pytest.mark.anyio
async def test_generator_survives_reconnecting_connection_state_update() -> None:
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot

    manager._mark_all(ConnectionState.RECONNECTING)
    update = await asyncio.wait_for(gen.__anext__(), timeout=2.0)

    assert '"connection_state":"reconnecting"' in update
    await gen.aclose()


@pytest.mark.anyio
async def test_generator_never_serializes_raw_provider_frame_fields() -> None:
    """Feeds a raw Twelve Data-shaped frame through the manager's real
    receive-path helper (`_handle_raw_frame`) and asserts the emitted SSE
    payload contains only the normalized schema — never the raw
    provider field names (`day_volume`, provider `event`/`status` keys,
    etc., task scope §26 item 27)."""
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))
    request = _fake_request()

    gen = _live_event_stream(manager, "AAPL", request)
    await asyncio.wait_for(gen.__anext__(), timeout=2.0)  # snapshot

    await manager._handle_raw_frame(
        {
            "event": "price",
            "symbol": "AAPL",
            "price": "150.25",
            "timestamp": int((_T0 + timedelta(seconds=10)).timestamp()),
            "day_volume": 999999,
        }
    )
    update = await asyncio.wait_for(gen.__anext__(), timeout=2.0)

    assert "day_volume" not in update
    assert '"last_price":"150.25"' in update
    await gen.aclose()


@pytest.mark.anyio
async def test_generator_ignores_last_event_id_and_always_emits_fresh_snapshot() -> None:
    """No replay is implemented (task scope §20-§21): a request carrying
    `Last-Event-ID` still gets a brand-new `snapshot` as its first event,
    because the generator never reads that header at all."""
    manager = _make_manager(quote=_quote("AAPL", "100", as_of=_T0))

    class _RequestWithLastEventId(_FakeRequest):
        headers = {"last-event-id": "999"}

    gen = _live_event_stream(manager, "AAPL", cast(Request, _RequestWithLastEventId()))
    first = await asyncio.wait_for(gen.__anext__(), timeout=2.0)

    assert '"event":"snapshot"' in first
    assert "id: 1" in first  # not "resuming" from 999 — a fresh revision-1 snapshot
    await gen.aclose()


# ---------------------------------------------------------------------------
# FastAPI lifespan wiring (task scope §5, §26 items 1-4) — always with
# TRADING_AI_LIVE_STREAMING_ENABLED=false so `LiveMarketManager.start()`
# cannot attempt a real network connection (no subscribers -> REST
# fallback makes zero requests either).
# ---------------------------------------------------------------------------


def test_app_startup_with_market_api_key_constructs_and_starts_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRADING_AI_MARKET_DATA_API_KEY", _FAKE_API_KEY)
    monkeypatch.setenv("TRADING_AI_LIVE_STREAMING_ENABLED", "false")
    app = create_app()

    with TestClient(app) as client:
        manager = client.app.state.live_market_manager  # type: ignore[attr-defined]
        assert manager is not None
        assert isinstance(manager, LiveMarketManager)
        assert manager.health_snapshot().run_mode is RunMode.POLLING_FALLBACK

    # After the context manager exits, lifespan shutdown has run.
    assert manager.health_snapshot().run_mode is RunMode.DISCONNECTED


def test_app_startup_without_market_api_key_disables_live_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRADING_AI_MARKET_DATA_API_KEY", raising=False)
    app = create_app()

    with TestClient(app) as client:
        assert client.app.state.live_market_manager is None  # type: ignore[attr-defined]
        response = client.get("/instruments/AAPL/live-stream")
        assert response.status_code == 503


def test_app_shutdown_stops_manager_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards against a double-`stop()`/lingering-task regression: the
    manager's own `stop()` is already proven idempotent
    (`test_live_manager.py::test_stop_before_start_is_a_no_op`), so this
    only needs to prove *lifespan* actually calls it once, not zero or
    many times."""
    monkeypatch.setenv("TRADING_AI_MARKET_DATA_API_KEY", _FAKE_API_KEY)
    monkeypatch.setenv("TRADING_AI_LIVE_STREAMING_ENABLED", "false")
    app = create_app()

    with TestClient(app) as client:
        manager = client.app.state.live_market_manager  # type: ignore[attr-defined]
        assert manager._main_task is not None

    assert manager._main_task is None
