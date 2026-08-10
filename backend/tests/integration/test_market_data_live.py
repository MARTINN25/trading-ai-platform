"""Opt-in smoke test against the real Twelve Data API.

Deliberately its own file with only `@pytest.mark.live_provider` on the
one test — never the module-level `pytestmark = pytest.mark.integration`
used by `test_watchlist_integration.py`. If this file carried that
marker too, a plain `pytest -m integration` run would also fire a real
external HTTP call, which the task explicitly rules out ("не делать
live external-provider tests частью обычного pytest suite").

Run explicitly:

    TRADING_AI_LIVE_MARKET_DATA_API_KEY=... \\
        python -m pytest -m live_provider tests/integration -v
"""

from __future__ import annotations

import asyncio
import os

import pytest

from trading_ai.market_data.gateway import TwelveDataGateway

_LIVE_API_KEY = os.environ.get("TRADING_AI_LIVE_MARKET_DATA_API_KEY")


@pytest.mark.live_provider
@pytest.mark.skipif(
    not _LIVE_API_KEY,
    reason=(
        "TRADING_AI_LIVE_MARKET_DATA_API_KEY is not set - skipping live "
        "market-data provider smoke test (opt-in only)."
    ),
)
def test_live_market_data_quote_smoke() -> None:
    assert _LIVE_API_KEY is not None
    gateway = TwelveDataGateway(api_key=_LIVE_API_KEY)

    quote = asyncio.run(gateway.get_quote("AAPL"))

    assert quote.ticker == "AAPL"
    assert quote.price > 0
    assert quote.source == "twelvedata"
    assert quote.as_of.tzinfo is not None
