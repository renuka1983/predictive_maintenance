"""Feature access control.

Every maturity-gated endpoint funnels through :meth:`FeatureGate.require` so
that the 403 payload (including the upgrade path) is identical everywhere.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeatureToggle, Tenant
from app.schemas.tenant import FeatureListResponse, FeatureResponse
from app.services.feature_catalog import (
    FEATURES,
    FEATURES_BY_KEY,
    LEVEL_NAMES,
    Feature,
)


class FeatureGate:
    """Decide whether a tenant may use a given feature."""

    @staticmethod
    def _overrides(db: Session, tenant_id: str) -> Dict[str, FeatureToggle]:
        """Manual toggles, keyed by feature, that override level-based access."""
        stmt = select(FeatureToggle).where(
            FeatureToggle.tenant_id == tenant_id, FeatureToggle.source == "manual"
        )
        return {row.feature_key: row for row in db.execute(stmt).scalars()}

    @staticmethod
    def is_enabled(db: Session, tenant: Tenant, feature_key: str) -> bool:
        """True when ``tenant`` may use ``feature_key``.

        Access is granted by maturity level, but an explicit manual toggle
        (set by an admin, e.g. for a trial) always wins.
        """
        feature = FEATURES_BY_KEY.get(feature_key)
        if feature is None:
            raise KeyError(f"Unknown feature '{feature_key}'")

        override = FeatureGate._overrides(db, tenant.id).get(feature_key)
        if override is not None:
            return bool(override.is_enabled)
        return tenant.maturity_level >= feature.required_level

    @staticmethod
    def require(db: Session, tenant: Tenant, feature_key: str) -> None:
        """Raise 403 with an upgrade path unless the feature is available."""
        if FeatureGate.is_enabled(db, tenant, feature_key):
            return

        feature = FEATURES_BY_KEY[feature_key]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "feature_locked",
                "message": (
                    f"'{feature.name}' requires maturity Level "
                    f"{feature.required_level} ({LEVEL_NAMES[feature.required_level]}). "
                    f"Your tenant is at Level {tenant.maturity_level}."
                ),
                "feature_key": feature.key,
                "required_level": feature.required_level,
                "current_level": tenant.maturity_level,
            },
        )

    @staticmethod
    def _to_response(feature: Feature, enabled: bool) -> FeatureResponse:
        return FeatureResponse(
            feature_key=feature.key,
            name=feature.name,
            description=feature.description,
            required_level=feature.required_level,
            is_enabled=enabled,
            category=feature.category,
        )

    @staticmethod
    def list_features(db: Session, tenant: Tenant) -> FeatureListResponse:
        """Split the catalogue into what the tenant has and what is locked."""
        overrides = FeatureGate._overrides(db, tenant.id)
        enabled: List[FeatureResponse] = []
        locked: List[FeatureResponse] = []

        for feature in FEATURES:
            override = overrides.get(feature.key)
            is_on = (
                bool(override.is_enabled)
                if override is not None
                else tenant.maturity_level >= feature.required_level
            )
            (enabled if is_on else locked).append(
                FeatureGate._to_response(feature, is_on)
            )

        return FeatureListResponse(
            tenant_id=tenant.id,
            maturity_level=tenant.maturity_level,
            enabled=enabled,
            locked=locked,
        )

    @staticmethod
    def enabled_keys(db: Session, tenant: Tenant) -> List[str]:
        """Feature keys currently available to the tenant."""
        return [f.feature_key for f in FeatureGate.list_features(db, tenant).enabled]

    @staticmethod
    def sync_toggles(db: Session, tenant: Tenant) -> List[FeatureToggle]:
        """Persist the catalogue state for a tenant after an assessment.

        Manual overrides are left untouched; automatic rows are created or
        flipped to match the tenant's current level, stamping ``enabled_at``
        the first time a feature unlocks.
        """
        stmt = select(FeatureToggle).where(FeatureToggle.tenant_id == tenant.id)
        existing = {row.feature_key: row for row in db.execute(stmt).scalars()}
        now = datetime.now(timezone.utc)
        result: List[FeatureToggle] = []

        for feature in FEATURES:
            should_enable = tenant.maturity_level >= feature.required_level
            toggle = existing.get(feature.key)

            if toggle is None:
                toggle = FeatureToggle(
                    tenant_id=tenant.id,
                    feature_key=feature.key,
                    required_level=feature.required_level,
                    is_enabled=should_enable,
                    enabled_at=now if should_enable else None,
                    source="auto",
                )
                db.add(toggle)
            elif toggle.source == "auto":
                if should_enable and not toggle.is_enabled:
                    toggle.enabled_at = now
                toggle.is_enabled = should_enable
                toggle.required_level = feature.required_level
                db.add(toggle)

            result.append(toggle)

        db.commit()
        return result

    @staticmethod
    def set_override(
        db: Session, tenant: Tenant, feature_key: str, enabled: bool
    ) -> FeatureToggle:
        """Manually grant or revoke a feature regardless of maturity level."""
        feature = FEATURES_BY_KEY.get(feature_key)
        if feature is None:
            raise KeyError(f"Unknown feature '{feature_key}'")

        stmt = select(FeatureToggle).where(
            FeatureToggle.tenant_id == tenant.id,
            FeatureToggle.feature_key == feature_key,
        )
        toggle: Optional[FeatureToggle] = db.execute(stmt).scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if toggle is None:
            toggle = FeatureToggle(
                tenant_id=tenant.id,
                feature_key=feature_key,
                required_level=feature.required_level,
            )
        toggle.is_enabled = enabled
        toggle.source = "manual"
        toggle.enabled_at = now if enabled else None
        db.add(toggle)
        db.commit()
        db.refresh(toggle)
        return toggle
