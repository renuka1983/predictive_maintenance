"""Tenant maturity assessment.

Maturity is scored across four 25-point dimensions (CMMS, production, IoT and
data quality) for a 100-point total, and the level (0-4) is derived from which
*data domains* are actually present - not from the score alone. This keeps
level assignment explainable to a customer: you reach Level 2 because you sent
production data, not because a number crossed a line.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Machine,
    MaintenanceRecord,
    ProductionBatch,
    SensorReading,
    Tenant,
)
from app.schemas.common import UpgradePath
from app.schemas.tenant import MaturityAssessment, MaturityDimension
from app.services.feature_catalog import LEVEL_NAMES, features_unlocked_at


class MaturityService:
    """Assess how much of the platform a tenant's data can support."""

    @staticmethod
    def _count(db: Session, model, tenant_id: str) -> int:
        stmt = select(func.count()).select_from(model).where(
            model.tenant_id == tenant_id
        )
        return int(db.execute(stmt).scalar_one() or 0)

    @staticmethod
    def _score_cmms(db: Session, tenant_id: str, machine_count: int) -> MaturityDimension:
        """CMMS dimension: enough maintenance records, spread over machines."""
        records = MaturityService._count(db, MaintenanceRecord, tenant_id)
        target = settings.min_maintenance_records
        volume = min(records / target, 1.0) if target else 0.0

        covered = 0
        if machine_count:
            stmt = (
                select(func.count(func.distinct(MaintenanceRecord.machine_id)))
                .where(MaintenanceRecord.tenant_id == tenant_id)
            )
            covered = int(db.execute(stmt).scalar_one() or 0)
        coverage = (covered / machine_count) if machine_count else 0.0

        score = round(25 * (0.6 * volume + 0.4 * coverage), 2)
        return MaturityDimension(
            name="cmms",
            score=score,
            detail=(
                f"{records} maintenance records across {covered}/{machine_count} "
                f"machines (target {target}+ records)"
            ),
        )

    @staticmethod
    def _score_production(db: Session, tenant_id: str) -> MaturityDimension:
        """Production dimension: MES/ERP batches available for ML features."""
        batches = MaturityService._count(db, ProductionBatch, tenant_id)
        target = settings.min_production_batches
        volume = min(batches / target, 1.0) if target else 0.0
        score = round(25 * volume, 2)
        return MaturityDimension(
            name="production",
            score=score,
            detail=f"{batches} production batches (target {target}+)",
        )

    @staticmethod
    def _score_sensors(
        db: Session, tenant_id: str, machine_count: int
    ) -> MaturityDimension:
        """IoT dimension: reading volume plus how many machines are instrumented."""
        readings = MaturityService._count(db, SensorReading, tenant_id)
        target = settings.min_sensor_readings
        volume = min(readings / target, 1.0) if target else 0.0

        instrumented = 0
        if machine_count:
            stmt = select(func.count()).select_from(Machine).where(
                Machine.tenant_id == tenant_id, Machine.has_sensors.is_(True)
            )
            instrumented = int(db.execute(stmt).scalar_one() or 0)
        coverage = (instrumented / machine_count) if machine_count else 0.0

        score = round(25 * (0.5 * volume + 0.5 * coverage), 2)
        return MaturityDimension(
            name="iot_sensors",
            score=score,
            detail=(
                f"{readings} readings from {instrumented}/{machine_count} "
                f"instrumented machines"
            ),
        )

    @staticmethod
    def _score_quality(db: Session, tenant_id: str, machine_count: int) -> MaturityDimension:
        """Data quality: completeness and recency of what has been supplied."""
        if machine_count == 0:
            return MaturityDimension(
                name="data_quality", score=0.0, detail="No machines registered"
            )

        checks: List[Tuple[str, float]] = []

        # 1. Are machines described well enough to analyse (line + economics)?
        stmt = select(func.count()).select_from(Machine).where(
            Machine.tenant_id == tenant_id,
            Machine.production_line.isnot(None),
            Machine.hourly_downtime_cost > 0,
        )
        described = int(db.execute(stmt).scalar_one() or 0)
        checks.append(("machine metadata", described / machine_count))

        # 2. Do maintenance records carry costs and failure modes?
        total_records = MaturityService._count(db, MaintenanceRecord, tenant_id)
        if total_records:
            stmt = select(func.count()).select_from(MaintenanceRecord).where(
                MaintenanceRecord.tenant_id == tenant_id,
                MaintenanceRecord.total_cost > 0,
                MaintenanceRecord.failure_mode.isnot(None),
            )
            complete = int(db.execute(stmt).scalar_one() or 0)
            checks.append(("record completeness", complete / total_records))
        else:
            checks.append(("record completeness", 0.0))

        # 3. Is the data fresh (activity in the last 90 days)?
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        stmt = select(func.count()).select_from(MaintenanceRecord).where(
            MaintenanceRecord.tenant_id == tenant_id,
            MaintenanceRecord.start_time >= cutoff,
        )
        recent = int(db.execute(stmt).scalar_one() or 0)
        checks.append(("recency", 1.0 if recent else 0.0))

        ratio = sum(value for _, value in checks) / len(checks)
        score = round(25 * ratio, 2)
        detail = ", ".join(f"{name} {value:.0%}" for name, value in checks)
        return MaturityDimension(name="data_quality", score=score, detail=detail)

    @staticmethod
    def _derive_level(
        machine_count: int,
        cmms: MaturityDimension,
        production: MaturityDimension,
        sensors: MaturityDimension,
        site_count: int,
    ) -> int:
        """Map dimension scores onto a maturity level.

        Each level needs the previous level's data domain to be materially
        populated (>= 60% of its dimension score), so a tenant cannot skip a
        level by dumping sensor data with no maintenance history.
        """
        if machine_count == 0 or cmms.score < 12.5:
            return 0
        level = 1
        if production.score >= 15.0:
            level = 2
            if sensors.score >= 15.0:
                level = 3
                if site_count > 1:
                    level = 4
        return level

    @staticmethod
    def _upgrade_path(
        level: int,
        cmms: MaturityDimension,
        production: MaturityDimension,
        sensors: MaturityDimension,
        site_count: int,
    ) -> UpgradePath:
        """Explain, in customer terms, what the next level requires."""
        if level >= 4:
            return UpgradePath(current_level=4, next_level=None, requirements=[], unlocks=[])

        next_level = level + 1
        requirements: List[str] = []
        if next_level == 1:
            requirements.append(
                "Register your machines and import at least "
                f"{settings.min_maintenance_records} maintenance work orders"
            )
        elif next_level == 2:
            requirements.append(
                f"Import at least {settings.min_production_batches} production "
                "batches from your MES/ERP"
            )
            if cmms.score < 20:
                requirements.append("Improve CMMS coverage across all machines")
        elif next_level == 3:
            requirements.append(
                f"Stream at least {settings.min_sensor_readings} sensor readings"
            )
            requirements.append(
                "Flag instrumented machines with has_sensors so coverage is at least "
                f"{settings.min_sensor_machine_coverage:.0%}"
            )
        elif next_level == 4:
            requirements.append("Onboard a second site to enable multi-site rollups")
            if site_count <= 1:
                requirements.append("Set the site field on machines at each plant")

        return UpgradePath(
            current_level=level,
            next_level=next_level,
            requirements=requirements,
            unlocks=[f.name for f in features_unlocked_at(next_level)],
        )

    @classmethod
    def assess(cls, db: Session, tenant: Tenant, persist: bool = True) -> MaturityAssessment:
        """Run a full assessment for ``tenant``.

        When ``persist`` is true the tenant row is updated with the new level
        and score so that gating decisions elsewhere are a single column read.
        """
        machine_count = cls._count(db, Machine, tenant.id)

        site_stmt = (
            select(func.count(func.distinct(Machine.site)))
            .where(Machine.tenant_id == tenant.id, Machine.site.isnot(None))
        )
        site_count = int(db.execute(site_stmt).scalar_one() or 0)

        cmms = cls._score_cmms(db, tenant.id, machine_count)
        production = cls._score_production(db, tenant.id)
        sensors = cls._score_sensors(db, tenant.id, machine_count)
        quality = cls._score_quality(db, tenant.id, machine_count)

        dimensions = [cmms, production, sensors, quality]
        score = round(sum(d.score for d in dimensions), 2)
        level = cls._derive_level(machine_count, cmms, production, sensors, site_count)
        assessed_at = datetime.now(timezone.utc)

        if persist:
            tenant.maturity_level = level
            tenant.maturity_score = score
            tenant.last_assessed_at = assessed_at
            db.add(tenant)
            db.commit()
            db.refresh(tenant)

        return MaturityAssessment(
            tenant_id=tenant.id,
            level=level,
            level_name=LEVEL_NAMES[level],
            score=score,
            dimensions=dimensions,
            assessed_at=assessed_at,
            upgrade_path=cls._upgrade_path(level, cmms, production, sensors, site_count),
        )

    @staticmethod
    def get_level(db: Session, tenant: Tenant, refresh: bool = False) -> int:
        """Current maturity level, optionally recomputed first."""
        if refresh or tenant.last_assessed_at is None:
            return MaturityService.assess(db, tenant).level
        return tenant.maturity_level
