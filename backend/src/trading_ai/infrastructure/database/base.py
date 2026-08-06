"""Shared SQLAlchemy declarative base.

No business model is mapped here (ADR-0004 does not select a data
model in this bootstrap). This exists only so Alembic has a
`target_metadata` to point at; the metadata is currently empty.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for future ORM models."""
