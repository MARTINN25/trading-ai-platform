"""Process-local live-market connection manager (Phase 2C.2).

Owns exactly one shared provider connection per backend process (task
scope §5, §8: "do not create one provider WebSocket per symbol... per
browser/user"), a symbol subscription registry with reference counts
(task scope §9), and one in-memory `market_data.live_state
.InstrumentLiveState` per subscribed symbol. Depends only on
`live_provider.LiveStreamClientLike` (never on `TwelveDataStreamClient`
concretely, task scope §20) and on a small REST quote protocol (reused,
not duplicated, from the existing `TwelveDataGateway`, task scope §14).

Wired into `main.py`'s FastAPI lifespan as of Phase 2C.3 — one instance
per process, constructed in `app.state.live_market_manager`, the same
optional-feature pattern already used for the other three provider
gateways there. `get_state_with_revision`/`wait_for_change` (Phase 2C.3,
task scope §10/§19) are the observer/subscriber mechanism the SSE route
(`api/routes/live_market.py`) uses to await state changes instead of
polling `get_state()` in a tight loop; both live here, not in
`live_state.py` (task scope §19: revision is a manager-level delivery
concept, not a domain concept).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol

from trading_ai.market_data.live_provider import (
    LiveProviderCapabilityError,
    LiveStreamClientLike,
)
from trading_ai.market_data.live_state import (
    DEFAULT_FRESHNESS_POLICY,
    ConnectionState,
    FreshnessPolicy,
    InstrumentLiveState,
    IntervalPolicy,
    PriceUpdateEvent,
    UpdateKind,
    apply_authoritative_snapshot,
    apply_price_update,
    bootstrap_state,
    with_connection_state,
    with_market_state,
)
from trading_ai.market_data.twelve_data_stream import (
    HEARTBEAT_INTERVAL_SECONDS,
    FrameKind,
    classify_frame,
    market_state_from_quote,
    parse_price_event,
)
from trading_ai.market_data.types import MarketDataError, MarketDataMalformedResponseError, MarketQuote
from trading_ai.watchlist.domain import normalize_ticker

logger = logging.getLogger(__name__)

# The current 1D chart's own intraday granularity (`gateway.py`'s
# `_PERIOD_PROVIDER_PARAMS[InstrumentHistoryPeriod.ONE_DAY]`) — task
# scope §13: "prefer one explicit live aggregation interval matching
# current 1D chart intraday use" rather than inventing a new
# granularity or supporting multiple live timeframes in this slice.
# Epoch-anchored (the `IntervalPolicy` default) — exact exchange-session
# alignment remains unresolved and is left to later REST reconciliation
# (`apply_authoritative_closed_bar`, not implemented by this manager
# yet), exactly as the task permits.
DEFAULT_LIVE_INTERVAL_POLICY = IntervalPolicy(duration=timedelta(minutes=5))


class RunMode(str, Enum):
    """Process-wide live-data capability mode (task scope §7) —
    deliberately distinct from the per-symbol `live_state
    .ConnectionState`: this describes whether the *manager* currently
    has a working live-data path at all, which in turn determines what
    `ConnectionState` this manager applies to every subscribed symbol.
    """

    STREAMING = "streaming"
    POLLING_FALLBACK = "polling_fallback"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True)
class BackoffPolicy:
    """Explicit, documented reconnect policy (task scope §16) — no
    magic constant scattered inline. Same "policy object, not hardcoded
    thresholds" convention `live_state.FreshnessPolicy`/`IntervalPolicy`
    already established.
    """

    initial_delay: timedelta = timedelta(seconds=1)
    multiplier: float = 2.0
    max_delay: timedelta = timedelta(seconds=60)


def compute_backoff_delay(policy: BackoffPolicy, attempt: int) -> timedelta:
    """Pure, deterministic exponential backoff, capped at `max_delay` —
    no jitter (task scope §16 lists jitter as conditional: "if project
    test style allows deterministic injection"; this manager's single
    process talking to one provider connection has no "thundering herd"
    of independent clients to de-synchronize, so jitter was evaluated
    and omitted as not genuinely needed — the simplest correct model,
    same principle already applied in `live_state.py`'s corrective
    review). `attempt` is 0-indexed (0 = the delay before the first
    retry). Tests exercise this function directly — no real sleep
    needed (task scope §16: "tests must not sleep").
    """
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    raw_seconds = policy.initial_delay.total_seconds() * (policy.multiplier**attempt)
    capped_seconds = min(raw_seconds, policy.max_delay.total_seconds())
    return timedelta(seconds=capped_seconds)


class _QuoteGatewayLike(Protocol):
    """The one REST capability this manager needs — satisfied
    structurally by the existing `TwelveDataGateway` as-is (task scope
    §14: "reuse existing REST quote/history integrations... do not
    duplicate the existing Twelve Data REST gateway"), no changes to
    that class required beyond the additive `MarketQuote.is_market_open`
    field already added for this task.
    """

    async def get_quote(self, ticker: str) -> MarketQuote: ...


@dataclass(slots=True)
class _Subscription:
    ref_count: int
    state: InstrumentLiveState
    # Phase 2C.3 (SSE delivery, task scope §10/§19): a monotonically
    # increasing per-symbol revision plus a replaceable `asyncio.Event`
    # is the smallest provider-agnostic observer mechanism that lets an
    # SSE (or any future) consumer *await* the next change instead of
    # polling `get_state()` in a tight loop. Deliberately not part of
    # `InstrumentLiveState`/`live_state.py` (task scope §10/§19: "do not
    # put UI-specific revision semantics in live_state.py") — this is a
    # manager-level delivery concept, not a domain concept. `changed` is
    # replaced (not `.clear()`-ed) on every bump so that concurrently
    # waiting consumers never race a clear() against a fresh waiter that
    # arrived between the bump and the clear.
    revision: int = 0
    changed: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True, slots=True)
class ManagerHealth:
    """Observability snapshot (task scope §23) — every field here is
    safe to log or expose as-is; no secrets, no raw provider payloads."""

    run_mode: RunMode
    connected_at: datetime | None
    last_message_at: datetime | None
    reconnect_count: int
    malformed_event_count: int
    active_subscriptions: int


def _quote_to_snapshot_event(quote: MarketQuote) -> PriceUpdateEvent:
    """`MarketQuote` is already provider-neutral (its own docstring:
    mirrors the `llm_gateway` isolation pattern) — this conversion
    needs no Twelve-Data-specific knowledge and belongs here, not in
    `twelve_data_stream.py`."""
    return PriceUpdateEvent(
        symbol=quote.ticker,
        price=quote.price,
        timestamp=quote.as_of,
        source="twelvedata_rest",
        kind=UpdateKind.AUTHORITATIVE_SNAPSHOT,
        volume_hint=None,
    )


class LiveMarketManager:
    """Public surface deliberately small (task scope §25/§8):
    `subscribe`/`unsubscribe`/`get_state`/`start`/`stop`/
    `health_snapshot`. Everything else is a private implementation
    detail.
    """

    def __init__(
        self,
        stream_client: LiveStreamClientLike | None,
        quote_gateway: _QuoteGatewayLike,
        *,
        interval_policy: IntervalPolicy = DEFAULT_LIVE_INTERVAL_POLICY,
        freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
        backoff_policy: BackoffPolicy = BackoffPolicy(),
        poll_interval_seconds: float = 15.0,
        heartbeat_interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        # `stream_client=None` is a legitimate, explicit input (task
        # scope §6/§7) — e.g. `TRADING_AI_LIVE_STREAMING_ENABLED=false`,
        # or no provider stream client constructed at all for this
        # environment — not a capability probed at runtime by guessing.
        self._stream_client = stream_client
        self._quote_gateway = quote_gateway
        self._interval_policy = interval_policy
        self._freshness_policy = freshness_policy
        self._backoff_policy = backoff_policy
        self._poll_interval_seconds = poll_interval_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._sleep = sleep_fn
        self._clock = clock

        self._lock = asyncio.Lock()
        self._subscriptions: dict[str, _Subscription] = {}

        self._run_mode = RunMode.DISCONNECTED
        self._backoff_attempt = 0
        self._reconnect_count = 0
        self._connected_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._malformed_event_count = 0

        self._main_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    # -- public surface -----------------------------------------------

    async def start(self) -> None:
        if self._main_task is not None:
            return
        self._stop_event = asyncio.Event()
        if self._stream_client is not None:
            self._main_task = asyncio.create_task(self._run_stream_loop())
        else:
            self._run_mode = RunMode.POLLING_FALLBACK
            self._main_task = asyncio.create_task(self._run_poll_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._main_task
        self._main_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._stream_client is not None:
            await self._stream_client.close()
        self._run_mode = RunMode.DISCONNECTED

    async def subscribe(self, symbol: str) -> InstrumentLiveState:
        ticker = normalize_ticker(symbol)
        is_new = False
        async with self._lock:
            existing = self._subscriptions.get(ticker)
            if existing is not None:
                existing.ref_count += 1
                state = existing.state
            else:
                state = bootstrap_state(ticker)
                self._subscriptions[ticker] = _Subscription(ref_count=1, state=state)
                is_new = True

        if is_new:
            # REST bootstrap outside the lock (network I/O) — task
            # scope §14.A, "bootstrap last-known-good price from REST
            # quote". A failure here is not fatal to subscribe() —
            # the symbol simply starts as NO_DATA until the next
            # successful update (live tick or poll cycle).
            await self._bootstrap_from_rest(ticker)
            if self._run_mode is RunMode.STREAMING and self._stream_client is not None:
                try:
                    await self._stream_client.subscribe([ticker])
                except Exception:
                    logger.warning(
                        "live_manager operation=subscribe symbol=%s status=provider_send_failed",
                        ticker,
                    )
                    # Not fatal: the next reconnect cycle resubscribes
                    # every currently-registered symbol from scratch
                    # (task scope §16: "resubscribe after reconnect").

        async with self._lock:
            return self._subscriptions[ticker].state

    async def unsubscribe(self, symbol: str) -> None:
        ticker = normalize_ticker(symbol)
        should_unsubscribe_provider = False
        async with self._lock:
            subscription = self._subscriptions.get(ticker)
            if subscription is None:
                return
            subscription.ref_count -= 1
            if subscription.ref_count <= 0:
                del self._subscriptions[ticker]
                should_unsubscribe_provider = True

        if should_unsubscribe_provider and self._run_mode is RunMode.STREAMING and self._stream_client is not None:
            try:
                await self._stream_client.unsubscribe([ticker])
            except Exception:
                logger.warning(
                    "live_manager operation=unsubscribe symbol=%s status=provider_send_failed",
                    ticker,
                )

    def get_state(self, symbol: str) -> InstrumentLiveState | None:
        ticker = normalize_ticker(symbol)
        subscription = self._subscriptions.get(ticker)
        return subscription.state if subscription is not None else None

    def get_state_with_revision(self, symbol: str) -> tuple[InstrumentLiveState, int] | None:
        """Current state plus its monotonic revision (task scope §19) —
        the building block an SSE (or any future) consumer uses for an
        initial snapshot and to later ask `wait_for_change` "tell me
        when this is no longer true"."""
        ticker = normalize_ticker(symbol)
        subscription = self._subscriptions.get(ticker)
        if subscription is None:
            return None
        return subscription.state, subscription.revision

    async def wait_for_change(
        self, symbol: str, since_revision: int, *, timeout: float | None = None
    ) -> tuple[InstrumentLiveState, int] | None:
        """Block until `symbol`'s revision differs from `since_revision`,
        or `timeout` elapses first (task scope §10, §18, §11).

        Returns the *latest* state/revision as soon as they differ —
        never an intermediate one: if several mutations land while
        nobody is waiting, or while a slow consumer is still handling
        the previous result, the very next call already observes the
        newest revision and transparently skips everything in between.
        This is the whole backpressure/coalescing story for this task
        (§11, §18) — there is no per-consumer queue to bound or overflow,
        because "latest revision wins" already caps memory at one state
        object per symbol regardless of how many updates happened or how
        many consumers are subscribed.

        Returns `None` on timeout, or if `symbol` is no longer
        subscribed by anyone (a benign race with a concurrent
        `unsubscribe` — never an error).

        No tight polling loop (task scope §10): suspends on an
        `asyncio.Event` and is only woken by an actual state mutation
        (`_set_state`) or the timeout — never a fixed-interval `sleep`.
        """
        ticker = normalize_ticker(symbol)
        while True:
            async with self._lock:
                subscription = self._subscriptions.get(ticker)
                if subscription is None:
                    return None
                if subscription.revision != since_revision:
                    return subscription.state, subscription.revision
                event = subscription.changed
            if timeout is not None:
                try:
                    await asyncio.wait_for(event.wait(), timeout=timeout)
                except TimeoutError:
                    return None
            else:
                await event.wait()

    def health_snapshot(self) -> ManagerHealth:
        return ManagerHealth(
            run_mode=self._run_mode,
            connected_at=self._connected_at,
            last_message_at=self._last_message_at,
            reconnect_count=self._reconnect_count,
            malformed_event_count=self._malformed_event_count,
            active_subscriptions=len(self._subscriptions),
        )

    def __repr__(self) -> str:
        # No API key is ever held by this class (only the stream
        # client holds it) — explicit override for the same reason as
        # `TwelveDataStreamClient.__repr__` (task scope §24, item 24).
        return (
            f"LiveMarketManager(run_mode={self._run_mode.value}, "
            f"active_subscriptions={len(self._subscriptions)})"
        )

    # -- REST bootstrap / fallback polling ------------------------------

    async def _bootstrap_from_rest(self, ticker: str) -> None:
        try:
            quote = await self._quote_gateway.get_quote(ticker)
        except MarketDataError:
            logger.info(
                "live_manager operation=bootstrap symbol=%s status=rest_unavailable", ticker
            )
            return
        await self._apply_rest_quote(ticker, quote)

    async def _apply_rest_quote(self, ticker: str, quote: MarketQuote) -> None:
        event = _quote_to_snapshot_event(quote)
        market_state = market_state_from_quote(quote.is_market_open)
        async with self._lock:
            subscription = self._subscriptions.get(ticker)
            if subscription is None:
                return  # unsubscribed while the REST call was in flight
            state = apply_authoritative_snapshot(subscription.state, event)
            state = with_market_state(state, market_state)
            self._set_state(subscription, state)

    async def _run_poll_loop(self) -> None:
        self._run_mode = RunMode.POLLING_FALLBACK
        while not self._stop_event.is_set():
            await self._poll_all_once()
            self._mark_all(ConnectionState.DEGRADED)
            await self._sleep(self._poll_interval_seconds)

    async def _poll_all_once(self) -> None:
        async with self._lock:
            tickers = list(self._subscriptions.keys())
        # Sequential, not concurrent (task scope §15: "no aggressive
        # polling", "one backend manager owns fallback polling per
        # symbol" — a simple bounded-rate loop, not a burst of
        # simultaneous requests).
        for ticker in tickers:
            await self._bootstrap_from_rest(ticker)

    # -- streaming loop / reconnect --------------------------------------

    async def _run_stream_loop(self) -> None:
        assert self._stream_client is not None
        while not self._stop_event.is_set():
            try:
                await self._run_one_connection()
            except asyncio.CancelledError:
                raise
            except LiveProviderCapabilityError as exc:
                # Structural failure (task scope §7) — stop retrying
                # WebSocket entirely for this manager instance and
                # fall back to REST polling instead.
                logger.warning(
                    "live_manager operation=stream_loop status=capability_unavailable reason=%s",
                    exc.reason,
                )
                self._mark_all(ConnectionState.DISCONNECTED)
                await self._run_poll_loop()
                return
            except Exception as exc:
                logger.warning(
                    "live_manager operation=stream_loop status=connection_error error_type=%s",
                    type(exc).__name__,
                )

            self._mark_all(ConnectionState.DISCONNECTED)
            if self._stop_event.is_set():
                break
            self._reconnect_count += 1
            delay = compute_backoff_delay(self._backoff_policy, self._backoff_attempt)
            self._run_mode = RunMode.DEGRADED
            await self._sleep(delay.total_seconds())
            self._backoff_attempt += 1
        self._run_mode = RunMode.DISCONNECTED

    async def _run_one_connection(self) -> None:
        assert self._stream_client is not None
        await self._stream_client.connect()
        self._backoff_attempt = 0  # a connection was established — reset backoff (task scope §16)
        self._run_mode = RunMode.STREAMING
        self._connected_at = self._clock()
        await self._resubscribe_all()

        receive_task = asyncio.create_task(self._receive_forever())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        try:
            done, pending = await asyncio.wait(
                {receive_task, heartbeat_task}, return_when=asyncio.FIRST_EXCEPTION
            )
            for finished in done:
                exc = finished.exception()
                if exc is not None:
                    raise exc
        finally:
            for task in (receive_task, heartbeat_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(receive_task, heartbeat_task, return_exceptions=True)

    async def _resubscribe_all(self) -> None:
        assert self._stream_client is not None
        async with self._lock:
            tickers = list(self._subscriptions.keys())
        if tickers:
            await self._stream_client.subscribe(tickers)
        self._mark_all(ConnectionState.LIVE)

    async def _heartbeat_loop(self) -> None:
        assert self._stream_client is not None
        while not self._stop_event.is_set():
            await self._sleep(self._heartbeat_interval_seconds)
            await self._stream_client.send_heartbeat()

    async def _receive_forever(self) -> None:
        assert self._stream_client is not None
        while not self._stop_event.is_set():
            raw = await self._stream_client.receive()
            self._last_message_at = self._clock()
            await self._handle_raw_frame(raw)

    async def _handle_raw_frame(self, raw: object) -> None:
        kind = classify_frame(raw)
        if kind is not FrameKind.PRICE:
            # Known harmless status/unknown frames (task scope §19) —
            # never raised as an error, only observed.
            logger.debug("live_manager operation=receive frame_kind=%s", kind.value)
            return

        try:
            event = parse_price_event(raw)
        except MarketDataMalformedResponseError:
            self._malformed_event_count += 1
            logger.warning("live_manager operation=receive status=malformed_price_event")
            return
        if event is None:
            return

        async with self._lock:
            subscription = self._subscriptions.get(event.symbol)
            if subscription is None:
                # Not (or no longer) subscribed — a benign race with a
                # recent unsubscribe, or a frame for a symbol this
                # process never asked about. Not an error.
                return
            try:
                state = apply_price_update(subscription.state, event, self._interval_policy)
                state = with_connection_state(state, ConnectionState.LIVE)
                self._set_state(subscription, state)
            except Exception:
                # `live_state` itself rejects a malformed/mismatched
                # event with a typed error (defense in depth, task
                # scope §19) — count and continue, never crash the
                # receive loop over one bad event.
                self._malformed_event_count += 1
                logger.warning(
                    "live_manager operation=receive status=rejected_by_domain symbol=%s",
                    event.symbol,
                )

    def _mark_all(self, connection_state: ConnectionState) -> None:
        # No `await` in this loop body — atomic from the event loop's
        # perspective (no other coroutine can interleave mid-iteration
        # in a single-threaded cooperative scheduler), so no explicit
        # lock is needed here even though `_subscriptions` is shared
        # mutable state (task scope §21). Same reasoning covers
        # `_set_state`'s own revision bump/event replacement below.
        for subscription in self._subscriptions.values():
            self._set_state(subscription, with_connection_state(subscription.state, connection_state))

    def _set_state(self, subscription: _Subscription, new_state: InstrumentLiveState) -> None:
        """The one place `_Subscription.state` is ever written (task
        scope §19) — bumps `revision` and wakes any `wait_for_change`
        waiters, but only on a *genuine* change. `InstrumentLiveState` is
        a frozen dataclass with structural equality, so a call that would
        set the exact same value (e.g. `_mark_all(ConnectionState.LIVE)`
        on an already-`LIVE` symbol, or `apply_price_update`'s own
        documented same-timestamp no-op) is a true no-op here too — no
        revision bump, no SSE `update` event, directly serving the
        "do not create unnecessary browser churn" requirement (task
        scope §18) without any special-casing at the SSE layer.
        """
        if new_state == subscription.state:
            return
        subscription.state = new_state
        subscription.revision += 1
        old_event = subscription.changed
        subscription.changed = asyncio.Event()
        old_event.set()
