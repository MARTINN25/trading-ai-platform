"""Small, provider-agnostic live-stream transport protocol (Phase 2C.2).

`LiveMarketManager` (`live_manager.py`) depends only on this `Protocol`,
never on `TwelveDataStreamClient` (`twelve_data_stream.py`) concretely —
the same isolation pattern already used for `llm_gateway`/`sources`
elsewhere in this codebase (ADR-0007 §20-21), applied here at a much
smaller scale (task scope §20: "we currently have one provider... a
small adapter protocol/interface is enough" — deliberately not a
larger provider-framework abstraction).

This module defines no I/O, no provider field names, no domain types —
just the shape a live-stream transport must satisfy to be usable by
the manager, which is what makes the manager testable with a fake
transport (no real network) in `test_live_manager.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class LiveProviderCapabilityError(Exception):
    """Raised by `connect()` to signal a *structural*, not transient,
    reason streaming cannot work — e.g. the account/plan does not
    include WebSocket access (task scope §7: "if provider refuses
    WebSocket due to account/plan: record a structured capability
    failure... do not retry aggressively forever").

    Deliberately defined here, not in a concrete provider module: this
    is how `LiveMarketManager` distinguishes "stop retrying, fall back
    to polling for good" from an ordinary transient connection failure
    (network blip, temporary outage) *without ever importing a
    provider-specific exception type* — `TwelveDataStreamClient` is
    responsible for translating whatever provider-specific signal it
    receives (e.g. an HTTP 401/403 handshake rejection) into this one
    provider-agnostic error (task scope §20: the manager must not
    depend on concrete Twelve Data internals).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LiveStreamClientLike(Protocol):
    """What `LiveMarketManager` needs from any live-stream transport.

    Every method is `async` — a real implementation (e.g.
    `TwelveDataStreamClient`) performs network I/O; a test fake performs
    none. `receive()` is expected to be called in a loop by the caller
    (mirrors the underlying `websockets` library's own iteration model)
    and to raise on connection loss/closure — it does not return a
    sentinel "closed" value, so the manager's reconnect loop is driven
    by exception handling, not by polling a status flag.
    """

    async def connect(self) -> None:
        """Establish the underlying connection and authenticate.

        Raises on failure (auth rejected, network error, connection
        refused) — the manager interprets any exception here as a
        connection attempt failure subject to the reconnect/backoff
        policy (task scope §16), not a fatal, unrecoverable condition.
        """
        ...

    async def subscribe(self, symbols: Sequence[str]) -> None:
        """Subscribe to one or more symbols on the already-connected transport."""
        ...

    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        """Unsubscribe one or more symbols, if the transport supports it."""
        ...

    async def send_heartbeat(self) -> None:
        """Send whatever keep-alive message the transport's provider requires."""
        ...

    async def receive(self) -> object:
        """Return one already-JSON-decoded raw provider frame.

        The manager never receives raw bytes/text here — decoding is
        the transport's job, so a malformed-JSON frame is a transport-
        level exception (mirrors what `receive()` on a real websocket
        connection would raise for that class of failure), while a
        well-formed-but-unrecognized *event* is a normal, non-exceptional
        value the manager's own normalization step decides how to
        handle (task scope §19).
        """
        ...

    async def close(self) -> None:
        """Close the connection. Must be safe to call even if `connect()`
        never succeeded or was never called (idempotent cleanup)."""
        ...
