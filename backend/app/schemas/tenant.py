"""Tenant request/response schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import UpgradePath


class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[EmailStr] = None
    subscription_tier: str = Field("free", max_length=50)


class TenantCreate(TenantBase):
    slug: str = Field(
        ...,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="URL-safe unique identifier, lowercase letters/digits/hyphens",
    )


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    contact_email: Optional[EmailStr] = None
    subscription_tier: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class TenantResponse(TenantBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    is_active: bool
    maturity_level: int
    maturity_score: float
    last_assessed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MaturityDimension(BaseModel):
    """Score breakdown for one of the four maturity dimensions."""

    name: str
    score: float = Field(..., ge=0, le=25)
    max_score: float = 25.0
    detail: str


class MaturityAssessment(BaseModel):
    """Full result of a maturity assessment run."""

    tenant_id: str
    level: int = Field(..., ge=0, le=4)
    level_name: str
    score: float = Field(..., ge=0, le=100)
    dimensions: List[MaturityDimension]
    assessed_at: datetime
    upgrade_path: UpgradePath


class FeatureResponse(BaseModel):
    """One feature and whether the tenant can use it."""

    model_config = ConfigDict(from_attributes=True)

    feature_key: str
    name: str
    description: str
    required_level: int
    is_enabled: bool
    category: str


class FeatureListResponse(BaseModel):
    tenant_id: str
    maturity_level: int
    enabled: List[FeatureResponse]
    locked: List[FeatureResponse]
