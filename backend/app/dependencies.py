"""Shared FastAPI dependencies: tenant resolution and common query params."""

from typing import Optional

from fastapi import Depends, Header, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Machine, Tenant


def get_tenant_by_id(db: Session, tenant_id: str) -> Tenant:
    """Load a tenant by id or slug, or raise 404."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        tenant = db.execute(
            select(Tenant).where(Tenant.slug == tenant_id)
        ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )
    return tenant


def get_path_tenant(
    tenant_id: str = Path(..., description="Tenant id or slug"),
    db: Session = Depends(get_db),
) -> Tenant:
    """Resolve the tenant named in the URL path."""
    return get_tenant_by_id(db, tenant_id)


def get_current_tenant(
    x_tenant_id: Optional[str] = Header(
        None,
        alias="X-Tenant-ID",
        description="Tenant id or slug identifying the calling organisation",
    ),
    db: Session = Depends(get_db),
) -> Tenant:
    """Resolve the tenant context for a request.

    Tenant scope is carried in the ``X-Tenant-ID`` header so that no endpoint
    can accidentally serve cross-tenant data: every downstream query filters on
    the tenant returned here.
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required X-Tenant-ID header",
        )

    tenant = get_tenant_by_id(db, x_tenant_id)
    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant '{tenant.slug}' is inactive",
        )
    return tenant


def get_tenant_machine(db: Session, tenant: Tenant, machine_id: str) -> Machine:
    """Load a machine that belongs to ``tenant``, or raise 404.

    A machine belonging to a different tenant is reported as not found rather
    than forbidden, so the API never confirms the existence of another
    tenant's assets.
    """
    machine = db.execute(
        select(Machine).where(
            Machine.id == machine_id, Machine.tenant_id == tenant.id
        )
    ).scalar_one_or_none()
    if machine is None:
        machine = db.execute(
            select(Machine).where(
                Machine.machine_code == machine_id, Machine.tenant_id == tenant.id
            )
        ).scalar_one_or_none()
    if machine is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine '{machine_id}' not found for this tenant",
        )
    return machine


class Pagination:
    """Standard limit/offset pagination parameters."""

    def __init__(
        self,
        limit: int = Query(50, ge=1, le=500, description="Maximum rows to return"),
        offset: int = Query(0, ge=0, description="Rows to skip"),
    ):
        self.limit = limit
        self.offset = offset
