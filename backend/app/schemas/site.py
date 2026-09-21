"""Site schemas (Level 4 enterprise)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SiteBase(BaseModel):
    display_name: Optional[str] = Field(None, max_length=200)
    region: Optional[str] = Field(None, max_length=120)
    country: Optional[str] = Field(None, max_length=80)
    timezone: Optional[str] = Field(None, max_length=60)
    is_active: bool = True


class SiteCreate(SiteBase):
    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Must match the 'site' value on this tenant's machines",
    )


class SiteUpdate(SiteBase):
    display_name: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    is_active: Optional[bool] = None


class SiteResponse(SiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    created_at: datetime
    updated_at: datetime


class SiteWithStats(SiteResponse):
    """A registered site plus how many machines currently reference it."""

    machine_count: int = 0
