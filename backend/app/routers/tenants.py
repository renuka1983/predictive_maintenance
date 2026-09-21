"""Tenant administration, maturity assessment and feature toggles."""

from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import Pagination, get_path_tenant
from app.models import Tenant
from app.schemas.common import Message, PaginatedResponse
from app.schemas.tenant import (
    FeatureListResponse,
    MaturityAssessment,
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)
from app.services import FeatureGate, MaturityService
from app.services.feature_catalog import LEVEL_NAMES, LEVEL_PRICING, FEATURES

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post(
    "", response_model=TenantResponse, status_code=status.HTTP_201_CREATED
)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)) -> Tenant:
    """Onboard a new customer organisation at maturity Level 0."""
    tenant = Tenant(**payload.model_dump())
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A tenant with slug '{payload.slug}' already exists",
        )
    db.refresh(tenant)
    # Seed the toggle table so the customer can see their upgrade path.
    FeatureGate.sync_toggles(db, tenant)
    return tenant


@router.get("", response_model=PaginatedResponse[TenantResponse])
def list_tenants(
    page: Pagination = Depends(),
    is_active: bool | None = Query(None, description="Filter by active flag"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[TenantResponse]:
    """List tenants (platform administration endpoint)."""
    stmt = select(Tenant)
    count_stmt = select(func.count()).select_from(Tenant)
    if is_active is not None:
        stmt = stmt.where(Tenant.is_active.is_(is_active))
        count_stmt = count_stmt.where(Tenant.is_active.is_(is_active))

    total = int(db.execute(count_stmt).scalar_one() or 0)
    rows = list(
        db.execute(
            stmt.order_by(Tenant.created_at.desc())
            .limit(page.limit)
            .offset(page.offset)
        ).scalars()
    )
    return PaginatedResponse[TenantResponse](
        items=[TenantResponse.model_validate(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/levels", tags=["reference"])
def list_levels() -> List[dict]:
    """Reference data: what each maturity level is called and unlocks."""
    return [
        {
            "level": level,
            "name": name,
            "pricing": LEVEL_PRICING[level],
            "features": [
                {"key": f.key, "name": f.name, "category": f.category}
                for f in FEATURES
                if f.required_level == level
            ],
        }
        for level, name in sorted(LEVEL_NAMES.items())
    ]


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(tenant: Tenant = Depends(get_path_tenant)) -> Tenant:
    """Fetch one tenant by id or slug."""
    return tenant


@router.patch("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    payload: TenantUpdate,
    tenant: Tenant = Depends(get_path_tenant),
    db: Session = Depends(get_db),
) -> Tenant:
    """Update mutable tenant attributes."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.delete("/{tenant_id}", response_model=Message)
def delete_tenant(
    tenant: Tenant = Depends(get_path_tenant), db: Session = Depends(get_db)
) -> Message:
    """Delete a tenant and every row that belongs to it."""
    slug = tenant.slug
    db.delete(tenant)
    db.commit()
    return Message(detail=f"Tenant '{slug}' and all associated data deleted")


@router.post("/{tenant_id}/assess", response_model=MaturityAssessment)
def assess_tenant(
    tenant: Tenant = Depends(get_path_tenant), db: Session = Depends(get_db)
) -> MaturityAssessment:
    """Re-run the maturity assessment and sync feature toggles.

    This is the only endpoint that changes a tenant's level; analytics
    endpoints read the cached level so a single slow assessment cannot be
    triggered by ordinary dashboard traffic.
    """
    assessment = MaturityService.assess(db, tenant)
    FeatureGate.sync_toggles(db, tenant)
    return assessment


@router.get("/{tenant_id}/maturity", response_model=MaturityAssessment)
def get_maturity(
    refresh: bool = Query(False, description="Recompute instead of reading cache"),
    tenant: Tenant = Depends(get_path_tenant),
    db: Session = Depends(get_db),
) -> MaturityAssessment:
    """Current maturity assessment, optionally recomputed on demand."""
    return MaturityService.assess(db, tenant, persist=refresh)


@router.get("/{tenant_id}/features", response_model=FeatureListResponse)
def list_tenant_features(
    tenant: Tenant = Depends(get_path_tenant), db: Session = Depends(get_db)
) -> FeatureListResponse:
    """Which features this tenant has unlocked and which are still locked."""
    return FeatureGate.list_features(db, tenant)


@router.put("/{tenant_id}/features/{feature_key}", response_model=FeatureListResponse)
def override_feature(
    feature_key: str,
    enabled: bool = Body(..., embed=True, description="Grant or revoke the feature"),
    tenant: Tenant = Depends(get_path_tenant),
    db: Session = Depends(get_db),
) -> FeatureListResponse:
    """Manually grant or revoke a feature (e.g. to run a trial).

    Manual overrides survive future maturity assessments.
    """
    try:
        FeatureGate.set_override(db, tenant, feature_key, enabled)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown feature '{feature_key}'",
        )
    return FeatureGate.list_features(db, tenant)
