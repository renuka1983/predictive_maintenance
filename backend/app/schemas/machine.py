"""Machine request/response schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.machine import MACHINE_STATUSES


class MachineBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    machine_type: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=120)
    model_number: Optional[str] = Field(None, max_length=120)
    site: Optional[str] = Field(None, max_length=120)
    production_line: Optional[str] = Field(None, max_length=120)
    line_position: Optional[int] = Field(None, ge=0)
    criticality: int = Field(3, ge=1, le=5)
    status: str = Field("operational")
    installation_date: Optional[date] = None
    hourly_output_units: float = Field(0.0, ge=0)
    hourly_downtime_cost: float = Field(0.0, ge=0)
    has_sensors: bool = False

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in MACHINE_STATUSES:
            raise ValueError(f"status must be one of {MACHINE_STATUSES}")
        return value


class MachineCreate(MachineBase):
    machine_code: str = Field(..., min_length=1, max_length=60)


class MachineUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    machine_type: Optional[str] = None
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    site: Optional[str] = None
    production_line: Optional[str] = None
    line_position: Optional[int] = Field(None, ge=0)
    criticality: Optional[int] = Field(None, ge=1, le=5)
    status: Optional[str] = None
    installation_date: Optional[date] = None
    hourly_output_units: Optional[float] = Field(None, ge=0)
    hourly_downtime_cost: Optional[float] = Field(None, ge=0)
    has_sensors: Optional[bool] = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value):
        if value is not None and value not in MACHINE_STATUSES:
            raise ValueError(f"status must be one of {MACHINE_STATUSES}")
        return value


class MachineResponse(MachineBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    machine_code: str
    created_at: datetime
    updated_at: datetime


class MachineStatus(BaseModel):
    """Live health summary for one machine (content varies by maturity level)."""

    machine_id: str
    machine_code: str
    name: str
    status: str
    criticality: int
    days_since_last_maintenance: Optional[int] = None
    maintenance_count: int = 0
    failure_count: int = 0
    total_downtime_hours: float = 0.0
    total_maintenance_cost: float = 0.0
    mtbf_hours: Optional[float] = None
    health_score: float = Field(100.0, ge=0, le=100)
