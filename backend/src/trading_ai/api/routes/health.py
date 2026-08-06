"""Liveness-style health endpoint (ADR-0009, §41).

Deliberately performs no dependency checks (no database, no external
calls) — this is a lightweight liveness signal, not a readiness check.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}
