"""In-process, short-lived cache of just-generated analyses awaiting an
explicit save (Product Owner decision: explicit "Сохранить инсайт"
action, not auto-save — see task scope §2).

Exists solely so `POST /instruments/{ticker}/insights` never has to
trust client-supplied analysis content for provenance-sensitive fields
(task scope §12: "не позволять frontend подделать provider/model/
provenance"). The generate endpoint stores its own result here under a
fresh opaque token and returns *only the token* as the thing the save
call must present back — every other field the save call would
otherwise need comes from this server-held copy, never from the
request body.

Not Redis, not a worker, not a durable queue (task scope §29) — a
plain in-process dict is sufficient because the whole platform is a
single local-user, single-process MVP deployment (`PRODUCT_SCOPE.md`
§21, `ADR-0008`). A restart between generate and save simply loses the
pending entry — the user regenerates; no data was ever promised saved,
so this is a safe, honest degradation, not a data-loss bug.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from trading_ai.ai.types import InstrumentAnalysis

# Generous enough for a human to read a generated analysis and decide
# to save it, small enough to bound memory in the pathological case of
# many generations never being saved.
_TTL_SECONDS = 30 * 60
_MAX_ENTRIES = 50


@dataclass(frozen=True, slots=True)
class _Entry:
    ticker: str
    analysis: InstrumentAnalysis
    expires_at: float


class PendingAnalysisCache:
    """One instance lives on `app.state` for the process lifetime
    (`main.py` lifespan) — never recreated per-request."""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def put(self, ticker: str, analysis: InstrumentAnalysis) -> str:
        self._sweep_expired()
        if len(self._entries) >= _MAX_ENTRIES:
            oldest_token = min(self._entries, key=lambda token: self._entries[token].expires_at)
            del self._entries[oldest_token]
        token = uuid.uuid4().hex
        self._entries[token] = _Entry(
            ticker=ticker, analysis=analysis, expires_at=time.monotonic() + _TTL_SECONDS
        )
        return token

    def pop(self, ticker: str, token: str) -> InstrumentAnalysis | None:
        """Single-use: removes the entry regardless of outcome, so a
        second save attempt with the same token never re-saves (task
        scope §16: "не позволять дублирующую запись при случайном
        повторном click"). Returns `None` if the token is unknown,
        expired, or was issued for a different ticker.
        """
        entry = self._entries.pop(token, None)
        if entry is None:
            return None
        if entry.expires_at < time.monotonic():
            return None
        if entry.ticker != ticker:
            return None
        return entry.analysis

    def _sweep_expired(self) -> None:
        now = time.monotonic()
        expired = [token for token, entry in self._entries.items() if entry.expires_at < now]
        for token in expired:
            del self._entries[token]
