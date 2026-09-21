"""Production batch (MES/ERP) model - unlocks Level 2 analytics."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProductionBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A production run on a machine, with quality and throughput outcomes."""

    __tablename__ = "production_batches"
    __table_args__ = (
        Index("ix_batch_tenant_machine", "tenant_id", "machine_id"),
        Index("ix_batch_tenant_start", "tenant_id", "start_time"),
    )

    tenant_id = Column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    machine_id = Column(
        String(36), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False
    )

    batch_number = Column(String(80), nullable=True)
    product_code = Column(String(80), nullable=True, index=True)

    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=True)

    planned_units = Column(Integer, nullable=False, default=0)
    produced_units = Column(Integer, nullable=False, default=0)
    defective_units = Column(Integer, nullable=False, default=0)
    scrap_units = Column(Integer, nullable=False, default=0)

    planned_runtime_minutes = Column(Float, nullable=False, default=0.0)
    actual_runtime_minutes = Column(Float, nullable=False, default=0.0)
    downtime_minutes = Column(Float, nullable=False, default=0.0)

    machine = relationship("Machine", back_populates="production_batches")

    @property
    def good_units(self) -> int:
        return max(self.produced_units - self.defective_units - self.scrap_units, 0)

    @property
    def yield_rate(self) -> float:
        """Share of produced units that passed quality control (0-1)."""
        if not self.produced_units:
            return 0.0
        return self.good_units / self.produced_units

    @property
    def availability(self) -> float:
        """OEE availability component (0-1)."""
        if not self.planned_runtime_minutes:
            return 0.0
        return min(self.actual_runtime_minutes / self.planned_runtime_minutes, 1.0)

    @property
    def performance(self) -> float:
        """OEE performance component (0-1)."""
        if not self.planned_units:
            return 0.0
        return min(self.produced_units / self.planned_units, 1.0)

    @property
    def oee(self) -> float:
        """Overall Equipment Effectiveness (0-1)."""
        return self.availability * self.performance * self.yield_rate
