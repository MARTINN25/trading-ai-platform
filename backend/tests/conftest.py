"""Shared test setup.

Deliberately does *not* set a default `TRADING_AI_DATABASE_URL`. The
application must be importable and `/health` usable without it
(ADR-0009, §41), and the normal test suite must actually exercise
that — hiding a missing required setting behind a fake default here
would defeat the point of testing it. Tests that need a value set it
explicitly via `monkeypatch`; `/ready`-success tests override the
readiness dependency instead of touching a real database.
"""

from __future__ import annotations
