"""Alembic environment — async PostgreSQL migration flow.

The database URL is never read from alembic.ini. It comes from
`trading_ai.config.get_required_database_url()`, i.e. from
`TRADING_AI_DATABASE_URL` in the environment, so credentials are never
stored in this repository. Unlike the FastAPI application, Alembic
*always* needs a real URL to do anything meaningful — running it
without `TRADING_AI_DATABASE_URL` set fails fast here with a clear,
credential-free error, both for online and offline (`--sql`) modes.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from trading_ai.config import get_required_database_url
from trading_ai.infrastructure.database.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No business models are mapped onto Base yet (bootstrap-only) — this
# metadata is currently empty, matching the empty baseline migration.
target_metadata = Base.metadata


def get_database_url() -> str:
    """Return the migration target URL, or raise a clear, credential-free error."""
    return get_required_database_url()


def run_migrations_offline() -> None:
    """Render migrations to SQL without connecting to any database."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Connect via an async engine and run migrations against a real DB."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
