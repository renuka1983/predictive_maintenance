"""Site registry (Level 4 enterprise)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_tenant
from app.models import Machine, Site, Tenant
from app.schemas.common import Message
from app.schemas.site import SiteCreate, SiteResponse, SiteUpdate, SiteWithStats
from app.services import FeatureGate

router = APIRouter(prefix="/sites", tags=["sites"])


def _get_site(db: Session, tenant: Tenant, site_id: str) -> Site:
    """Load a site by id or name, scoped to the calling tenant."""
    site = db.execute(
        select(Site).where(Site.id == site_id, Site.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if site is None:
        site = db.execute(
            select(Site).where(Site.name == site_id, Site.tenant_id == tenant.id)
        ).scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site '{site_id}' not found for this tenant",
        )
    return site


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Site:
    """Register a plant so rollups can group it by region.

    ``name`` must match the ``site`` string on this tenant's machines; that
    string is the join key between the registry and the asset register.
    """
    FeatureGate.require(db, tenant, "site_registry")
    site = Site(tenant_id=tenant.id, **payload.model_dump())
    db.add(site)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Site '{payload.name}' is already registered for this tenant",
        )
    db.refresh(site)
    return site


@router.get("", response_model=List[SiteWithStats])
def list_sites(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> List[SiteWithStats]:
    """List registered sites with their current machine counts."""
    FeatureGate.require(db, tenant, "site_registry")

    counts = dict(
        db.execute(
            select(Machine.site, func.count())
            .where(Machine.tenant_id == tenant.id)
            .group_by(Machine.site)
        ).all()
    )
    sites = list(
        db.execute(
            select(Site).where(Site.tenant_id == tenant.id).order_by(Site.name)
        ).scalars()
    )
    return [
        SiteWithStats(
            **SiteResponse.model_validate(site).model_dump(),
            machine_count=counts.get(site.name, 0),
        )
        for site in sites
    ]


@router.get("/unregistered", response_model=List[str])
def list_unregistered_sites(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> List[str]:
    """Site names used by machines but absent from the registry.

    Rollups still include these (falling back to the bare machine string),
    but they cannot be grouped by region until they are registered.
    """
    FeatureGate.require(db, tenant, "site_registry")

    used = {
        row[0]
        for row in db.execute(
            select(Machine.site)
            .where(Machine.tenant_id == tenant.id, Machine.site.isnot(None))
            .distinct()
        ).all()
    }
    registered = {
        row[0]
        for row in db.execute(
            select(Site.name).where(Site.tenant_id == tenant.id)
        ).all()
    }
    return sorted(used - registered)


@router.post("/sync", response_model=List[SiteResponse])
def sync_sites(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> List[Site]:
    """Create a registry entry for every site name used by a machine.

    Convenience for onboarding an enterprise tenant that already has machines
    tagged with site names; regions can then be filled in afterwards.
    """
    FeatureGate.require(db, tenant, "site_registry")

    used = {
        row[0]
        for row in db.execute(
            select(Machine.site)
            .where(Machine.tenant_id == tenant.id, Machine.site.isnot(None))
            .distinct()
        ).all()
    }
    registered = {
        row[0]
        for row in db.execute(
            select(Site.name).where(Site.tenant_id == tenant.id)
        ).all()
    }

    for name in sorted(used - registered):
        db.add(Site(tenant_id=tenant.id, name=name))
    db.commit()

    return list(
        db.execute(
            select(Site).where(Site.tenant_id == tenant.id).order_by(Site.name)
        ).scalars()
    )


@router.get("/regions", response_model=List[str])
def list_regions(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> List[str]:
    """Distinct regions across this tenant's registered sites."""
    FeatureGate.require(db, tenant, "site_registry")
    rows = db.execute(
        select(Site.region)
        .where(Site.tenant_id == tenant.id, Site.region.isnot(None))
        .distinct()
        .order_by(Site.region)
    ).all()
    return [row[0] for row in rows]


@router.get("/{site_id}", response_model=SiteResponse)
def get_site(
    site_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Site:
    """Fetch one site by id or name."""
    FeatureGate.require(db, tenant, "site_registry")
    return _get_site(db, tenant, site_id)


@router.patch("/{site_id}", response_model=SiteResponse)
def update_site(
    site_id: str,
    payload: SiteUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Site:
    """Update site metadata, e.g. to assign it to a region."""
    FeatureGate.require(db, tenant, "site_registry")
    site = _get_site(db, tenant, site_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(site, field, value)
    db.add(site)
    db.commit()
    db.refresh(site)
    return site


@router.delete("/{site_id}", response_model=Message)
def delete_site(
    site_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> Message:
    """Remove a site from the registry.

    Machines are left untouched: their ``site`` string still groups them in
    rollups, they simply lose the region metadata.
    """
    FeatureGate.require(db, tenant, "site_registry")
    site = _get_site(db, tenant, site_id)
    name = site.name
    db.delete(site)
    db.commit()
    return Message(detail=f"Site '{name}' removed from the registry")
