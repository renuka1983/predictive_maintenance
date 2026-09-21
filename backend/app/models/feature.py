"""Feature toggle model - tracks which capabilities a tenant has unlocked."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FeatureToggle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Persisted state of one feature for one tenant.

    Toggles are synchronised from the feature catalogue whenever a maturity
    assessment runs, which gives an audit trail of when each capability
    became available to a customer.
    """

    __tablename__ = "feature_toggles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_key", name="uq_feature_tenant_key"),
    )

    tenant_id = Column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    feature_key = Column(String(100), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=False)
    required_level = Column(Integer, nullable=False, default=0)
    enabled_at = Column(DateTime(timezone=True), nullable=True)
    # "auto" = granted by maturity assessment, "manual" = admin override.
    source = Column(String(20), nullable=False, default="auto")

    tenant = relationship("Tenant", back_populates="feature_toggles")
