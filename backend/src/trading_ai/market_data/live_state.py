"""Canonical, provider-agnostic live-market-state domain model (Phase 2C.1).

This module is the single source of truth *shape* that a future
instrument header, live chart, market snapshot, and freshness
indicator will all read from instead of independently formatting
whatever a REST response happened to return (the root cause identified
in the Phase 2C architecture report: three components, three
independent fetches, three independently-drifting timestamps).

Deliberately transport-agnostic (task scope §3, §21): nothing here
knows whether a `PriceUpdateEvent` originated from REST polling, a
provider WebSocket, or any other future adapter. A transport adapter's
job is to normalize whatever a real provider sends into a
`PriceUpdateEvent`/authoritative `Bar`/`InstrumentLiveState`
market-state update; this module's job is to apply those normalized
inputs deterministically. No network, no `asyncio`, no `time.sleep`,
no wall-clock reads hidden inside a function — every function that
needs "now" takes it as an explicit parameter (task scope §11, §19),
which is what makes every transition here a pure, replayable,
unit-testable function: `new_state = apply_...(old_state, ...)`,
never a mutation of shared state.

`UpdateKind` determines which entrypoint a normalized event may be
applied through (`apply_price_update` requires `PROVISIONAL`;
`apply_authoritative_snapshot` requires `AUTHORITATIVE_SNAPSHOT`) — it
is a routing/validation distinction, **not** an independent precedence
mechanism (corrective review, task scope §8: the original wording here
overclaimed this). Precedence itself is purely timestamp-based,
applied uniformly regardless of `kind` or transport: the newer
timestamp always wins; an older or exactly-equal timestamp never
regresses already-recorded state. This single rule already implements
every precedence example the architecture report and this task's spec
describe — a stale live tick never overrides a newer REST quote, and,
symmetrically, a stale/duplicate reconciliation call never overrides a
newer live tick, purely because "newer" always wins regardless of
which entrypoint produced it. No additional authority-ranking
mechanism was introduced beyond this (task scope §8: "prefer the
simplest correct model").

Two same-interval, same-timestamp `PROVISIONAL` events are a special
case of this: without a provider sequence/trade-identity field, this
domain cannot prove whether they are the same trade redelivered or two
genuinely distinct trades that happen to share a timestamp at the
granularity provided. Rather than guess, an exactly-equal timestamp
within the same open bar is a **total, deterministic no-op** — see
`apply_price_update`'s docstring for the precise rule and its
distinction from a genuinely *older* (not equal) event, which *is*
still allowed to extend `high`/`low`/volume (order-independent
aggregates) while still never regressing `close`/`last_price`.

`PriceUpdateEvent.source` stays a plain, opaque `str` label (never an
enum of transport kinds) quite deliberately: enumerating "REST" vs.
"WebSocket" vs. anything else here would reintroduce exactly the
transport coupling this slice must avoid (task scope §21). A provider
sequence/id field was evaluated and omitted — timestamp-based
precedence (below) is sufficient for every behavior this task
specifies, so an unused field was not added just because the task
mentioned it as a possibility ("only if genuinely useful").
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum

from trading_ai.watchlist.domain import InvalidTickerError, normalize_ticker

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LiveStateError(Exception):
    """Base class for live-market-state domain errors.

    Mirrors the project's existing per-area base-exception convention
    (`WatchlistError`, `MarketDataError`) rather than raising bare
    `ValueError`/`RuntimeError` (task scope §23). Raised directly (not
    through a subclass) only for generic, context-free argument checks
    (e.g. a non-UTC `now`, an invalid `IntervalPolicy`) that don't
    belong to either subclass below.
    """


class InvalidPriceUpdateEventError(LiveStateError):
    """A `PriceUpdateEvent` failed validation at the point it was applied.

    Covers structural/context problems: non-positive or non-finite
    price, negative volume hint, a non-UTC timestamp (naive, or aware
    with a non-zero offset — task scope §5 of the corrective review), a
    symbol that does not match the state it is being applied to, or an
    `UpdateKind` that does not match the entrypoint it was passed to
    (task scope §10).

    Deliberately **not** raised for a merely stale/out-of-order-but-
    otherwise-valid event — that is a normal, expected outcome of
    network delivery, not a caller bug, and is handled as a documented,
    deterministic no-op by `apply_price_update`/`apply_authoritative_*`
    instead (see their docstrings and task scope §13).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidBarError(LiveStateError):
    """An authoritative `Bar` failed validation at the point it was applied.

    Covers: non-finite/non-positive OHLC, `high < low`, a non-UTC
    timestamp (naive, or aware with a non-zero offset), or an attempt
    to authoritatively close an interval that starts *after* the
    state's own current bar (a future interval that has not even
    opened yet in this state, task scope §14).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Enums (task scope §4-§7)
# ---------------------------------------------------------------------------


class MarketState(str, Enum):
    """Normalized trading-session state for one instrument.

    Purely a *representation* of whatever an adapter tells this domain
    (e.g. a real provider's `is_market_open`/session fields) — this
    module never infers exchange calendars, holidays, or session
    boundaries itself (task scope §5). `UNKNOWN` is the honest default
    before any adapter has ever reported a session state, not a guess.
    """

    OPEN = "open"
    CLOSED = "closed"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"
    UNKNOWN = "unknown"


class ConnectionState(str, Enum):
    """Health of the backend's connection to *a* data transport —
    deliberately independent of `MarketState` (task scope §6): a
    healthy connection during a closed market is normal, not degraded,
    and a disconnected transport during an open market is a real
    problem regardless of what the market is doing.
    """

    CONNECTING = "connecting"
    LIVE = "live"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    DEGRADED = "degraded"


class FreshnessState(str, Enum):
    """User-facing honesty about how trustworthy `last_price` is right
    now — always *derived* (see `derive_freshness_state`), never a
    field an adapter sets directly, because freshness depends on
    elapsed wall-clock time and would go stale the instant it was
    stored (task scope §7).
    """

    LIVE = "live"
    DELAYED = "delayed"
    MARKET_CLOSED = "market_closed"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    NO_DATA = "no_data"


class UpdateKind(str, Enum):
    """Which entrypoint a normalized update is valid for — a
    routing/validation distinction, **not** an independent precedence
    mechanism (corrective review, task scope §8; see module docstring).
    Precedence is purely timestamp-based everywhere in this module,
    regardless of `kind`. A future REST-poll adapter and a future
    provider-WebSocket adapter both normally produce `PROVISIONAL`
    updates; only an explicit reconciliation call (regardless of
    transport) produces an `AUTHORITATIVE_*` one.
    """

    PROVISIONAL = "provisional"
    AUTHORITATIVE_SNAPSHOT = "authoritative_snapshot"


class VolumeQuality(str, Enum):
    """How much to trust `Bar.volume` (task scope §18). This module
    never assumes a provider's raw volume figure is cumulative-session
    vs. per-tick-incremental — that interpretation is a transport
    adapter's responsibility, applied *before* constructing a
    `PriceUpdateEvent`/`Bar`. Here, a `volume_hint` on an applied event
    is always treated as an already-normalized incremental contribution
    to the in-progress bar (documented at `apply_price_update`).
    """

    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"
    AUTHORITATIVE = "authoritative"


# ---------------------------------------------------------------------------
# Freshness policy (task scope §7: no magic thresholds inline)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    """Explicit, documented thresholds for `derive_freshness_state`.

    Same "documented implementation judgment call, not an invented
    false-precision number" caveat already established by
    `ai/horizon.py`'s `_MIN_HISTORY_POINTS_BY_HORIZON`/
    `_MAX_QUOTE_AGE_BY_HORIZON` — no product/architecture document read
    for this task fixes a numeric live-data freshness threshold
    (`ADR-0012` §29 explicitly leaves exact freshness thresholds open
    for future Solution Architect judgment), so these defaults are a
    reasonable, clearly-labeled starting point, not a Product-Owner- or
    provider-mandated number. A caller may supply a different
    `FreshnessPolicy` entirely; nothing here hardcodes a threshold
    inline in the derivation logic itself.
    """

    live_max_age: timedelta = timedelta(seconds=30)
    delayed_max_age: timedelta = timedelta(minutes=5)
    stale_after: timedelta = timedelta(minutes=15)


DEFAULT_FRESHNESS_POLICY = FreshnessPolicy()


# ---------------------------------------------------------------------------
# Interval policy (corrective review, task scope §7 — configurable
# interval alignment without provider coupling)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IntervalPolicy:
    """Transport-agnostic bar-interval alignment.

    `duration` is the bar size (e.g. five minutes); `interval_start`
    boundaries are computed as `anchor + n * duration` for whatever
    integer `n` places the given timestamp inside `[interval_start,
    interval_start + duration)` (see `_floor_to_interval`). Defaulting
    `anchor` to the Unix epoch keeps existing generic behavior
    unchanged (grid boundaries at predictable, timezone-independent
    points), but a future adapter may supply a different anchor (e.g.
    a specific session's opening instant) to line bar boundaries up
    with a real exchange/provider's own bars — entirely by choosing
    *where this domain's grid starts*, without this module knowing
    anything about exchange calendars, sessions, or provider names.
    `IntervalPolicy` itself contains no calendar logic and no
    provider-specific values — `anchor` is one fixed instant supplied
    by the caller, not a recurring rule this domain evaluates.

    `duration` must be a positive `timedelta`; `anchor` must be a
    timezone-aware UTC (zero-offset) `datetime` — validated by
    `_validate_interval_policy` at the point of use (task scope §5, the
    same "validate at the function boundary, not in `__post_init__`"
    convention as every other type in this module).
    """

    duration: timedelta
    anchor: datetime = _EPOCH


# ---------------------------------------------------------------------------
# Bar (task scope §8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Bar:
    """One interval's OHLCV state — in progress or closed.

    Deliberately **not** a reuse of `market_data.types.PricePoint`:
    `PricePoint` models an already-closed, REST-fetched historical bar
    whose `open`/`high`/`low` are honestly nullable (a real provider
    limitation for that HTTP response shape) and that carries no
    concept of "in progress" or volume trust level at all. `Bar` models
    a fundamentally different thing — a live-state bar that may still
    be accumulating, always has a fully-formed OHLC once any event has
    been applied to it, and must represent partial/unavailable volume
    explicitly. Adding those concepts onto `PricePoint` would leak
    live-state semantics into the already-shipped, tested REST/API
    history contract (`instruments.py`'s `/history` endpoint) that this
    task must not touch. Reusing `Decimal`/UTC-`datetime` conventions
    from `PricePoint` where they already fit is enough reuse.

    `close_at` is the timestamp of whichever applied event most
    recently determined `close` — the bookkeeping this domain needs to
    resolve out-of-order events deterministically (task scope §13; see
    `apply_price_update`). It is meaningful for a closed/authoritative
    bar too (when this reconciliation's close value was captured).

    `open` is fixed at first application to a freshly-opened bar and is
    never revised by a later-arriving, earlier-timestamped event — a
    deliberate, documented simplification (task scope §13 only requires
    ordering protection for *last price*/`close`; `high`/`low` are
    genuinely order-independent aggregates by definition, task scope
    §9, so they are updated unconditionally for any valid in-interval
    event regardless of arrival order).
    """

    interval_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    close_at: datetime
    volume: int | None
    volume_quality: VolumeQuality
    is_closed: bool


# ---------------------------------------------------------------------------
# Normalized update event (task scope §9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PriceUpdateEvent:
    """A transport-normalized price update — never a provider-specific
    payload shape (task scope §9, §21).

    `volume_hint`, when present, is treated by this domain as an
    already-normalized **incremental** contribution to the in-progress
    bar's volume (see `apply_price_update`) — converting a real
    provider's raw volume semantics (cumulative session total,
    per-trade size, or anything else) into this incremental contract is
    the transport adapter's job, not this domain's (task scope §18).

    No provider sequence/id field: timestamp-based precedence (`kind` +
    `timestamp` comparison, see module docstring) is sufficient for
    every ordering/precedence rule this task specifies, so one was not
    added speculatively.
    """

    symbol: str
    price: Decimal
    timestamp: datetime
    source: str
    kind: UpdateKind = UpdateKind.PROVISIONAL
    volume_hint: int | None = None


# ---------------------------------------------------------------------------
# Canonical live state (task scope §4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstrumentLiveState:
    """The single canonical object header/chart/snapshot/freshness-
    indicator/AI-comparison will all eventually read from (task scope
    §3). `freshness_state` is intentionally **not** a field here — see
    `derive_freshness_state`.

    `last_price`/`last_price_as_of` are both `None` only for a state
    that has never received a single valid update (`NO_DATA` — task
    scope §16); once set, they are never cleared by a connection or
    market-state change, only ever replaced by a *newer* valid value
    (last-known-good, task scope §16).
    """

    instrument: str
    last_price: Decimal | None
    last_price_as_of: datetime | None
    last_update_source: str | None
    market_state: MarketState
    connection_state: ConnectionState
    current_bar: Bar | None
    last_closed_bar: Bar | None
    history_as_of: datetime | None


# ---------------------------------------------------------------------------
# Public operations (task scope §25 — deliberately small surface)
# ---------------------------------------------------------------------------


def bootstrap_state(instrument: str) -> InstrumentLiveState:
    """Create the initial, honest `NO_DATA`/`UNKNOWN`/`CONNECTING` state
    for a symbol. Reuses the project's existing ticker normalization
    (`watchlist.domain.normalize_ticker`) rather than a competing parser
    (task scope §20) — raises `InvalidTickerError` for anything that
    fails that already-established validation.
    """
    ticker = normalize_ticker(instrument)
    return InstrumentLiveState(
        instrument=ticker,
        last_price=None,
        last_price_as_of=None,
        last_update_source=None,
        market_state=MarketState.UNKNOWN,
        connection_state=ConnectionState.CONNECTING,
        current_bar=None,
        last_closed_bar=None,
        history_as_of=None,
    )


def with_connection_state(
    state: InstrumentLiveState, connection_state: ConnectionState
) -> InstrumentLiveState:
    """Set connection health independently of everything else (task
    scope §6) — a minimal, necessary companion to the five ops task
    scope §25 names explicitly: §5/§6 require `MarketState`/
    `ConnectionState` to be independently settable by a future adapter,
    and no other listed operation does that. Never touches
    `last_price`/`current_bar`/`last_closed_bar` (last-known-good,
    task scope §16).
    """
    return replace(state, connection_state=connection_state)


def with_market_state(state: InstrumentLiveState, market_state: MarketState) -> InstrumentLiveState:
    """Set session state independently of everything else (task scope
    §5) — same minimal-companion rationale as `with_connection_state`.
    """
    return replace(state, market_state=market_state)


def apply_price_update(
    state: InstrumentLiveState, event: PriceUpdateEvent, interval: IntervalPolicy
) -> InstrumentLiveState:
    """Apply one `PROVISIONAL` tick/poll sample, aggregating it into the
    in-progress current bar and, deterministically, rolling the
    interval over when the event belongs to a later interval than the
    current bar (task scope §11, §12). `interval` is an `IntervalPolicy`
    (corrective review, task scope §7), not a raw `timedelta` — this
    lets a future adapter align bar boundaries to its own
    exchange/session anchor without this domain knowing anything about
    calendars or providers; the default anchor (Unix epoch) reproduces
    the original generic behavior unchanged.

    Within the current, still-open interval, three cases are
    distinguished by comparing `event.timestamp` against the bar's
    `close_at` (corrective review, task scope §2-§3 — the original
    version of this function let an equal-timestamp event still extend
    `high`/`low`/volume, which this review found ambiguous without a
    provider sequence/trade-identity field):

    - `event.timestamp == bar.close_at` — a **total, deterministic
      no-op**. Without sequence/trade identity, this domain cannot
      prove whether this is the same trade redelivered or a genuinely
      distinct trade that happens to share a timestamp at the
      granularity provided; treating it as a no-op (never touching
      `open`/`high`/`low`/`close`/`close_at`/`volume`/`last_price`/
      `last_price_as_of`, regardless of price or `volume_hint`) is the
      only choice that cannot silently corrupt the bar depending on
      arrival order. This is *not* an error — ordinary, expected
      redelivery — so no exception is raised, `state` is simply
      returned unchanged.
    - `event.timestamp < bar.close_at` — a genuinely **older, distinct**
      event (still within the same open interval). `high`/`low` extend
      unconditionally (order-independent aggregates by definition,
      task scope §9) and `volume_hint`, if present, still contributes
      incrementally — real trading activity that occurred in this
      interval is not discarded merely because it was reported out of
      order. `close`/`close_at` (and the outer state's `last_price`/
      `last_price_as_of`) are **not** changed — an older event must
      never regress the displayed last price (task scope §13).
    - `event.timestamp > bar.close_at` — the normal case: everything
      (`high`/`low`/volume/`close`/`close_at`/`last_price`) updates.

    An event whose interval is *older* than the current bar's interval
    (arrived very late, after rollover already happened) never touches
    `current_bar` or `last_closed_bar` at all — only
    `apply_authoritative_closed_bar` may ever replace a closed bar
    (task scope §14); this function structurally cannot, since it never
    writes to `last_closed_bar` except as part of the rollover it
    itself performs. Missing intervals are never fabricated (task scope
    §12) — an event several intervals ahead simply rolls directly to
    its own interval; no empty bars are synthesized for the gap.
    """
    _validate_interval_policy(interval)
    _validate_event(state, event, expected_kind=UpdateKind.PROVISIONAL)

    event_interval_start = _floor_to_interval(event.timestamp, interval)

    if state.current_bar is None or event_interval_start > state.current_bar.interval_start:
        # First bar ever, or a rollover: close whatever was open (if
        # anything) and seed a brand-new bar purely from this event.
        new_closed_bar = (
            replace(state.current_bar, is_closed=True) if state.current_bar is not None else None
        )
        new_current_bar = Bar(
            interval_start=event_interval_start,
            open=event.price,
            high=event.price,
            low=event.price,
            close=event.price,
            close_at=event.timestamp,
            volume=event.volume_hint,
            volume_quality=VolumeQuality.PARTIAL if event.volume_hint is not None else VolumeQuality.UNAVAILABLE,
            is_closed=False,
        )
        next_state = replace(
            state,
            current_bar=new_current_bar,
            last_closed_bar=new_closed_bar if new_closed_bar is not None else state.last_closed_bar,
        )
        return _apply_last_price_if_newer(next_state, event)

    if event_interval_start == state.current_bar.interval_start:
        bar = state.current_bar

        if event.timestamp == bar.close_at:
            # Total no-op — see docstring. Deliberately returns the
            # original `state` object, not even a `replace()` no-op, to
            # make the "nothing changed" guarantee explicit and cheap.
            return state

        new_high = max(bar.high, event.price)
        new_low = min(bar.low, event.price)
        new_volume: int | None
        new_volume_quality: VolumeQuality
        if event.volume_hint is not None:
            new_volume = (bar.volume or 0) + event.volume_hint
            new_volume_quality = VolumeQuality.PARTIAL
        else:
            new_volume, new_volume_quality = bar.volume, bar.volume_quality

        if event.timestamp > bar.close_at:
            new_close, new_close_at = event.price, event.timestamp
        else:
            # event.timestamp < bar.close_at: older, distinct event —
            # extrema/volume contribute, close/last_price do not regress.
            new_close, new_close_at = bar.close, bar.close_at

        updated_bar = replace(
            bar,
            high=new_high,
            low=new_low,
            close=new_close,
            close_at=new_close_at,
            volume=new_volume,
            volume_quality=new_volume_quality,
        )
        return _apply_last_price_if_newer(replace(state, current_bar=updated_bar), event)

    # event_interval_start < state.current_bar.interval_start: a
    # straggler for an already-rolled-over interval. Bars are untouched
    # (closed-bar authority, task scope §14); `last_price` may still
    # advance if this event is somehow newer than the recorded
    # timestamp (it structurally won't be in the common case, but the
    # same single newer-wins rule handles it correctly either way
    # without a separate special case).
    return _apply_last_price_if_newer(state, event)


def apply_authoritative_snapshot(
    state: InstrumentLiveState, event: PriceUpdateEvent
) -> InstrumentLiveState:
    """Apply an authoritative point-in-time price (e.g. a REST quote
    reconciliation) — updates only `last_price`/`last_price_as_of`
    (task scope §15), never `current_bar`/`last_closed_bar`: bar
    aggregation is driven exclusively by `apply_price_update` and
    `apply_authoritative_closed_bar`, keeping "what is the latest
    price" and "what does the current bar look like" independently
    reasoned about.

    Same newer-wins precedence as everywhere else in this module — an
    older/duplicate-timestamped snapshot is a deterministic no-op, so a
    stale reconciliation call can never regress a genuinely newer
    provisional tick (task scope §8, §15).
    """
    _validate_event(state, event, expected_kind=UpdateKind.AUTHORITATIVE_SNAPSHOT)
    return _apply_last_price_if_newer(state, event)


def apply_authoritative_closed_bar(
    state: InstrumentLiveState, bar: Bar, *, now: datetime
) -> InstrumentLiveState:
    """Replace `last_closed_bar` with a provider-reconciled, authoritative
    bar (task scope §14, §15) — the only way, besides this function's
    own rollover inside `apply_price_update`, that `last_closed_bar` is
    ever written. No I/O happens here; the caller already has the
    authoritative `Bar` in hand (a future REST-reconciliation adapter's
    job to fetch and construct it).

    Rejected (raises `InvalidBarError`, a caller-misuse case, not a
    routine no-op) if `bar.interval_start` is later than the state's
    own current bar — this function cannot authoritatively close an
    interval that has not even opened yet in this state.

    A stale reconciliation for the same `interval_start` — one whose
    `close_at` is older than what is already recorded there — is a
    deterministic no-op (same newer-wins rule as everywhere else),
    never an exception; a slow/retried reconciliation call arriving
    after a fresher one is a routine, expected occurrence.

    `last_price`/`last_price_as_of` are refreshed too, using the same
    newer-wins rule, since a reconciled closed bar's `close` is real,
    authoritative price information.
    """
    _require_utc(now, "now")
    _validate_bar(bar)
    if state.current_bar is not None and bar.interval_start > state.current_bar.interval_start:
        raise InvalidBarError(
            "cannot authoritatively close an interval later than the current bar"
        )
    if (
        state.last_closed_bar is not None
        and state.last_closed_bar.interval_start == bar.interval_start
        and state.last_closed_bar.close_at > bar.close_at
    ):
        return state

    closed_bar = bar if bar.is_closed else replace(bar, is_closed=True)
    next_state = replace(state, last_closed_bar=closed_bar, history_as_of=now)
    if next_state.last_price_as_of is None or closed_bar.close_at > next_state.last_price_as_of:
        next_state = replace(
            next_state,
            last_price=closed_bar.close,
            last_price_as_of=closed_bar.close_at,
            last_update_source="authoritative_closed_bar",
        )
    return next_state


def derive_freshness_state(
    state: InstrumentLiveState, policy: FreshnessPolicy, now: datetime
) -> FreshnessState:
    """Deterministically derive user-facing freshness from
    `MarketState` + `ConnectionState` + `last_price_as_of` + `now` +
    `policy` (task scope §7) — never stored on `InstrumentLiveState`
    itself, since it is a function of elapsed wall-clock time and would
    be stale the instant it was written down.

    Order of precedence:
    1. `NO_DATA` — no valid value has ever been received, regardless of
       connection/market state.
    2. `DISCONNECTED` — the transport is known to be down; the last
       valid price is still whatever `last_price` holds (last-known-
       good, task scope §16), but the connection problem is surfaced
       honestly rather than silently reusing `LIVE`.
    3. `MarketState.CLOSED` — absence of a new tick is *not* staleness
       by itself (`ADR-0012` §22's already-approved principle) →
       `MARKET_CLOSED`, unless the data is old enough to cross
       `policy.stale_after` regardless of market state (task scope §17:
       "actual stale policy may still override when data is
       unreasonably old").
    4. `OPEN`/`PRE_MARKET`/`AFTER_HOURS`/`UNKNOWN` — normal age bands
       against `policy.live_max_age`/`delayed_max_age`/`stale_after`
       (corrective review, task scope §6: the original version treated
       *every* non-`OPEN` state as `MARKET_CLOSED`, which was wrong for
       `PRE_MARKET`/`AFTER_HOURS` — extended-hours updates can be
       genuinely live — and for `UNKNOWN`, which must not *claim*
       "market closed" merely because session state hasn't been
       reported yet; `CLOSED` is the only state honestly known to mean
       "no new prices are expected right now").

    `RECONNECTING`/`DEGRADED`/`CONNECTING` connection states
    deliberately do *not* short-circuit to `DISCONNECTED` — a
    reconnecting transport may still be showing a genuinely fresh price
    by age; only a fully `DISCONNECTED` transport is treated as an
    unconditional freshness override (`FreshnessState` has no dedicated
    `RECONNECTING` value — forcing it to `DISCONNECTED` here would be
    dishonest in the other direction).
    """
    _require_utc(now, "now")
    if state.last_price is None or state.last_price_as_of is None:
        return FreshnessState.NO_DATA
    if state.connection_state is ConnectionState.DISCONNECTED:
        return FreshnessState.DISCONNECTED

    age = now - state.last_price_as_of

    if state.market_state is MarketState.CLOSED:
        if age <= policy.stale_after:
            return FreshnessState.MARKET_CLOSED
        return FreshnessState.STALE

    # OPEN, PRE_MARKET, AFTER_HOURS, and UNKNOWN all use the normal
    # age bands — only a definitively CLOSED market gets the
    # MARKET_CLOSED treatment above.
    if age <= policy.live_max_age:
        return FreshnessState.LIVE
    if age <= policy.delayed_max_age:
        return FreshnessState.DELAYED
    return FreshnessState.STALE


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _apply_last_price_if_newer(
    state: InstrumentLiveState, event: PriceUpdateEvent
) -> InstrumentLiveState:
    if state.last_price_as_of is not None and event.timestamp <= state.last_price_as_of:
        return state
    return replace(
        state,
        last_price=event.price,
        last_price_as_of=event.timestamp,
        last_update_source=event.source,
    )


def _floor_to_interval(timestamp: datetime, policy: IntervalPolicy) -> datetime:
    """Deterministic interval boundary relative to `policy.anchor`
    (corrective review, task scope §7 — previously hardcoded to the
    Unix epoch; the default `IntervalPolicy.anchor` still is the epoch,
    so default behavior is unchanged). The same timestamp always floors
    to the same boundary regardless of when or in what order it is
    processed (task scope §19: replay-safe), for any fixed anchor. Not
    guaranteed to line up with a specific real provider's own bar
    boundaries (e.g. exchange-session-aligned 5-minute bars) unless the
    caller supplies a matching anchor — reconciliation via
    `apply_authoritative_closed_bar` remains the correction mechanism
    either way; this pure domain only needs internally consistent
    boundaries, not knowledge of any real exchange calendar.
    """
    elapsed = timestamp - policy.anchor
    bucket_index = elapsed // policy.duration
    return policy.anchor + bucket_index * policy.duration


def _validate_interval_policy(policy: IntervalPolicy) -> None:
    if policy.duration <= timedelta(0):
        raise LiveStateError("IntervalPolicy.duration must be a positive timedelta")
    if not _is_utc(policy.anchor):
        raise LiveStateError("IntervalPolicy.anchor must be a timezone-aware UTC datetime (zero offset)")


def _is_utc(value: datetime) -> bool:
    """`True` only for a timezone-aware datetime whose UTC offset is
    exactly zero (corrective review, task scope §5). Rejects both a
    naive datetime (`tzinfo is None`, `utcoffset()` is `None`) and an
    aware-but-non-UTC offset like `+03:00` — the previous validation
    only checked awareness, silently accepting any offset while error
    messages already claimed "UTC". This module never silently
    converts a non-UTC-but-aware timestamp to UTC — an adapter that has
    a non-UTC timestamp is responsible for converting it before
    constructing a `PriceUpdateEvent`/`Bar`/`IntervalPolicy`, exactly
    like every other normalization this domain expects of adapters.
    """
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


def _require_utc(value: datetime, name: str) -> None:
    if not _is_utc(value):
        raise LiveStateError(f"{name} must be a timezone-aware UTC datetime (zero offset)")


def _validate_event(
    state: InstrumentLiveState, event: PriceUpdateEvent, *, expected_kind: UpdateKind
) -> None:
    if event.kind is not expected_kind:
        raise InvalidPriceUpdateEventError(
            f"expected a {expected_kind.value} update, got {event.kind.value}"
        )
    if not _is_utc(event.timestamp):
        raise InvalidPriceUpdateEventError(
            "event timestamp must be a timezone-aware UTC datetime (zero offset)"
        )
    if not event.price.is_finite() or event.price <= 0:
        raise InvalidPriceUpdateEventError("event price must be a finite, positive Decimal")
    if event.volume_hint is not None and event.volume_hint < 0:
        raise InvalidPriceUpdateEventError("event volume_hint must not be negative")
    try:
        normalized_symbol = normalize_ticker(event.symbol)
    except InvalidTickerError as exc:
        raise InvalidPriceUpdateEventError(f"invalid event symbol: {exc.reason}") from exc
    if normalized_symbol != state.instrument:
        raise InvalidPriceUpdateEventError(
            f"event symbol {normalized_symbol!r} does not match state instrument {state.instrument!r}"
        )


def _validate_bar(bar: Bar) -> None:
    if not _is_utc(bar.interval_start) or not _is_utc(bar.close_at):
        raise InvalidBarError("bar timestamps must be timezone-aware UTC datetimes (zero offset)")
    for label, value in (("open", bar.open), ("high", bar.high), ("low", bar.low), ("close", bar.close)):
        if not value.is_finite() or value <= 0:
            raise InvalidBarError(f"bar {label} must be a finite, positive Decimal")
    if bar.high < bar.low:
        raise InvalidBarError("bar high must not be less than bar low")
    if bar.volume is not None and bar.volume < 0:
        raise InvalidBarError("bar volume must not be negative")
