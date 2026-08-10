"""Regression test for a real secret-leakage incident found during live
verification: httpx's own INFO-level request logging writes the full
request URL (including any query-param API key) into our structured
logs unless explicitly silenced. `configure_logging()` must raise the
httpx/httpcore logger levels so that never happens, regardless of
which module in the app happens to use httpx.
"""

from __future__ import annotations

import logging

from trading_ai.logging import configure_logging


def test_configure_logging_silences_httpx_info_logging() -> None:
    configure_logging("INFO")

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


def test_configure_logging_silences_even_when_debug_requested() -> None:
    """The app's own DEBUG level must not accidentally re-enable
    httpx's verbose request logging — the two are independent."""
    configure_logging("DEBUG")

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
