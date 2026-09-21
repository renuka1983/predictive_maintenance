"""Production batch CRUD and line views (Level 2+)."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_current_tenant, get_tenant_machine
from app.models import ProductionBatch, Tenant
from app.schemas.common import Message, PaginatedResponse
from app.schemas.production import (
    ProductionCreate,
    ProductionLineView,
    ProductionResponse,
    ProductionUpdate,
)
from app.services import AnalyticsService, FeatureGate

router = APIRouter(prefix="/production", tags=["production"])


def _get_batch(db: Session, tenant: Tenant, batch_id: str) -> ProductionBatch:
    from fastapi import HTTPException

    batch = db.execute(
        select(ProductionBatch).where(
            ProductionBatch.id == batch_id, ProductionBatch.tenant_id == tenant.id
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Production batch '{batch_id}' not found for this tenant",
        )
    return batch


@router.post("", response_model=ProductionResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: ProductionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> ProductionBatch:
    """Record a production batch.

    Ingest is always allowed - a tenant must be able to send production data
    *before* it unlocks the Level 2 analytics that data enables.
    """
    machine = get_tenant_machine(db, tenant, payload.machine_id)
    data = payload.model_dump()
    data["machine_id"] = machine.id
    batch = ProductionBatch(tenant_id=tenant.id, **data)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("", response_model=PaginatedResponse[ProductionResponse])
def list_batches(
    page: Pagination = Depends(),
    machine_id: Optional[str] = Query(None),
    product_code: Optional[str] = Query(None),
    start_after: Optional[datetime] = Query(None),
    start_before: Optional[datetime] = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProductionResponse]:
    """Search production batches (requires Level 2)."""
    FeatureGate.require(db, tenant, "production_tracking")

    filters = [ProductionBatch.tenant_id == tenant.id]
    if machine_id:
        machine = get_tenant_machine(db, tenant, machine_id)
        filters.append(ProductionBatch.machine_id == machine.id)
    if product_code:
        filters.append(ProductionBatch.product_code == product_code)
    if start_after:
        filters.append(ProductionBatch.start_time >= start_after)
    if start_before:
        filters.append(ProductionBatch.start_time <= start_before)

    total = int(
        db.execute(
            select(func.count()).select_from(ProductionBatch).where(*filters)
        ).scalar_one()
        or 0
    )
    rows = list(
        db.execute(
            select(ProductionBatch)
            .where(*filters)
            .order_by(ProductionBatch.start_time.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return PaginatedResponse[ProductionResponse](
        items=[ProductionResponse.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/lines/{production_line}", response_model=ProductionLineView)
def get_line_view(
    production_line: str,
    window_days: int = Query(30, ge=1, le=365),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> ProductionLineView:
    """Station-by-station OEE for one line, with the bottleneck flagged."""
    FeatureGate.require(db, tenant, "production_tracking")
    return AnalyticsService.production_line_view(
        db, tenant.id, production_line, window_days
    )


@router.get("/{batch_id}", response_model=ProductionResponse)
def get_batch(
    batch_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> ProductionBatch:
    """Fetch one production batch."""
    FeatureGate.require(db, tenant, "production_tracking")
    return _get_batch(db, tenant, batch_id)


@router.patch("/{batch_id}", response_model=ProductionResponse)
def update_batch(
    batch_id: str,
    payload: ProductionUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> ProductionBatch:
    """Update a production batch, e.g. to close it out with final counts."""
    batch = _get_batch(db, tenant, batch_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.delete("/{batch_id}", response_model=Message)
def delete_batch(
    batch_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Message:
    """Delete a production batch."""
    batch = _get_batch(db, tenant, batch_id)
    db.delete(batch)
    db.commit()
    return Message(detail=f"Production batch '{batch_id}' deleted")
