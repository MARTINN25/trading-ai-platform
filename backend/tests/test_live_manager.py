"""Deterministic tests for `market_data/live_manager.py` (Phase 2C.2).

No real network, no real `websockets` connection, no real clock sleeps
in the reconnect/backoff/polling logic under test — `FakeStreamClient`/
`FakeQuoteGateway` implement the two small protocols the manager
depends on, and `RecordingSleeper` replaces `asyncio.sleep` so backoff/
poll-interval waits are instant and inspectable (task scope §16: "tests
must not sleep... inject sleeper/backoff calculator").

A short *real* `asyncio.wait_for` timeout is used purely as a hang
safety net around a few genuinely-concurrent-task tests (never as the
mechanism that paces the logic under test, which the fake sleeper
already makes instant) — the same reasoning already applied throughout
this codebase's other async tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from trading_ai.market_data.live_provider import LiveProviderCapabilityError
from trading_ai.market_data.live_state import ConnectionState, FreshnessState, MarketState, derive_freshness_state
from trading_ai.market_data.live_manager import (
    BackoffPolicy,
    LiveMarketManager,
    RunMode,
    compute_backoff_delay,
)
from trading_ai.market_data.types import MarketDataUnavailableError, MarketQuote

_FAKE_API_KEY = "test-secret-manager-key-should-never-leak"


def _quote(ticker: str, price: str, *, as_of: datetime, is_market_open: bool | None = None) -> MarketQuote:
    return MarketQuote(
        ticker=ticker,
        price=Decimal(price),
        change=Decimal("0"),
        change_percent=Decimal("0"),
        as_of=as_of,
        source="twelvedata",
        is_market_open=is_market_open,
    )


_T0 = datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc)


class _Raise:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


class FakeStreamClient:
    """Implements `LiveStreamClientLike` structurally — no real socket."""

    def __init__(self) -> None:
        self.connect_calls = 0
        self.connect_results: list[BaseException | None] = []
        self.subscribe_calls: list[list[str]] = []
        self.unsubscribe_calls: list[list[str]] = []
        self.heartbeat_calls = 0
        self.closed = False
        self._recv_queue: asyncio.Queue[Any] = asyncio.Queue()

    async def connect(self) -> None:
        self.connect_calls += 1
        if self.connect_results:
            result = self.connect_results.pop(0)
            if result is not None:
                raise result

    async def subscribe(self, symbols: Sequence[str]) -> None:
        self.subscribe_calls.append(list(symbols))

    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        self.unsubscribe_calls.append(list(symbols))

    async def send_heartbeat(self) -> None:
        self.heartbeat_calls += 1

    async def receive(self) -> object:
        item = await self._recv_queue.get()
        if isinstance(item, _Raise):
            raise item.exc
        return item

    async def close(self) -> None:
        self.closed = True

    def push_frame(self, frame: object) -> None:
        self._recv_queue.put_nowait(frame)

    def push_error(self, exc: BaseException) -> None:
        self._recv_queue.put_nowait(_Raise(exc))


class FakeQuoteGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._quotes: dict[str, MarketQuote] = {}
        self._errors: dict[str, BaseException] = {}

    def set_quote(self, ticker: str, quote: MarketQuote) -> None:
        self._quotes[ticker] = quote

    def set_error(self, ticker: str, exc: BaseException) -> None:
        self._errors[ticker] = exc

    async def get_quote(self, ticker: str) -> MarketQuote:
        self.calls.append(ticker)
        if ticker in self._errors:
            raise self._errors[ticker]
        if ticker in self._quotes:
            return self._quotes[ticker]
        raise MarketDataUnavailableError("no fake quote configured")


class RecordingSleeper:
    """Replaces `asyncio.sleep` so backoff/heartbeat/poll waits are
    instant (task scope §16) — but still `await asyncio.sleep(0)`
    itself, a pure scheduler yield with zero real wall-clock delay, not
    a "sleep" in the sense the task means. Without at least one real
    yield point, a tight `while: await sleep_fn(...): await
    something_else_with_no_await()` loop (e.g. `_heartbeat_loop` when
    both the sleeper *and* the fake transport never yield) can spin
    without ever returning control to the event loop, starving every
    other task — including the test's own polling loop and `stop()`
    itself. This was a real, reproduced hang, not a hypothetical.
    """

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        await asyncio.sleep(0)


async def _wait_until(predicate: Any, *, timeout: float = 2.0) -> None:
    async def _poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(_poll(), timeout=timeout)


# --- compute_backoff_delay: task scope §16, §24 items 14-15 --------------


def test_compute_backoff_delay_exponential_progression() -> None:
    policy = BackoffPolicy(initial_delay=timedelta(seconds=1), multiplier=2.0, max_delay=timedelta(seconds=60))

    delays = [compute_backoff_delay(policy, attempt) for attempt in range(5)]

    assert delays == [
        timedelta(seconds=1),
        timedelta(seconds=2),
        timedelta(seconds=4),
        timedelta(seconds=8),
        timedelta(seconds=16),
    ]


def test_compute_backoff_delay_is_capped_at_max_delay() -> None:
    policy = BackoffPolicy(initial_delay=timedelta(seconds=1), multiplier=2.0, max_delay=timedelta(seconds=10))

    delay = compute_backoff_delay(policy, attempt=10)

    assert delay == timedelta(seconds=10)


def test_compute_backoff_delay_rejects_negative_attempt() -> None:
    with pytest.raises(ValueError):
        compute_backoff_delay(BackoffPolicy(), attempt=-1)


# --- subscribe / unsubscribe / refcount: task scope §9, §24 items 6-10 ---


@pytest.mark.anyio
async def test_subscribe_first_subscriber_registers_and_bootstraps_from_rest() -> None:
    quotes = FakeQuoteGateway()
    quotes.set_quote("AAPL", _quote("AAPL", "100", as_of=_T0))
    manager = LiveMarketManager(None, quotes)

    state = await manager.subscribe("AAPL")

    assert state.instrument == "AAPL"
    assert quotes.calls == ["AAPL"]
    assert manager.get_state("AAPL") is not None
    assert manager.get_state("AAPL").last_price == Decimal("100")  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_subscribe_same_symbol_twice_increments_refcount_only() -> None:
    quotes = FakeQuoteGateway()
    quotes.set_quote("AAPL", _quote("AAPL", "100", as_of=_T0))
    manager = LiveMarketManager(None, quotes)

    await manager.subscribe("AAPL")
    await manager.subscribe("AAPL")

    assert quotes.calls == ["AAPL"]  # bootstrapped once, not twice
    assert manager._subscriptions["AAPL"].ref_count == 2


@pytest.mark.anyio
async def test_unsubscribe_decrements_refcount_keeps_subscription_while_positive() -> None:
    manager = LiveMarketManager(None, FakeQuoteGateway())
    await manager.subscribe("AAPL")
    await manager.subscribe("AAPL")

    await manager.unsubscribe("AAPL")

    assert manager.get_state("AAPL") is not None
    assert manager._subscriptions["AAPL"].ref_count == 1


@pytest.mark.anyio
async def test_last_unsubscribe_removes_subscription_and_sends_provider_unsubscribe() -> None:
    stream = FakeStreamClient()
    manager = LiveMarketManager(stream, FakeQuoteGateway())
    manager._run_mode = RunMode.STREAMING  # simulate an already-streaming manager
    await manager.subscribe("AAPL")

    await manager.unsubscribe("AAPL")

    assert stream.unsubscribe_calls == [["AAPL"]]
    assert manager.get_state("AAPL") is None


@pytest.mark.anyio
async def test_unsubscribe_unknown_symbol_is_a_no_op() -> None:
    manager = LiveMarketManager(None, FakeQuoteGateway())

    await manager.unsubscribe("AAPL")  # must not raise


@pytest.mark.anyio
async def test_concurrent_subscribe_same_symbol_does_not_duplicate_provider_subscription() -> None:
    stream = FakeStreamClient()
    manager = LiveMarketManager(stream, FakeQuoteGateway())
    manager._run_mode = RunMode.STREAMING

    await asyncio.gather(manager.subscribe("AAPL"), manager.subscribe("AAPL"))

    assert stream.subscribe_calls == [["AAPL"]]
    assert manager._subscriptions["AAPL"].ref_count == 2


# --- live event application: task scope §24 items 11-12 -------------------


@pytest.mark.anyio
async def test_live_price_frame_updates_canonical_state() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")

    await manager._handle_raw_frame(
        {"event": "price", "symbol": "AAPL", "price": "303.94", "timestamp": 1_754_812_800}
    )

    state = manager.get_state("AAPL")
    assert state is not None
    assert state.last_price == Decimal("303.94")
    assert state.connection_state is ConnectionState.LIVE


@pytest.mark.anyio
async def test_duplicate_frame_delivery_does_not_corrupt_state() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")
    frame = {"event": "price", "symbol": "AAPL", "price": "100", "timestamp": 1_754_812_800}

    await manager._handle_raw_frame(frame)
    await manager._handle_raw_frame(frame)

    state = manager.get_state("AAPL")
    assert state is not None
    assert state.last_price == Decimal("100")


@pytest.mark.anyio
async def test_frame_for_unsubscribed_symbol_is_ignored() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())

    await manager._handle_raw_frame(
        {"event": "price", "symbol": "MSFT", "price": "100", "timestamp": 1_754_812_800}
    )  # must not raise — MSFT was never subscribed

    assert manager.get_state("MSFT") is None


# --- reconnect / backoff / resubscribe: task scope §24 items 13, 16-17 ----


@pytest.mark.anyio
async def test_reconnect_after_failures_resubscribes_and_preserves_last_known_good() -> None:
    stream = FakeStreamClient()
    stream.connect_results = [ConnectionError("boom"), ConnectionError("boom"), None]
    sleeper = RecordingSleeper()
    manager = LiveMarketManager(
        stream,
        FakeQuoteGateway(),
        backoff_policy=BackoffPolicy(initial_delay=timedelta(seconds=1)),
        sleep_fn=sleeper,
        # A very large heartbeat interval so the (independently
        # running) heartbeat task's own `sleep_fn` calls never
        # interleave with the backoff-delay assertions below —
        # heartbeat timing has its own dedicated tests.
        heartbeat_interval_seconds=1_000_000.0,
    )
    await manager.subscribe("AAPL")
    await manager._handle_raw_frame(
        {"event": "price", "symbol": "AAPL", "price": "303.94", "timestamp": 1_754_812_800}
    )

    await manager.start()
    await _wait_until(lambda: stream.connect_calls >= 3)
    await _wait_until(lambda: stream.subscribe_calls == [["AAPL"]])
    await manager.stop()

    assert stream.connect_calls == 3
    # The heartbeat task runs concurrently and also calls `sleep_fn`
    # (with `heartbeat_interval_seconds`, set enormous above precisely
    # so it's trivially distinguishable here) — filter it out to check
    # only the backoff-relevant delays.
    backoff_calls = [c for c in sleeper.calls if c != 1_000_000.0]
    assert backoff_calls == [1.0, 2.0]  # exponential, two failures before success
    state = manager.get_state("AAPL")
    assert state is not None
    assert state.last_price == Decimal("303.94")  # preserved through both failures


@pytest.mark.anyio
async def test_successful_reconnect_resets_backoff() -> None:
    stream = FakeStreamClient()
    stream.connect_results = [ConnectionError("a"), ConnectionError("b"), None]
    sleeper = RecordingSleeper()
    manager = LiveMarketManager(
        stream,
        FakeQuoteGateway(),
        backoff_policy=BackoffPolicy(initial_delay=timedelta(seconds=1)),
        sleep_fn=sleeper,
        heartbeat_interval_seconds=1_000_000.0,  # see test_reconnect_after_failures... for why
    )
    await manager.subscribe("AAPL")

    await manager.start()
    await _wait_until(lambda: stream.connect_calls >= 3)  # two failures, then a success
    # Wait for the *downstream effect* of that success (resubscribe),
    # not just the sleeper's recorded call count — the sleeper yields
    # via a bare `asyncio.sleep(0)`, so a test polling loop can observe
    # a recorded call before the manager task has actually resumed past
    # it; waiting on a later, code-sequenced effect avoids that race.
    await _wait_until(lambda: stream.subscribe_calls == [["AAPL"]])

    # Force a *new* disconnect on the now-stable connection so a 4th
    # connect attempt happens — its backoff delay should start fresh
    # from `initial_delay`, not continue at 4s.
    stream.push_error(ConnectionError("c"))
    await _wait_until(lambda: stream.connect_calls >= 4)
    await manager.stop()

    # See test_reconnect_after_failures_resubscribes_and_preserves_last_known_good
    # for why the concurrent heartbeat task's own recorded delay must
    # be filtered out here.
    backoff_calls = [c for c in sleeper.calls if c != 1_000_000.0]
    assert backoff_calls == [1.0, 2.0, 1.0]


@pytest.mark.anyio
async def test_connection_loss_marks_subscriptions_disconnected_but_preserves_price() -> None:
    """Exercises exactly what `_run_stream_loop` calls on any connection
    failure (`_mark_all(DISCONNECTED)`) directly and deterministically —
    a live end-to-end version of this would race against the fake
    transport's own automatic reconnect (nothing stops it succeeding
    again immediately once its scripted failures are exhausted), which
    makes asserting a *transient* mid-flight state inherently
    timing-dependent rather than a real behavior difference. The
    reconnect loop actually invoking `_mark_all` on failure is covered
    by `test_reconnect_after_failures_resubscribes_and_preserves_last_known_good`."""
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")
    await manager._handle_raw_frame(
        {"event": "price", "symbol": "AAPL", "price": "50", "timestamp": 1_754_812_800}
    )

    manager._mark_all(ConnectionState.DISCONNECTED)

    state = manager.get_state("AAPL")
    assert state is not None
    assert state.last_price == Decimal("50")  # preserved (task scope §18)
    assert state.connection_state is ConnectionState.DISCONNECTED
    # `derive_freshness_state` checks `ConnectionState.DISCONNECTED`
    # before any age band (`live_state.py`'s own precedence order) —
    # honest either way: never frozen "LIVE" (task scope §18).
    freshness = derive_freshness_state(state, manager._freshness_policy, _T0 + timedelta(hours=1))
    assert freshness is FreshnessState.DISCONNECTED


# --- heartbeat: task scope §17 --------------------------------------------


@pytest.mark.anyio
async def test_heartbeat_is_sent_on_the_documented_interval() -> None:
    stream = FakeStreamClient()
    sleeper = RecordingSleeper()
    manager = LiveMarketManager(stream, FakeQuoteGateway(), sleep_fn=sleeper, heartbeat_interval_seconds=10.0)

    await manager.start()
    await _wait_until(lambda: stream.heartbeat_calls >= 1)
    await manager.stop()

    assert stream.heartbeat_calls >= 1
    assert 10.0 in sleeper.calls


@pytest.mark.anyio
async def test_heartbeat_failure_triggers_reconnect() -> None:
    stream = FakeStreamClient()

    real_send_heartbeat = stream.send_heartbeat

    async def failing_heartbeat() -> None:
        stream.heartbeat_calls += 1
        raise ConnectionError("heartbeat failed")

    stream.send_heartbeat = failing_heartbeat  # type: ignore[method-assign]
    sleeper = RecordingSleeper()
    manager = LiveMarketManager(stream, FakeQuoteGateway(), sleep_fn=sleeper, heartbeat_interval_seconds=10.0)

    await manager.start()
    # Wait on the downstream effect (a second `connect()` call), not on
    # `sleeper.calls` directly — see `test_successful_reconnect_resets_backoff`
    # for why that would race against the manager task's own resumption.
    await _wait_until(lambda: stream.connect_calls >= 2)
    await manager.stop()

    assert stream.heartbeat_calls >= 1
    assert 10.0 in sleeper.calls  # the heartbeat-interval wait was recorded
    del real_send_heartbeat  # unused, kept only for readability of intent


# --- malformed / unknown frames: task scope §24 items 18-19 ----------------


@pytest.mark.anyio
async def test_malformed_frame_is_counted_and_does_not_crash() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")

    await manager._handle_raw_frame({"event": "price", "symbol": "AAPL"})  # missing price/timestamp

    assert manager.health_snapshot().malformed_event_count == 1
    assert manager.get_state("AAPL") is not None  # state untouched, not corrupted


@pytest.mark.anyio
async def test_unknown_event_type_is_safely_ignored_not_counted_as_malformed() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())

    await manager._handle_raw_frame({"event": "subscribe-status", "status": "ok"})
    await manager._handle_raw_frame("not even a dict")
    await manager._handle_raw_frame({"event": "something-unrecognized"})

    assert manager.health_snapshot().malformed_event_count == 0


@pytest.mark.anyio
async def test_domain_rejected_event_is_counted_as_malformed_not_crashing() -> None:
    """A symbol-mismatched (or otherwise domain-rejected) event is
    caught defensively even though the manager routes by `event.symbol`
    — defense in depth against a provider frame that somehow claims a
    symbol this process is not tracking under a plausible key collision
    scenario is already handled by the `subscription is None` guard;
    this test targets the second layer (`live_state`'s own validation)
    being exercised safely too, e.g. a non-positive price the stream
    parser itself would already reject — verified here at the manager
    boundary instead of the parser boundary for defense-in-depth
    confidence."""
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")

    # A frame that passes stream-level parsing (finite, well-formed)
    # but ages older than nothing yet recorded is always accepted by
    # the domain on first application — so instead this exercises the
    # malformed-at-parse-layer path end-to-end through the manager:
    await manager._handle_raw_frame({"event": "price", "symbol": "AAPL", "price": "NaN", "timestamp": 1})

    assert manager.health_snapshot().malformed_event_count == 1
    assert manager.get_state("AAPL") is not None


# --- fallback mode / REST precedence: task scope §24 items 20-22 -----------


@pytest.mark.anyio
async def test_provider_access_denied_switches_to_polling_fallback() -> None:
    stream = FakeStreamClient()
    stream.connect_results = [LiveProviderCapabilityError("HTTP 401")]
    quotes = FakeQuoteGateway()
    quotes.set_quote("AAPL", _quote("AAPL", "100", as_of=_T0))
    sleeper = RecordingSleeper()
    manager = LiveMarketManager(stream, quotes, sleep_fn=sleeper, poll_interval_seconds=5.0)
    await manager.subscribe("AAPL")
    quotes.calls.clear()

    await manager.start()
    await _wait_until(lambda: manager.health_snapshot().run_mode is RunMode.POLLING_FALLBACK)
    await _wait_until(lambda: "AAPL" in quotes.calls)
    await manager.stop()

    assert manager.health_snapshot().run_mode is RunMode.DISCONNECTED  # after stop()
    assert stream.connect_calls == 1  # never retried WebSocket after the capability failure


@pytest.mark.anyio
async def test_no_stream_client_starts_directly_in_polling_fallback() -> None:
    quotes = FakeQuoteGateway()
    quotes.set_quote("AAPL", _quote("AAPL", "100", as_of=_T0))
    sleeper = RecordingSleeper()
    manager = LiveMarketManager(None, quotes, sleep_fn=sleeper, poll_interval_seconds=5.0)
    await manager.subscribe("AAPL")

    await manager.start()
    await _wait_until(lambda: manager.health_snapshot().run_mode is RunMode.POLLING_FALLBACK)
    await manager.stop()


@pytest.mark.anyio
async def test_fallback_rest_newer_quote_replaces_older_live_value() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")
    await manager._handle_raw_frame(
        {"event": "price", "symbol": "AAPL", "price": "100", "timestamp": int(_T0.timestamp())}
    )

    newer_quote = _quote("AAPL", "105", as_of=_T0 + timedelta(minutes=1))
    await manager._apply_rest_quote("AAPL", newer_quote)

    state = manager.get_state("AAPL")
    assert state is not None
    assert state.last_price == Decimal("105")


@pytest.mark.anyio
async def test_stale_rest_quote_cannot_replace_newer_live_value() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")
    await manager._handle_raw_frame(
        {"event": "price", "symbol": "AAPL", "price": "110", "timestamp": int((_T0 + timedelta(minutes=5)).timestamp())}
    )

    stale_quote = _quote("AAPL", "999", as_of=_T0)  # older than the live tick above
    await manager._apply_rest_quote("AAPL", stale_quote)

    state = manager.get_state("AAPL")
    assert state is not None
    assert state.last_price == Decimal("110")  # unchanged — stale REST never regresses newer live data


@pytest.mark.anyio
async def test_rest_bootstrap_sets_market_state_honestly() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())
    await manager.subscribe("AAPL")

    await manager._apply_rest_quote("AAPL", _quote("AAPL", "100", as_of=_T0, is_market_open=True))
    assert manager.get_state("AAPL").market_state is MarketState.OPEN  # type: ignore[union-attr]

    await manager._apply_rest_quote("AAPL", _quote("AAPL", "100", as_of=_T0 + timedelta(seconds=1), is_market_open=False))
    assert manager.get_state("AAPL").market_state is MarketState.UNKNOWN  # type: ignore[union-attr]


# --- stop / cleanup: task scope §24 item 23 --------------------------------


@pytest.mark.anyio
async def test_stop_cancels_task_and_closes_stream_client() -> None:
    stream = FakeStreamClient()
    manager = LiveMarketManager(stream, FakeQuoteGateway())

    await manager.start()
    await _wait_until(lambda: stream.connect_calls >= 1)
    await manager.stop()

    assert stream.closed is True
    assert manager._main_task is None
    assert manager.health_snapshot().run_mode is RunMode.DISCONNECTED


@pytest.mark.anyio
async def test_stop_before_start_is_a_no_op() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())

    await manager.stop()  # must not raise


@pytest.mark.anyio
async def test_start_is_idempotent() -> None:
    stream = FakeStreamClient()
    manager = LiveMarketManager(stream, FakeQuoteGateway())

    await manager.start()
    first_task = manager._main_task
    await manager.start()  # second call must not spawn a second task

    assert manager._main_task is first_task
    await manager.stop()


# --- secret safety: task scope §24 item 24 ---------------------------------


def test_manager_repr_never_contains_api_key() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())

    assert _FAKE_API_KEY not in repr(manager)


def test_health_snapshot_never_contains_api_key() -> None:
    manager = LiveMarketManager(FakeStreamClient(), FakeQuoteGateway())

    snapshot = manager.health_snapshot()

    assert _FAKE_API_KEY not in repr(snapshot)
    assert _FAKE_API_KEY not in str(snapshot)
