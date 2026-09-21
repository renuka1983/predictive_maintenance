"""Maintenance request/response schemas."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.maintenance import MAINTENANCE_TYPES


class MaintenanceBase(BaseModel):
    machine_id: str
    work_order_number: Optional[str] = Field(None, max_length=80)
    maintenance_type: str = Field("reactive")
    failure_mode: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    downtime_hours: float = Field(0.0, ge=0)
    labor_hours: float = Field(0.0, ge=0)
    labor_cost: float = Field(0.0, ge=0)
    parts_cost: float = Field(0.0, ge=0)
    total_cost: Optional[float] = Field(None, ge=0)
    technician: Optional[str] = Field(None, max_length=120)

    @field_validator("maintenance_type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        if value not in MAINTENANCE_TYPES:
            raise ValueError(f"maintenance_type must be one of {MAINTENANCE_TYPES}")
        return value

    @model_validator(mode="after")
    def _check_window_and_cost(self):
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time must not be before start_time")
        if self.total_cost is None:
            self.total_cost = round(self.labor_cost + self.parts_cost, 2)
        return self


class MaintenanceCreate(MaintenanceBase):
    pass


class MaintenanceUpdate(BaseModel):
    work_order_number: Optional[str] = None
    maintenance_type: Optional[str] = None
    failure_mode: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    downtime_hours: Optional[float] = Field(None, ge=0)
    labor_hours: Optional[float] = Field(None, ge=0)
    labor_cost: Optional[float] = Field(None, ge=0)
    parts_cost: Optional[float] = Field(None, ge=0)
    total_cost: Optional[float] = Field(None, ge=0)
    technician: Optional[str] = None

    @field_validator("maintenance_type")
    @classmethod
    def _validate_type(cls, value):
        if value is not None and value not in MAINTENANCE_TYPES:
            raise ValueError(f"maintenance_type must be one of {MAINTENANCE_TYPES}")
        return value


class MaintenanceResponse(MaintenanceBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime


class MaintenanceStats(BaseModel):
    """Level 1 descriptive analytics over the maintenance log."""

    tenant_id: str
    window_days: int
    total_records: int
    planned_count: int
    reactive_count: int
    planned_ratio: float = Field(..., ge=0, le=1)
    total_downtime_hours: float
    total_cost: float
    labor_cost: float
    parts_cost: float
    mean_repair_hours: float
    mtbf_hours: Optional[float] = None
    cost_per_machine: float
    top_failure_modes: List[Dict[str, object]] = []
    monthly_trend: List[Dict[str, object]] = []
