"""Maintenance history (CMMS) model - the Level 1 data foundation."""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MAINTENANCE_TYPES = ("planned", "preventive", "reactive", "predictive")


class MaintenanceRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One maintenance work order against a machine."""

    __tablename__ = "maintenance_records"
    __table_args__ = (
        Index("ix_maint_tenant_machine", "tenant_id", "machine_id"),
        Index("ix_maint_tenant_start", "tenant_id", "start_time"),
    )

    tenant_id = Column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    machine_id = Column(
        String(36), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )

    work_order_number = Column(String(80), nullable=True)
    maintenance_type = Column(String(30), nullable=False, default="reactive")
    failure_mode = Column(String(120), nullable=True, index=True)
    description = Column(Text, nullable=True)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)
    downtime_hours = Column(Float, nullable=False, default=0.0)
    labor_hours = Column(Float, nullable=False, default=0.0)

    labor_cost = Column(Float, nullable=False, default=0.0)
    parts_cost = Column(Float, nullable=False, default=0.0)
    total_cost = Column(Float, nullable=False, default=0.0)

    technician = Column(String(120), nullable=True)

    machine = relationship("Machine", back_populates="maintenance_records")

    @property
    def is_failure(self) -> bool:
        """Reactive work orders represent unplanned failures."""
        return self.maintenance_type == "reactive"
