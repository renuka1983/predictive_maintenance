"""Shared declarative base and column helpers."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp used as the default for audit columns."""
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    """Generate a string UUID primary key.

    String UUIDs keep the schema portable between PostgreSQL (production) and
    SQLite (tests) without dialect-specific column types.
    """
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` audit columns."""

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class UUIDPrimaryKeyMixin:
    """Adds a string UUID primary key."""

    id = Column(String(36), primary_key=True, default=new_uuid)
