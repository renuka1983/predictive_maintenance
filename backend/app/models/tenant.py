"""Tenant model - the root of multi-tenant isolation."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A customer organisation.

    Every other table carries a ``tenant_id`` foreign key back to this table;
    all queries must filter on it so that no data can cross tenant boundaries.
    """

    __tablename__ = "tenants"

    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True, index=True)
    industry = Column(String(100), nullable=True)
    contact_email = Column(String(200), nullable=True)

    subscription_tier = Column(String(50), nullable=False, default="free")
    is_active = Column(Boolean, nullable=False, default=True)

    # Cached result of the most recent maturity assessment.
    maturity_level = Column(Integer, nullable=False, default=0)
    maturity_score = Column(Float, nullable=False, default=0.0)
    last_assessed_at = Column(DateTime(timezone=True), nullable=True)

    machines = relationship(
        "Machine", back_populates="tenant", cascade="all, delete-orphan"
    )
    sites = relationship(
        "Site", back_populates="tenant", cascade="all, delete-orphan"
    )
    feature_toggles = relationship(
        "FeatureToggle", back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Tenant {self.slug} L{self.maturity_level}>"
