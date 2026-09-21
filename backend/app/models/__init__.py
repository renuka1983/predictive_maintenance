"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` so that
``Base.metadata.create_all()`` builds the full schema.
"""

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, new_uuid, utcnow
from app.models.feature import FeatureToggle
from app.models.machine import MACHINE_STATUSES, Machine
from app.models.maintenance import MAINTENANCE_TYPES, MaintenanceRecord
from app.models.production import ProductionBatch
from app.models.sensor import SENSOR_TYPES, SensorReading
from app.models.site import Site
from app.models.tenant import Tenant

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "new_uuid",
    "utcnow",
    "Tenant",
    "Machine",
    "MACHINE_STATUSES",
    "MaintenanceRecord",
    "MAINTENANCE_TYPES",
    "ProductionBatch",
    "SensorReading",
    "SENSOR_TYPES",
    "Site",
    "FeatureToggle",
]
