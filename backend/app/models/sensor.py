"""IoT sensor telemetry model - unlocks Level 3 analytics."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base, utcnow

SENSOR_TYPES = (
    "vibration",
    "temperature",
    "pressure",
    "current",
    "acoustic",
    "rpm",
    "oil_quality",
)


class SensorReading(Base):
    """A single timestamped sensor measurement.

    This is the highest-volume table in the system, so it uses a plain
    autoincrementing integer key and composite indexes tuned for the
    "latest readings for a machine" access pattern.
    """

    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_tenant_machine_time", "tenant_id", "machine_id", "recorded_at"),
        Index("ix_sensor_tenant_type_time", "tenant_id", "sensor_type", "recorded_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    machine_id = Column(
        String(36), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )

    sensor_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(30), nullable=True)
    quality = Column(String(20), nullable=False, default="good")  # good/suspect/bad

    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    machine = relationship("Machine", back_populates="sensor_readings")
