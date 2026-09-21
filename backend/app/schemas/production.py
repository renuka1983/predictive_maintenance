"""Production batch request/response schemas (Level 2+)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductionBase(BaseModel):
    machine_id: str
    batch_number: Optional[str] = Field(None, max_length=80)
    product_code: Optional[str] = Field(None, max_length=80)
    start_time: datetime
    end_time: Optional[datetime] = None
    planned_units: int = Field(0, ge=0)
    produced_units: int = Field(0, ge=0)
    defective_units: int = Field(0, ge=0)
    scrap_units: int = Field(0, ge=0)
    planned_runtime_minutes: float = Field(0.0, ge=0)
    actual_runtime_minutes: float = Field(0.0, ge=0)
    downtime_minutes: float = Field(0.0, ge=0)

    @model_validator(mode="after")
    def _check_units(self):
        if self.defective_units + self.scrap_units > self.produced_units:
            raise ValueError(
                "defective_units + scrap_units cannot exceed produced_units"
            )
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time must not be before start_time")
        return self


class ProductionCreate(ProductionBase):
    pass


class ProductionUpdate(BaseModel):
    batch_number: Optional[str] = None
    product_code: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    planned_units: Optional[int] = Field(None, ge=0)
    produced_units: Optional[int] = Field(None, ge=0)
    defective_units: Optional[int] = Field(None, ge=0)
    scrap_units: Optional[int] = Field(None, ge=0)
    planned_runtime_minutes: Optional[float] = Field(None, ge=0)
    actual_runtime_minutes: Optional[float] = Field(None, ge=0)
    downtime_minutes: Optional[float] = Field(None, ge=0)


class ProductionResponse(ProductionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    yield_rate: float
    oee: float
    created_at: datetime
    updated_at: datetime


class LineStationSummary(BaseModel):
    """One machine's contribution to a production line."""

    machine_id: str
    machine_code: str
    name: str
    line_position: Optional[int] = None
    status: str
    criticality: int
    oee: float
    yield_rate: float
    produced_units: int
    downtime_minutes: float
    is_bottleneck: bool = False


class ProductionLineView(BaseModel):
    """Level 2 view of a whole production line in flow order."""

    tenant_id: str
    production_line: str
    window_days: int
    stations: List[LineStationSummary]
    line_oee: float
    bottleneck_machine_id: Optional[str] = None
    total_produced_units: int
    total_downtime_minutes: float
