"""Maintenance work-order CRUD and Level 1 statistics."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_current_tenant, get_tenant_machine
from app.models import MaintenanceRecord, Tenant
from app.schemas.common import Message, PaginatedResponse
from app.schemas.maintenance import (
    MaintenanceCreate,
    MaintenanceResponse,
    MaintenanceStats,
    MaintenanceUpdate,
)
from app.services import AnalyticsService, FeatureGate

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _get_record(db: Session, tenant: Tenant, record_id: str) -> MaintenanceRecord:
    """Load a maintenance record scoped to the calling tenant."""
    from fastapi import HTTPException

    record = db.execute(
        select(MaintenanceRecord).where(
            MaintenanceRecord.id == record_id,
            MaintenanceRecord.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Maintenance record '{record_id}' not found for this tenant",
        )
    return record


@router.post("", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
def create_record(
    payload: MaintenanceCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> MaintenanceRecord:
    """Log a maintenance work order against one of this tenant's machines."""
    # Validates that the machine exists *and* belongs to the caller.
    machine = get_tenant_machine(db, tenant, payload.machine_id)

    data = payload.model_dump()
    data["machine_id"] = machine.id
    record = MaintenanceRecord(tenant_id=tenant.id, **data)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=PaginatedResponse[MaintenanceResponse])
def list_records(
    page: Pagination = Depends(),
    machine_id: Optional[str] = Query(None),
    maintenance_type: Optional[str] = Query(None),
    failure_mode: Optional[str] = Query(None),
    start_after: Optional[datetime] = Query(None),
    start_before: Optional[datetime] = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MaintenanceResponse]:
    """Search this tenant's maintenance history."""
    FeatureGate.require(db, tenant, "maintenance_history")

    filters = [MaintenanceRecord.tenant_id == tenant.id]
    if machine_id:
        machine = get_tenant_machine(db, tenant, machine_id)
        filters.append(MaintenanceRecord.machine_id == machine.id)
    if maintenance_type:
        filters.append(MaintenanceRecord.maintenance_type == maintenance_type)
    if failure_mode:
        filters.append(MaintenanceRecord.failure_mode == failure_mode)
    if start_after:
        filters.append(MaintenanceRecord.start_time >= start_after)
    if start_before:
        filters.append(MaintenanceRecord.start_time <= start_before)

    total = int(
        db.execute(
            select(func.count()).select_from(MaintenanceRecord).where(*filters)
        ).scalar_one()
        or 0
    )
    rows = list(
        db.execute(
            select(MaintenanceRecord)
            .where(*filters)
            .order_by(MaintenanceRecord.start_time.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return PaginatedResponse[MaintenanceResponse](
        items=[MaintenanceResponse.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/stats", response_model=MaintenanceStats)
def get_stats(
    window_days: int = Query(365, ge=1, le=1825),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> MaintenanceStats:
    """Level 1 KPIs: MTBF, MTTR, planned ratio, cost and failure Pareto."""
    FeatureGate.require(db, tenant, "maintenance_stats")
    return AnalyticsService.maintenance_stats(db, tenant.id, window_days)


@router.get("/{record_id}", response_model=MaintenanceResponse)
def get_record(
    record_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> MaintenanceRecord:
    """Fetch one maintenance record."""
    FeatureGate.require(db, tenant, "maintenance_history")
    return _get_record(db, tenant, record_id)


@router.patch("/{record_id}", response_model=MaintenanceResponse)
def update_record(
    record_id: str,
    payload: MaintenanceUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> MaintenanceRecord:
    """Correct a maintenance record (e.g. add final costs once closed)."""
    record = _get_record(db, tenant, record_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(record, field, value)
    # Keep the derived total consistent when either cost component changes.
    if ("labor_cost" in updates or "parts_cost" in updates) and "total_cost" not in updates:
        record.total_cost = round(record.labor_cost + record.parts_cost, 2)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{record_id}", response_model=Message)
def delete_record(
    record_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Message:
    """Delete a maintenance record."""
    record = _get_record(db, tenant, record_id)
    db.delete(record)
    db.commit()
    return Message(detail=f"Maintenance record '{record_id}' deleted")
