"""Sensor telemetry schemas (Level 3+)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.sensor import SENSOR_TYPES


class SensorReadingBase(BaseModel):
    machine_id: str
    sensor_type: str
    value: float
    unit: Optional[str] = Field(None, max_length=30)
    quality: str = Field("good")
    recorded_at: Optional[datetime] = None

    @field_validator("sensor_type")
    @classmethod
    def _validate_sensor_type(cls, value: str) -> str:
        if value not in SENSOR_TYPES:
            raise ValueError(f"sensor_type must be one of {SENSOR_TYPES}")
        return value

    @field_validator("quality")
    @classmethod
    def _validate_quality(cls, value: str) -> str:
        if value not in ("good", "suspect", "bad"):
            raise ValueError("quality must be one of ('good', 'suspect', 'bad')")
        return value


class SensorReadingCreate(SensorReadingBase):
    pass


class SensorBatchCreate(BaseModel):
    """Bulk ingest payload - IoT gateways push readings in batches."""

    readings: List[SensorReadingCreate] = Field(..., min_length=1, max_length=5000)


class SensorReadingResponse(SensorReadingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    recorded_at: datetime


class SensorSeriesPoint(BaseModel):
    recorded_at: datetime
    value: float


class SensorSeries(BaseModel):
    """Downsampled time series for charting."""

    machine_id: str
    sensor_type: str
    unit: Optional[str] = None
    points: List[SensorSeriesPoint]
    mean: float
    minimum: float
    maximum: float


class SensorSnapshot(BaseModel):
    """Latest value per sensor type for one machine."""

    machine_id: str
    machine_code: str
    captured_at: Optional[datetime] = None
    readings: List[SensorReadingResponse]
