"""Machine registry CRUD and per-machine status (Level 1+)."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_current_tenant, get_tenant_machine
from app.models import Machine, Tenant
from app.schemas.common import Message, PaginatedResponse
from app.schemas.machine import (
    MachineCreate,
    MachineResponse,
    MachineStatus,
    MachineUpdate,
)
from app.services import AnalyticsService, FeatureGate

router = APIRouter(prefix="/machines", tags=["machines"])


@router.post("", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
def create_machine(
    payload: MachineCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Machine:
    """Register a machine under the calling tenant."""
    machine = Machine(tenant_id=tenant.id, **payload.model_dump())
    db.add(machine)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Machine code '{payload.machine_code}' already exists for this tenant"
            ),
        )
    db.refresh(machine)
    return machine


@router.get("", response_model=PaginatedResponse[MachineResponse])
def list_machines(
    page: Pagination = Depends(),
    site: Optional[str] = Query(None),
    production_line: Optional[str] = Query(None),
    machine_status: Optional[str] = Query(None, alias="status"),
    has_sensors: Optional[bool] = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MachineResponse]:
    """List this tenant's machines with optional filters."""
    filters = [Machine.tenant_id == tenant.id]
    if site:
        filters.append(Machine.site == site)
    if production_line:
        filters.append(Machine.production_line == production_line)
    if machine_status:
        filters.append(Machine.status == machine_status)
    if has_sensors is not None:
        filters.append(Machine.has_sensors.is_(has_sensors))

    total = int(
        db.execute(
            select(func.count()).select_from(Machine).where(*filters)
        ).scalar_one()
        or 0
    )
    rows = list(
        db.execute(
            select(Machine)
            .where(*filters)
            .order_by(Machine.production_line, Machine.line_position, Machine.machine_code)
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return PaginatedResponse[MachineResponse](
        items=[MachineResponse.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/lines", response_model=List[str])
def list_production_lines(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> List[str]:
    """Distinct production line names, for navigation and filters."""
    rows = db.execute(
        select(Machine.production_line)
        .where(Machine.tenant_id == tenant.id, Machine.production_line.isnot(None))
        .distinct()
        .order_by(Machine.production_line)
    ).all()
    return [row[0] for row in rows]


@router.get("/sites", response_model=List[str])
def list_sites(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> List[str]:
    """Distinct site names for this tenant."""
    rows = db.execute(
        select(Machine.site)
        .where(Machine.tenant_id == tenant.id, Machine.site.isnot(None))
        .distinct()
        .order_by(Machine.site)
    ).all()
    return [row[0] for row in rows]


@router.get("/status", response_model=List[MachineStatus])
def list_machine_statuses(
    window_days: int = Query(365, ge=1, le=1825),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> List[MachineStatus]:
    """Health rollup for every machine, worst health first."""
    FeatureGate.require(db, tenant, "machine_registry")
    machines = list(
        db.execute(select(Machine).where(Machine.tenant_id == tenant.id)).scalars()
    )
    statuses = [
        AnalyticsService.machine_status(db, tenant.id, machine, window_days)
        for machine in machines
    ]
    statuses.sort(key=lambda s: s.health_score)
    return statuses


@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(
    machine_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Machine:
    """Fetch one machine by id or machine code."""
    return get_tenant_machine(db, tenant, machine_id)


@router.patch("/{machine_id}", response_model=MachineResponse)
def update_machine(
    machine_id: str,
    payload: MachineUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Machine:
    """Update machine attributes such as status or criticality."""
    machine = get_tenant_machine(db, tenant, machine_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(machine, field, value)
    db.add(machine)
    db.commit()
    db.refresh(machine)
    return machine


@router.delete("/{machine_id}", response_model=Message)
def delete_machine(
    machine_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Message:
    """Delete a machine and its maintenance, production and sensor history."""
    machine = get_tenant_machine(db, tenant, machine_id)
    code = machine.machine_code
    db.delete(machine)
    db.commit()
    return Message(detail=f"Machine '{code}' deleted")


@router.get("/{machine_id}/status", response_model=MachineStatus)
def get_machine_status(
    machine_id: str,
    window_days: int = Query(365, ge=1, le=1825),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> MachineStatus:
    """Health rollup for one machine."""
    FeatureGate.require(db, tenant, "machine_registry")
    machine = get_tenant_machine(db, tenant, machine_id)
    return AnalyticsService.machine_status(db, tenant.id, machine, window_days)
