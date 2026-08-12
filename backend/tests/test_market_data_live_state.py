"""Deterministic tests for `market_data/live_state.py` (Phase 2C.1,
corrective review pass).

Every function under test is pure and network-free — no gateway, no
httpx, no asyncio, no real clock. All "now"/timestamps are explicit
fixed constants (task scope §22 of the original slice: "Tests must not
use network" — and, implicitly, must not depend on the wall clock
either, or they would not be deterministic).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trading_ai.market_data.live_state import (
    Bar,
    ConnectionState,
    DEFAULT_FRESHNESS_POLICY,
    FreshnessPolicy,
    FreshnessState,
    IntervalPolicy,
    InvalidBarError,
    InvalidPriceUpdateEventError,
    LiveStateError,
    MarketState,
    PriceUpdateEvent,
    UpdateKind,
    VolumeQuality,
    apply_authoritative_closed_bar,
    apply_authoritative_snapshot,
    apply_price_update,
    bootstrap_state,
    derive_freshness_state,
    with_connection_state,
    with_market_state,
)
from trading_ai.watchlist.domain import InvalidTickerError

_POLICY = IntervalPolicy(duration=timedelta(minutes=5))

# 2026-03-02T14:30:00Z floors to itself under a 5-minute epoch-anchored
# grid (14:30 is an exact 5-minute epoch boundary) — a convenient,
# deterministic base for interval-boundary tests.
_T0 = datetime(2026, 3, 2, 14, 30, 0, tzinfo=timezone.utc)
_T0_PLUS_1 = _T0 + timedelta(minutes=1)
_T0_PLUS_2 = _T0 + timedelta(minutes=2)
_NEXT_INTERVAL = _T0 + timedelta(minutes=5)
_FAR_INTERVAL = _T0 + timedelta(minutes=25)

_PLUS_3H = timezone(timedelta(hours=3))


def _event(
    price: str,
    timestamp: datetime = _T0,
    *,
    symbol: str = "AAPL",
    source: str = "test_adapter",
    kind: UpdateKind = UpdateKind.PROVISIONAL,
    volume_hint: int | None = None,
) -> PriceUpdateEvent:
    return PriceUpdateEvent(
        symbol=symbol,
        price=Decimal(price),
        timestamp=timestamp,
        source=source,
        kind=kind,
        volume_hint=volume_hint,
    )


def _bar(
    interval_start: datetime = _T0,
    *,
    open_: str = "100",
    high: str = "101",
    low: str = "99",
    close: str = "100.5",
    close_at: datetime | None = None,
    volume: int | None = 1000,
    volume_quality: VolumeQuality = VolumeQuality.AUTHORITATIVE,
    is_closed: bool = True,
) -> Bar:
    return Bar(
        interval_start=interval_start,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        close_at=close_at or interval_start,
        volume=volume,
        volume_quality=volume_quality,
        is_closed=is_closed,
    )


# --- 1. empty initial state -------------------------------------------------


def test_bootstrap_state_is_empty_no_data() -> None:
    state = bootstrap_state("aapl")

    assert state.instrument == "AAPL"
    assert state.last_price is None
    assert state.last_price_as_of is None
    assert state.current_bar is None
    assert state.last_closed_bar is None
    assert state.market_state is MarketState.UNKNOWN
    assert state.connection_state is ConnectionState.CONNECTING


def test_bootstrap_state_rejects_invalid_ticker() -> None:
    with pytest.raises(InvalidTickerError):
        bootstrap_state("")


# --- 2. first valid price event --------------------------------------------


def test_apply_price_update_first_event_opens_bar_and_sets_last_price() -> None:
    state = bootstrap_state("AAPL")

    next_state = apply_price_update(state, _event("303.94", _T0), _POLICY)

    assert next_state.last_price == Decimal("303.94")
    assert next_state.last_price_as_of == _T0
    assert next_state.last_update_source == "test_adapter"
    assert next_state.current_bar is not None
    bar = next_state.current_bar
    assert bar.interval_start == _T0
    assert bar.open == bar.high == bar.low == bar.close == Decimal("303.94")
    assert bar.close_at == _T0
    assert bar.is_closed is False
    assert bar.volume is None
    assert bar.volume_quality is VolumeQuality.UNAVAILABLE


# --- 3. second event same interval -----------------------------------------


def test_apply_price_update_second_event_same_interval_updates_close() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    state = apply_price_update(state, _event("100.50", _T0_PLUS_1), _POLICY)

    bar = state.current_bar
    assert bar is not None
    assert bar.interval_start == _T0
    assert bar.open == Decimal("100")
    assert bar.close == Decimal("100.50")
    assert bar.close_at == _T0_PLUS_1
    assert state.last_price == Decimal("100.50")


# --- 4. high update ----------------------------------------------------------


def test_apply_price_update_updates_high_when_price_exceeds_it() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    state = apply_price_update(state, _event("105", _T0_PLUS_1), _POLICY)

    assert state.current_bar is not None
    assert state.current_bar.high == Decimal("105")
    assert state.current_bar.low == Decimal("100")


# --- 5. low update ------------------------------------------------------------


def test_apply_price_update_updates_low_when_price_below_it() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    state = apply_price_update(state, _event("95", _T0_PLUS_1), _POLICY)

    assert state.current_bar is not None
    assert state.current_bar.low == Decimal("95")
    assert state.current_bar.high == Decimal("100")


# --- 6. close update -----------------------------------------------------------


def test_apply_price_update_close_always_tracks_latest_timestamped_event() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = apply_price_update(state, _event("110", _T0_PLUS_1), _POLICY)

    state = apply_price_update(state, _event("102", _T0_PLUS_2), _POLICY)

    assert state.current_bar is not None
    assert state.current_bar.close == Decimal("102")
    assert state.current_bar.high == Decimal("110")


# --- 7. interval rollover -----------------------------------------------------


def test_apply_price_update_rolls_over_to_new_interval() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = apply_price_update(state, _event("105", _T0_PLUS_1), _POLICY)

    state = apply_price_update(state, _event("110", _NEXT_INTERVAL), _POLICY)

    assert state.last_closed_bar is not None
    assert state.last_closed_bar.interval_start == _T0
    assert state.last_closed_bar.close == Decimal("105")
    assert state.last_closed_bar.is_closed is True

    assert state.current_bar is not None
    assert state.current_bar.interval_start == _NEXT_INTERVAL
    assert state.current_bar.open == Decimal("110")
    assert state.current_bar.close == Decimal("110")
    assert state.current_bar.is_closed is False


# --- 8. no fabricated empty bars ----------------------------------------------


def test_apply_price_update_does_not_fabricate_bars_for_skipped_intervals() -> None:
    """A gap of several intervals (e.g. after a reconnect) must roll
    directly to the event's own interval — never synthesize empty bars
    for the intervals in between (task scope §12)."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    state = apply_price_update(state, _event("120", _FAR_INTERVAL), _POLICY)

    assert state.current_bar is not None
    assert state.current_bar.interval_start == _FAR_INTERVAL
    assert state.last_closed_bar is not None
    assert state.last_closed_bar.interval_start == _T0
    # No trace of the skipped intervals exists anywhere in the state —
    # only current_bar and last_closed_bar are tracked at all, and both
    # point directly at the real, non-fabricated intervals.


# --- 9. duplicate (exactly-equal-timestamp) event: TOTAL no-op -----------------
# Corrective review, task scope §2/§4: without provider sequence/trade
# identity, an exactly-equal-timestamp PROVISIONAL event can never be
# proven distinct from a redelivered duplicate — it must be a complete
# no-op, not just a partial one.


def test_apply_price_update_same_timestamp_different_price_is_total_no_op() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    duplicate = apply_price_update(state, _event("105", _T0), _POLICY)

    assert duplicate == state
    assert duplicate.current_bar is not None
    assert duplicate.current_bar.close == Decimal("100")
    assert duplicate.current_bar.high == Decimal("100")  # NOT extended to 105
    assert duplicate.current_bar.low == Decimal("100")
    assert duplicate.last_price == Decimal("100")


def test_apply_price_update_same_timestamp_same_price_is_total_no_op() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    duplicate = apply_price_update(state, _event("100", _T0), _POLICY)

    assert duplicate == state


def test_apply_price_update_same_timestamp_duplicate_does_not_double_volume() -> None:
    """Task scope §4's dedicated required case: first event volume_hint
    100, duplicate at the same timestamp also volume_hint 100 — the
    resulting bar volume must be 100, never 200."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0, volume_hint=100), _POLICY)
    assert state.current_bar is not None
    assert state.current_bar.volume == 100

    duplicate = apply_price_update(state, _event("100", _T0, volume_hint=100), _POLICY)

    assert duplicate.current_bar is not None
    assert duplicate.current_bar.volume == 100


def test_apply_price_update_same_timestamp_different_price_and_volume_is_total_no_op() -> None:
    """Task scope §4: same timestamp + different price + volume_hint is
    still a total no-op — the conflicting duplicate must not add volume
    either."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0, volume_hint=100), _POLICY)

    duplicate = apply_price_update(state, _event("999", _T0, volume_hint=50), _POLICY)

    assert duplicate == state
    assert duplicate.current_bar is not None
    assert duplicate.current_bar.volume == 100


# --- 10. older but distinct event (timestamp < close_at) -----------------------
# Corrective review, task scope §3: not to be confused with an
# exactly-equal-timestamp duplicate (§9 above). A genuinely older,
# distinct event within the same still-open interval may still extend
# high/low/volume (order-independent aggregates), but must never
# regress close/last_price.


def test_apply_price_update_older_distinct_event_extends_high_low() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("110", _T0_PLUS_2), _POLICY)

    late_arriving_older = apply_price_update(state, _event("90", _T0), _POLICY)

    assert late_arriving_older.current_bar is not None
    assert late_arriving_older.current_bar.close == Decimal("110")
    assert late_arriving_older.current_bar.close_at == _T0_PLUS_2
    assert late_arriving_older.current_bar.low == Decimal("90")
    assert late_arriving_older.last_price == Decimal("110")


def test_apply_price_update_older_distinct_event_contributes_volume() -> None:
    """Task scope §3: an older, distinct event's `volume_hint`, if
    present, still contributes to the bar's accumulated volume — real
    trading activity that occurred in this interval is not discarded
    merely because it was reported out of order."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("110", _T0_PLUS_2, volume_hint=200), _POLICY)
    assert state.current_bar is not None
    assert state.current_bar.volume == 200

    older = apply_price_update(state, _event("90", _T0, volume_hint=50), _POLICY)

    assert older.current_bar is not None
    assert older.current_bar.volume == 250
    assert older.current_bar.close == Decimal("110")  # close still not regressed


# --- 11. stale older update cannot replace newer price -------------------------


def test_apply_price_update_older_event_after_newer_does_not_change_last_price() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("110", _T0_PLUS_2), _POLICY)

    state = apply_price_update(state, _event("90", _T0), _POLICY)

    assert state.last_price == Decimal("110")
    assert state.last_price_as_of == _T0_PLUS_2


# --- 12. authoritative snapshot beats older provisional update -----------------


def test_authoritative_snapshot_with_newer_timestamp_overrides_provisional() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    snapshot = _event(
        "101.25", _T0_PLUS_2, kind=UpdateKind.AUTHORITATIVE_SNAPSHOT, source="rest_reconciliation"
    )
    state = apply_authoritative_snapshot(state, snapshot)

    assert state.last_price == Decimal("101.25")
    assert state.last_price_as_of == _T0_PLUS_2
    assert state.last_update_source == "rest_reconciliation"
    # Snapshot never touches bar aggregation.
    assert state.current_bar is not None
    assert state.current_bar.close == Decimal("100")


def test_authoritative_snapshot_with_older_timestamp_is_a_no_op() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0_PLUS_2), _POLICY)

    stale_snapshot = _event(
        "999", _T0, kind=UpdateKind.AUTHORITATIVE_SNAPSHOT, source="rest_reconciliation"
    )
    state = apply_authoritative_snapshot(state, stale_snapshot)

    assert state.last_price == Decimal("100")
    assert state.last_price_as_of == _T0_PLUS_2


def test_older_provisional_cannot_overwrite_newer_authoritative_last_price() -> None:
    """Task scope §8's explicit minimum-behavior requirement, tested
    directly: an older PROVISIONAL update must never overwrite
    `last_price` set by a newer AUTHORITATIVE_SNAPSHOT — even though
    the same provisional event *does* still legally update the current
    bar's `close` (bar aggregation and outer `last_price` are
    independent, task scope §15)."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    snapshot = _event(
        "101.25", _T0 + timedelta(minutes=3), kind=UpdateKind.AUTHORITATIVE_SNAPSHOT, source="rest"
    )
    state = apply_authoritative_snapshot(state, snapshot)
    assert state.last_price == Decimal("101.25")

    # A provisional tick newer than the bar's own close_at (_T0) but
    # older than the authoritative snapshot's timestamp.
    older_provisional = apply_price_update(state, _event("50", _T0_PLUS_1), _POLICY)

    assert older_provisional.last_price == Decimal("101.25")  # unchanged, still authoritative
    assert older_provisional.last_price_as_of == _T0 + timedelta(minutes=3)
    assert older_provisional.current_bar is not None
    assert older_provisional.current_bar.close == Decimal("50")  # bar itself still updates


# --- 13. authoritative closed bar replacement -----------------------------------


def test_apply_authoritative_closed_bar_replaces_provisional_rollover_bar() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = apply_price_update(state, _event("105", _NEXT_INTERVAL), _POLICY)
    assert state.last_closed_bar is not None
    assert state.last_closed_bar.volume_quality is VolumeQuality.UNAVAILABLE

    authoritative = _bar(
        _T0, open_="100", high="103", low="99.5", close="102", close_at=_T0 + timedelta(minutes=4),
        volume=48213, volume_quality=VolumeQuality.AUTHORITATIVE,
    )
    state = apply_authoritative_closed_bar(state, authoritative, now=_NEXT_INTERVAL)

    assert state.last_closed_bar == authoritative
    assert state.history_as_of == _NEXT_INTERVAL


def test_apply_authoritative_closed_bar_rejects_future_interval() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    future_bar = _bar(_FAR_INTERVAL)

    with pytest.raises(InvalidBarError):
        apply_authoritative_closed_bar(state, future_bar, now=_T0)


def test_apply_authoritative_closed_bar_stale_reconciliation_is_a_no_op() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = apply_price_update(state, _event("105", _NEXT_INTERVAL), _POLICY)

    fresh = _bar(_T0, close="102", close_at=_T0 + timedelta(minutes=4))
    state = apply_authoritative_closed_bar(state, fresh, now=_NEXT_INTERVAL)

    stale = _bar(_T0, close="999", close_at=_T0 + timedelta(minutes=1))
    result = apply_authoritative_closed_bar(state, stale, now=_NEXT_INTERVAL + timedelta(minutes=1))

    assert result.last_closed_bar == fresh


# --- 14. live event cannot mutate authoritative closed bar ----------------------


def test_apply_price_update_cannot_mutate_already_closed_bar() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = apply_price_update(state, _event("105", _NEXT_INTERVAL), _POLICY)

    authoritative = _bar(_T0, close="102", close_at=_T0 + timedelta(minutes=4))
    state = apply_authoritative_closed_bar(state, authoritative, now=_NEXT_INTERVAL)

    # A straggler event for the now-closed first interval must not
    # touch `last_closed_bar` at all.
    straggler = _event("999", _T0 + timedelta(minutes=3))
    state = apply_price_update(state, straggler, _POLICY)

    assert state.last_closed_bar == authoritative
    assert state.current_bar is not None
    assert state.current_bar.interval_start == _NEXT_INTERVAL


# --- 15-20: freshness derivation ------------------------------------------------


def test_derive_freshness_state_market_open_fresh_connection_is_live() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, MarketState.OPEN)
    state = with_connection_state(state, ConnectionState.LIVE)

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(seconds=5))

    assert freshness is FreshnessState.LIVE


@pytest.mark.parametrize(
    "market_state", [MarketState.PRE_MARKET, MarketState.AFTER_HOURS, MarketState.UNKNOWN]
)
def test_derive_freshness_state_extended_and_unknown_sessions_with_recent_price_are_live(
    market_state: MarketState,
) -> None:
    """Corrective review, task scope §6: PRE_MARKET/AFTER_HOURS/UNKNOWN
    must use the normal age bands, not be forced to MARKET_CLOSED —
    extended-hours updates can be genuinely live, and UNKNOWN must not
    *claim* the market is closed merely because session state hasn't
    been reported."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, market_state)
    state = with_connection_state(state, ConnectionState.LIVE)

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(seconds=5))

    assert freshness is FreshnessState.LIVE


def test_derive_freshness_state_market_closed_is_not_falsely_stale() -> None:
    """A gap well within `DEFAULT_FRESHNESS_POLICY.stale_after` (15
    minutes) but far beyond `live_max_age`/`delayed_max_age` — the
    market being closed, not raw age, is what must decide this case
    (task scope §17 of the original task)."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, MarketState.CLOSED)
    state = with_connection_state(state, ConnectionState.LIVE)

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(minutes=10))

    assert freshness is FreshnessState.MARKET_CLOSED


def test_derive_freshness_state_market_closed_but_unreasonably_old_is_stale() -> None:
    """Stale policy may still override "market closed" when the data is
    old enough (task scope §17 of the original task)."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, MarketState.CLOSED)
    state = with_connection_state(state, ConnectionState.LIVE)

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(days=3))

    assert freshness is FreshnessState.STALE


def test_derive_freshness_state_disconnected_preserves_last_known_good_price() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("303.94", _T0), _POLICY)
    state = with_market_state(state, MarketState.OPEN)
    state = with_connection_state(state, ConnectionState.LIVE)

    state = with_connection_state(state, ConnectionState.DISCONNECTED)

    assert state.last_price == Decimal("303.94")
    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(seconds=5))
    assert freshness is FreshnessState.DISCONNECTED


def test_derive_freshness_state_no_data_state() -> None:
    state = bootstrap_state("AAPL")

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0)

    assert freshness is FreshnessState.NO_DATA


def test_derive_freshness_state_stale_transition() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, MarketState.OPEN)
    state = with_connection_state(state, ConnectionState.LIVE)

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(minutes=30))

    assert freshness is FreshnessState.STALE


def test_derive_freshness_state_delayed_transition() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, MarketState.OPEN)
    state = with_connection_state(state, ConnectionState.LIVE)

    freshness = derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, _T0 + timedelta(minutes=2))

    assert freshness is FreshnessState.DELAYED


def test_derive_freshness_state_custom_policy_thresholds_are_honored() -> None:
    """No threshold is hardcoded in the derivation logic itself (task
    scope §7 of the original task) — a caller-supplied policy fully
    controls the bands."""
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)
    state = with_market_state(state, MarketState.OPEN)
    state = with_connection_state(state, ConnectionState.LIVE)
    generous_policy = FreshnessPolicy(
        live_max_age=timedelta(minutes=10),
        delayed_max_age=timedelta(minutes=30),
        stale_after=timedelta(hours=1),
    )

    freshness = derive_freshness_state(state, generous_policy, _T0 + timedelta(minutes=5))

    assert freshness is FreshnessState.LIVE


# --- 21. UTC/timezone validation ------------------------------------------------
# Corrective review, task scope §5: reject naive AND aware-non-UTC
# (e.g. +03:00) datetimes everywhere a timestamp is required.


def test_apply_price_update_rejects_naive_event_timestamp() -> None:
    state = bootstrap_state("AAPL")
    naive_event = PriceUpdateEvent(
        symbol="AAPL", price=Decimal("100"), timestamp=datetime(2026, 3, 2, 14, 30), source="x"
    )

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(state, naive_event, _POLICY)


def test_apply_price_update_rejects_non_utc_offset_event_timestamp() -> None:
    state = bootstrap_state("AAPL")
    offset_event = PriceUpdateEvent(
        symbol="AAPL",
        price=Decimal("100"),
        timestamp=datetime(2026, 3, 2, 17, 30, tzinfo=_PLUS_3H),
        source="x",
    )

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(state, offset_event, _POLICY)


def test_apply_price_update_accepts_zero_offset_non_utc_singleton_timezone() -> None:
    """A `timezone(timedelta(0))` instance is not the `timezone.utc`
    singleton but is semantically zero-offset UTC — must be accepted,
    proving the check is offset-based, not identity-based."""
    state = bootstrap_state("AAPL")
    zero_offset = timezone(timedelta(0))
    event = PriceUpdateEvent(
        symbol="AAPL", price=Decimal("100"), timestamp=datetime(2026, 3, 2, 14, 30, tzinfo=zero_offset), source="x"
    )

    result = apply_price_update(state, event, _POLICY)

    assert result.last_price == Decimal("100")


def test_derive_freshness_state_rejects_naive_now() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(LiveStateError):
        derive_freshness_state(state, DEFAULT_FRESHNESS_POLICY, datetime(2026, 3, 2, 14, 30))


def test_derive_freshness_state_rejects_non_utc_offset_now() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(LiveStateError):
        derive_freshness_state(
            state, DEFAULT_FRESHNESS_POLICY, datetime(2026, 3, 2, 17, 30, tzinfo=_PLUS_3H)
        )


def test_apply_authoritative_closed_bar_rejects_naive_now() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(LiveStateError):
        apply_authoritative_closed_bar(state, _bar(_T0), now=datetime(2026, 3, 2, 14, 30))


def test_apply_authoritative_closed_bar_rejects_non_utc_offset_now() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(LiveStateError):
        apply_authoritative_closed_bar(
            state, _bar(_T0), now=datetime(2026, 3, 2, 17, 30, tzinfo=_PLUS_3H)
        )


def test_apply_authoritative_closed_bar_rejects_non_utc_offset_bar_timestamps() -> None:
    state = bootstrap_state("AAPL")
    non_utc_bar = _bar(
        datetime(2026, 3, 2, 14, 30, tzinfo=_PLUS_3H),
        close_at=datetime(2026, 3, 2, 14, 34, tzinfo=_PLUS_3H),
    )

    with pytest.raises(InvalidBarError):
        apply_authoritative_closed_bar(state, non_utc_bar, now=_T0)


# --- 22. optional volume ---------------------------------------------------------


def test_apply_price_update_accumulates_volume_hint_incrementally() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0, volume_hint=500), _POLICY)

    state = apply_price_update(state, _event("101", _T0_PLUS_1, volume_hint=300), _POLICY)

    assert state.current_bar is not None
    assert state.current_bar.volume == 800
    assert state.current_bar.volume_quality is VolumeQuality.PARTIAL


# --- 23. unavailable volume -------------------------------------------------------


def test_apply_price_update_leaves_volume_unavailable_when_never_provided() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    state = apply_price_update(state, _event("101", _T0_PLUS_1), _POLICY)

    assert state.current_bar is not None
    assert state.current_bar.volume is None
    assert state.current_bar.volume_quality is VolumeQuality.UNAVAILABLE


def test_apply_price_update_rejects_negative_volume_hint() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(state, _event("100", _T0, volume_hint=-1), _POLICY)


# --- 24. symbol mismatch -----------------------------------------------------------


def test_apply_price_update_rejects_symbol_mismatch() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(state, _event("100", _T0, symbol="MSFT"), _POLICY)


def test_apply_price_update_wrong_kind_is_rejected() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(
            state, _event("100", _T0, kind=UpdateKind.AUTHORITATIVE_SNAPSHOT), _POLICY
        )


def test_apply_authoritative_snapshot_wrong_kind_is_rejected() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_authoritative_snapshot(state, _event("100", _T0, kind=UpdateKind.PROVISIONAL))


# --- 25. Decimal precision -----------------------------------------------------------


def test_apply_price_update_preserves_decimal_precision_no_float_involved() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("303.9401", _T0), _POLICY)

    state = apply_price_update(state, _event("303.9402", _T0_PLUS_1), _POLICY)

    assert state.last_price == Decimal("303.9402")
    assert isinstance(state.last_price, Decimal)
    assert state.current_bar is not None
    assert state.current_bar.high == Decimal("303.9402")
    # A value with more decimal places than float could represent
    # exactly stays exact through the whole pipeline.
    precise = apply_price_update(state, _event("100.100000000000001", _NEXT_INTERVAL), _POLICY)
    assert precise.last_price == Decimal("100.100000000000001")


# --- Non-positive/non-finite price validation -----------------------------------


@pytest.mark.parametrize("bad_price", ["0", "-5", "-0.01"])
def test_apply_price_update_rejects_non_positive_price(bad_price: str) -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(state, _event(bad_price, _T0), _POLICY)


def test_apply_price_update_rejects_non_finite_price() -> None:
    state = bootstrap_state("AAPL")
    event = PriceUpdateEvent(symbol="AAPL", price=Decimal("NaN"), timestamp=_T0, source="x")

    with pytest.raises(InvalidPriceUpdateEventError):
        apply_price_update(state, event, _POLICY)


# --- IntervalPolicy (corrective review, task scope §7) ---------------------------


def test_apply_price_update_rejects_non_positive_interval_duration() -> None:
    state = bootstrap_state("AAPL")

    with pytest.raises(LiveStateError):
        apply_price_update(state, _event("100", _T0), IntervalPolicy(duration=timedelta(0)))


def test_apply_price_update_rejects_non_utc_interval_anchor() -> None:
    state = bootstrap_state("AAPL")
    bad_policy = IntervalPolicy(
        duration=timedelta(minutes=5), anchor=datetime(2026, 1, 1, tzinfo=_PLUS_3H)
    )

    with pytest.raises(LiveStateError):
        apply_price_update(state, _event("100", _T0), bad_policy)


def test_apply_price_update_rejects_naive_interval_anchor() -> None:
    state = bootstrap_state("AAPL")
    bad_policy = IntervalPolicy(duration=timedelta(minutes=5), anchor=datetime(2026, 1, 1))

    with pytest.raises(LiveStateError):
        apply_price_update(state, _event("100", _T0), bad_policy)


def test_apply_price_update_default_anchor_is_deterministic_epoch_aligned() -> None:
    """Default `IntervalPolicy` (epoch anchor) behavior is unchanged
    from before this corrective review — a fixed reference point
    produces the same, predictable boundary every time."""
    state = bootstrap_state("AAPL")

    result = apply_price_update(state, _event("100", _T0), IntervalPolicy(duration=timedelta(minutes=5)))

    assert result.current_bar is not None
    assert result.current_bar.interval_start == _T0


def test_apply_price_update_custom_anchor_shifts_interval_boundaries_predictably() -> None:
    """A non-default anchor changes where bar boundaries fall, in a
    fully deterministic, predictable way — this is the mechanism a
    future adapter would use to align bars to a real exchange session
    open without this domain knowing about exchange calendars."""
    # Anchor 2 minutes after _T0: under the default (epoch) anchor,
    # _T0 + 3 minutes floors to _T0 (still inside the [T0, T0+5) grid
    # cell). Under an anchor 2 minutes later, the grid cells shift by
    # 2 minutes, so the same timestamp now floors to (anchor - 5min).
    shifted_anchor = _T0 + timedelta(minutes=2)
    shifted_policy = IntervalPolicy(duration=timedelta(minutes=5), anchor=shifted_anchor)
    state = bootstrap_state("AAPL")

    event_time = _T0 + timedelta(minutes=3)  # 1 minute after shifted_anchor
    result = apply_price_update(state, _event("100", event_time), shifted_policy)

    assert result.current_bar is not None
    assert result.current_bar.interval_start == shifted_anchor

    # A default-anchored policy would have floored the same timestamp
    # to a different boundary (_T0), proving the anchor genuinely
    # changes alignment, not just an internal implementation detail.
    default_result = apply_price_update(
        bootstrap_state("AAPL"), _event("100", event_time), IntervalPolicy(duration=timedelta(minutes=5))
    )
    assert default_result.current_bar is not None
    assert default_result.current_bar.interval_start == _T0
    assert default_result.current_bar.interval_start != result.current_bar.interval_start


def test_apply_price_update_custom_anchor_still_does_not_fabricate_skipped_bars() -> None:
    shifted_policy = IntervalPolicy(duration=timedelta(minutes=5), anchor=_T0 + timedelta(minutes=2))
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), shifted_policy)

    state = apply_price_update(state, _event("120", _FAR_INTERVAL), shifted_policy)

    assert state.current_bar is not None
    assert state.last_closed_bar is not None
    # Exactly two bars exist in the whole state — no intermediate ones.
    assert state.current_bar.interval_start != state.last_closed_bar.interval_start


# --- with_connection_state / with_market_state independence -----------------------


def test_with_connection_state_never_touches_price_fields() -> None:
    state = bootstrap_state("AAPL")
    state = apply_price_update(state, _event("100", _T0), _POLICY)

    reconnecting = with_connection_state(state, ConnectionState.RECONNECTING)

    assert reconnecting.last_price == state.last_price
    assert reconnecting.current_bar == state.current_bar
    assert reconnecting.connection_state is ConnectionState.RECONNECTING
    assert state.connection_state is ConnectionState.CONNECTING  # original state untouched (immutability)


def test_with_market_state_never_touches_connection_state() -> None:
    state = bootstrap_state("AAPL")

    opened = with_market_state(state, MarketState.OPEN)

    assert opened.market_state is MarketState.OPEN
    assert opened.connection_state is ConnectionState.CONNECTING
