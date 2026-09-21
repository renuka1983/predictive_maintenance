"""API routers, one module per resource."""

from app.routers import (
    analytics,
    machines,
    maintenance,
    production,
    sensors,
    sites,
    tenants,
)

__all__ = [
    "tenants",
    "machines",
    "maintenance",
    "production",
    "analytics",
    "sensors",
    "sites",
]
