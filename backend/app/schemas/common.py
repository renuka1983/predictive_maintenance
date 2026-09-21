"""Schemas shared across the API."""

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Message(BaseModel):
    """Simple message envelope for delete/ack responses."""

    detail: str


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard list envelope used by every collection endpoint."""

    items: List[T]
    total: int = Field(..., description="Total rows matching the filter")
    limit: int
    offset: int


class UpgradePath(BaseModel):
    """What a tenant must do to unlock the next maturity level."""

    current_level: int
    next_level: Optional[int] = None
    requirements: List[str] = []
    unlocks: List[str] = []
