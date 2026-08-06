"""Async session management.

Provides an explicit session factory and an explicit transactional
scope. No business logic lives here — this module only wires
infrastructure (ADR-0002: application/domain code does not depend on
framework or driver specifics beyond this boundary).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to `engine`.

    Called once per engine (normally from the FastAPI lifespan), not
    per request.
    """
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Explicit transactional boundary: commit on success, rollback on error.

    Callers own when a transaction starts and ends — no implicit,
    ambient transaction is created elsewhere.
    """
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
