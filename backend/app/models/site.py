"""Site model - first-class plants for Level 4 enterprise rollups.

``Machine.site`` remains a plain string so that Level 1-3 tenants need no
site registry at all. This table is *additive*: it attaches optional metadata
(region, country, timezone) to a site name so enterprise tenants can roll up
and benchmark by region. Analytics fall back to the bare machine string when
no matching row exists, which keeps every existing tenant working unchanged.
"""

from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Site(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A physical plant belonging to one tenant."""

    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_site_tenant_name"),
    )

    tenant_id = Column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )

    # Must match Machine.site exactly; that string is the join key.
    name = Column(String(120), nullable=False)
    display_name = Column(String(200), nullable=True)

    region = Column(String(120), nullable=True, index=True)
    country = Column(String(80), nullable=True)
    timezone = Column(String(60), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    tenant = relationship("Tenant", back_populates="sites")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Site {self.name} ({self.region})>"
