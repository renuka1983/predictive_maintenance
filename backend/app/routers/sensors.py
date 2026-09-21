"""IoT sensor ingest and telemetry queries (Level 3+)."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_current_tenant, get_tenant_machine
from app.models import Machine, SensorReading, Tenant
from app.schemas.common import PaginatedResponse
from app.schemas.sensor import (
    SensorBatchCreate,
    SensorReadingCreate,
    SensorReadingResponse,
    SensorSeries,
    SensorSeriesPoint,
    SensorSnapshot,
)
from app.services import FeatureGate

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post(
    "/readings", response_model=SensorReadingResponse, status_code=status.HTTP_201_CREATED
)
def ingest_reading(
    payload: SensorReadingCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> SensorReading:
    """Ingest a single sensor reading.

    Ingest is ungated so a tenant can stream data in order to *reach* Level 3.
    """
    machine = get_tenant_machine(db, tenant, payload.machine_id)
    data = payload.model_dump()
    data["machine_id"] = machine.id
    data["recorded_at"] = data.get("recorded_at") or datetime.now(timezone.utc)
    reading = SensorReading(tenant_id=tenant.id, **data)
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


@router.post("/readings/batch", status_code=status.HTTP_201_CREATED)
def ingest_batch(
    payload: SensorBatchCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict:
    """Bulk-ingest readings from an IoT gateway.

    Machine ids are resolved once per distinct machine rather than per reading,
    so a 5000-row push costs a handful of queries instead of thousands.
    """
    now = datetime.now(timezone.utc)
    resolved: dict[str, str] = {}
    rows: List[SensorReading] = []

    for item in payload.readings:
        if item.machine_id not in resolved:
            resolved[item.machine_id] = get_tenant_machine(
                db, tenant, item.machine_id
            ).id
        data = item.model_dump()
        data["machine_id"] = resolved[item.machine_id]
        data["recorded_at"] = data.get("recorded_at") or now
        rows.append(SensorReading(tenant_id=tenant.id, **data))

    db.bulk_save_objects(rows)
    db.commit()
    return {"ingested": len(rows), "machines": len(resolved)}


@router.get("/readings", response_model=PaginatedResponse[SensorReadingResponse])
def list_readings(
    page: Pagination = Depends(),
    machine_id: Optional[str] = Query(None),
    sensor_type: Optional[str] = Query(None),
    recorded_after: Optional[datetime] = Query(None),
    recorded_before: Optional[datetime] = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> PaginatedResponse[SensorReadingResponse]:
    """Query raw telemetry (requires Level 3)."""
    FeatureGate.require(db, tenant, "sensor_telemetry")

    filters = [SensorReading.tenant_id == tenant.id]
    if machine_id:
        machine = get_tenant_machine(db, tenant, machine_id)
        filters.append(SensorReading.machine_id == machine.id)
    if sensor_type:
        filters.append(SensorReading.sensor_type == sensor_type)
    if recorded_after:
        filters.append(SensorReading.recorded_at >= recorded_after)
    if recorded_before:
        filters.append(SensorReading.recorded_at <= recorded_before)

    total = int(
        db.execute(
            select(func.count()).select_from(SensorReading).where(*filters)
        ).scalar_one()
        or 0
    )
    rows = list(
        db.execute(
            select(SensorReading)
            .where(*filters)
            .order_by(SensorReading.recorded_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return PaginatedResponse[SensorReadingResponse](
        items=[SensorReadingResponse.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/latest", response_model=List[SensorSnapshot])
def latest_snapshot(
    machine_id: Optional[str] = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> List[SensorSnapshot]:
    """Most recent value per sensor type - the real-time monitoring feed.

    The frontend polls this endpoint; it returns one row per sensor channel
    rather than a raw firehose so the payload stays small.
    """
    FeatureGate.require(db, tenant, "realtime_monitoring")

    machine_filter = [Machine.tenant_id == tenant.id, Machine.has_sensors.is_(True)]
    if machine_id:
        machine_filter = [Machine.id == get_tenant_machine(db, tenant, machine_id).id]

    machines = list(db.execute(select(Machine).where(*machine_filter)).scalars())
    snapshots: List[SensorSnapshot] = []

    for machine in machines:
        # Latest timestamp per sensor type for this machine.
        latest_per_type = (
            select(
                SensorReading.sensor_type,
                func.max(SensorReading.recorded_at).label("latest"),
            )
            .where(
                SensorReading.tenant_id == tenant.id,
                SensorReading.machine_id == machine.id,
            )
            .group_by(SensorReading.sensor_type)
            .subquery()
        )
        rows = list(
            db.execute(
                select(SensorReading)
                .join(
                    latest_per_type,
                    (SensorReading.sensor_type == latest_per_type.c.sensor_type)
                    & (SensorReading.recorded_at == latest_per_type.c.latest),
                )
                .where(
                    SensorReading.tenant_id == tenant.id,
                    SensorReading.machine_id == machine.id,
                )
            ).scalars()
        )
        captured = max((r.recorded_at for r in rows), default=None)
        snapshots.append(
            SensorSnapshot(
                machine_id=machine.id,
                machine_code=machine.machine_code,
                captured_at=captured,
                readings=[SensorReadingResponse.model_validate(r) for r in rows],
            )
        )

    return snapshots


@router.get("/series", response_model=SensorSeries)
def get_series(
    machine_id: str = Query(..., description="Machine id or code"),
    sensor_type: str = Query(...),
    window_hours: int = Query(24, ge=1, le=8760),
    max_points: int = Query(500, ge=10, le=5000),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> SensorSeries:
    """Time series for charting, evenly downsampled to ``max_points``."""
    FeatureGate.require(db, tenant, "sensor_telemetry")
    machine = get_tenant_machine(db, tenant, machine_id)
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    rows = list(
        db.execute(
            select(SensorReading)
            .where(
                SensorReading.tenant_id == tenant.id,
                SensorReading.machine_id == machine.id,
                SensorReading.sensor_type == sensor_type,
                SensorReading.recorded_at >= since,
            )
            .order_by(SensorReading.recorded_at)
        ).scalars()
    )

    if not rows:
        return SensorSeries(
            machine_id=machine.id,
            sensor_type=sensor_type,
            unit=None,
            points=[],
            mean=0.0,
            minimum=0.0,
            maximum=0.0,
        )

    # Uniform stride keeps the shape of the curve while bounding the payload.
    stride = max(1, len(rows) // max_points)
    sampled = rows[::stride]
    values = [r.value for r in rows]

    return SensorSeries(
        machine_id=machine.id,
        sensor_type=sensor_type,
        unit=rows[0].unit,
        points=[
            SensorSeriesPoint(recorded_at=r.recorded_at, value=r.value)
            for r in sampled
        ],
        mean=round(sum(values) / len(values), 4),
        minimum=round(min(values), 4),
        maximum=round(max(values), 4),
    )
