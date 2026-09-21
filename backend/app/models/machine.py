"""Machine (manufacturing asset) model."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MACHINE_STATUSES = ("operational", "degraded", "maintenance", "down", "retired")


class Machine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single piece of production equipment belonging to one tenant."""

    __tablename__ = "machines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "machine_code", name="uq_machine_tenant_code"),
        Index("ix_machines_tenant_line", "tenant_id", "production_line"),
    )

    tenant_id = Column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )

    machine_code = Column(String(60), nullable=False)
    name = Column(String(200), nullable=False)
    machine_type = Column(String(100), nullable=True)
    manufacturer = Column(String(120), nullable=True)
    model_number = Column(String(120), nullable=True)

    # Level 2+ context: where the machine sits in the production flow.
    site = Column(String(120), nullable=True, index=True)
    production_line = Column(String(120), nullable=True)
    line_position = Column(Integer, nullable=True)

    criticality = Column(Integer, nullable=False, default=3)  # 1 (low) - 5 (critical)
    status = Column(String(30), nullable=False, default="operational")
    installation_date = Column(Date, nullable=True)

    # Economics used by cascade-impact and ROI calculations.
    hourly_output_units = Column(Float, nullable=False, default=0.0)
    hourly_downtime_cost = Column(Float, nullable=False, default=0.0)

    # Level 3 flag: does this asset stream IoT telemetry?
    has_sensors = Column(Boolean, nullable=False, default=False)

    tenant = relationship("Tenant", back_populates="machines")
    maintenance_records = relationship(
        "MaintenanceRecord", back_populates="machine", cascade="all, delete-orphan"
    )
    production_batches = relationship(
        "ProductionBatch", back_populates="machine", cascade="all, delete-orphan"
    )
    sensor_readings = relationship(
        "SensorReading", back_populates="machine", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Machine {self.machine_code} {self.status}>"
