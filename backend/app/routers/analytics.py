"""Maturity-aware analytics: the endpoints that gate on feature level."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_tenant, get_tenant_machine
from app.models import Machine, Tenant
from app.schemas.analytics import (
    AnomalyReport,
    CascadeImpact,
    DashboardSummary,
    ROIEstimate,
    RiskScore,
    RULPrediction,
    WeibullFit,
)
from app.services import AnalyticsService, FeatureGate, MLService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardSummary)
def get_dashboard(
    tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)
) -> DashboardSummary:
    """One payload driving the landing page, shaped by maturity level.

    Sections the tenant has not unlocked come back as ``null`` instead of an
    error, so the UI can render an upgrade prompt in their place without
    making a second round of requests that would only 403.
    """
    level = tenant.maturity_level
    enabled = FeatureGate.enabled_keys(db, tenant)

    machine_count = int(
        db.execute(
            select(func.count()).select_from(Machine).where(
                Machine.tenant_id == tenant.id
            )
        ).scalar_one()
        or 0
    )
    machines_down = int(
        db.execute(
            select(func.count()).select_from(Machine).where(
                Machine.tenant_id == tenant.id, Machine.status == "down"
            )
        ).scalar_one()
        or 0
    )

    summary = DashboardSummary(
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        maturity_level=level,
        maturity_score=tenant.maturity_score,
        machine_count=machine_count,
        machines_down=machines_down,
        enabled_features=enabled,
    )

    if "maintenance_stats" in enabled:
        stats = AnalyticsService.maintenance_stats(db, tenant.id, window_days=365)
        summary.maintenance_summary = {
            "total_records": stats.total_records,
            "reactive_count": stats.reactive_count,
            "planned_ratio": stats.planned_ratio,
            "total_cost": stats.total_cost,
            "total_downtime_hours": stats.total_downtime_hours,
            "mtbf_hours": stats.mtbf_hours,
            "monthly_trend": stats.monthly_trend[-12:],
            "top_failure_modes": stats.top_failure_modes[:5],
        }

    if "failure_risk_scoring" in enabled:
        summary.top_risks = MLService.risk_scores(db, tenant.id, limit=5)

    if "production_tracking" in enabled:
        lines = [
            row[0]
            for row in db.execute(
                select(Machine.production_line)
                .where(
                    Machine.tenant_id == tenant.id,
                    Machine.production_line.isnot(None),
                )
                .distinct()
            ).all()
        ]
        summary.line_summary = [
            {
                "production_line": line,
                "line_oee": view.line_oee,
                "produced_units": view.total_produced_units,
                "bottleneck_machine_id": view.bottleneck_machine_id,
                "station_count": len(view.stations),
            }
            for line in sorted(lines)
            for view in [
                AnalyticsService.production_line_view(db, tenant.id, line, 30)
            ]
        ]

    if "anomaly_detection" in enabled:
        report = MLService.detect_anomalies(db, tenant.id, window_hours=24)
        summary.active_anomalies = report.anomaly_count

    if "rul_prediction" in enabled:
        instrumented = list(
            db.execute(
                select(Machine).where(
                    Machine.tenant_id == tenant.id, Machine.has_sensors.is_(True)
                )
            ).scalars()
        )
        predictions = [
            MLService.predict_rul(db, tenant.id, machine) for machine in instrumented
        ]
        # Shortest remaining life first; machines with no trend are omitted.
        watchlist = [p for p in predictions if p.rul_hours is not None]
        watchlist.sort(key=lambda p: p.rul_hours)
        summary.rul_watchlist = watchlist[:5]

    if "benchmarking" in enabled:
        summary.site_benchmark = AnalyticsService.site_benchmark(db, tenant.id)

    return summary


# ----------------------------------------------------------------------
# Level 1
# ----------------------------------------------------------------------
@router.get("/reliability/weibull", response_model=WeibullFit)
def get_weibull(
    machine_id: Optional[str] = Query(None, description="Omit for a fleet-wide fit"),
    horizon_days: int = Query(30, ge=1, le=365),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> WeibullFit:
    """Fit a Weibull reliability curve to observed failure intervals."""
    FeatureGate.require(db, tenant, "weibull_reliability")
    resolved_id = (
        get_tenant_machine(db, tenant, machine_id).id if machine_id else None
    )
    return MLService.weibull_fit(db, tenant.id, resolved_id, horizon_days)


# ----------------------------------------------------------------------
# Level 2
# ----------------------------------------------------------------------
@router.get("/risk", response_model=List[RiskScore])
def get_risk_scores(
    horizon_days: int = Query(30, ge=1, le=365),
    machine_id: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=500),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> List[RiskScore]:
    """Failure probability per machine, highest risk first."""
    FeatureGate.require(db, tenant, "failure_risk_scoring")
    resolved_id = (
        get_tenant_machine(db, tenant, machine_id).id if machine_id else None
    )
    return MLService.risk_scores(db, tenant.id, horizon_days, resolved_id, limit)


@router.get("/cascade/{machine_id}", response_model=CascadeImpact)
def get_cascade_impact(
    machine_id: str,
    downtime_hours: float = Query(4.0, gt=0, le=720),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> CascadeImpact:
    """Model the line-wide cost of one machine going down."""
    FeatureGate.require(db, tenant, "cascade_impact_analysis")
    machine = get_tenant_machine(db, tenant, machine_id)
    return MLService.cascade_impact(db, tenant.id, machine, downtime_hours)


@router.post("/simulate", response_model=CascadeImpact)
def simulate_downtime(
    machine_id: str = Query(..., description="Machine id or code to take down"),
    downtime_hours: float = Query(..., gt=0, le=720),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> CascadeImpact:
    """What-if simulator: cost of a hypothetical stoppage."""
    FeatureGate.require(db, tenant, "impact_simulator")
    machine = get_tenant_machine(db, tenant, machine_id)
    return MLService.cascade_impact(db, tenant.id, machine, downtime_hours)


@router.get("/roi", response_model=ROIEstimate)
def get_roi(
    window_days: int = Query(365, ge=30, le=1825),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> ROIEstimate:
    """Savings available from avoiding preventable reactive maintenance."""
    FeatureGate.require(db, tenant, "roi_analysis")
    return AnalyticsService.roi_estimate(db, tenant.id, window_days)


# ----------------------------------------------------------------------
# Level 3
# ----------------------------------------------------------------------
@router.get("/anomalies", response_model=AnomalyReport)
def get_anomalies(
    window_hours: int = Query(24, ge=1, le=720),
    machine_id: Optional[str] = Query(None),
    contamination: float = Query(
        0.005, gt=0, lt=0.5, description="Expected outlier rate in the window"
    ),
    limit: int = Query(100, ge=1, le=1000),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> AnomalyReport:
    """Isolation Forest anomalies across recent telemetry."""
    FeatureGate.require(db, tenant, "anomaly_detection")
    resolved_id = (
        get_tenant_machine(db, tenant, machine_id).id if machine_id else None
    )
    return MLService.detect_anomalies(
        db, tenant.id, window_hours, resolved_id, contamination, limit
    )


@router.get("/rul", response_model=List[RULPrediction])
def get_rul(
    machine_id: Optional[str] = Query(None),
    window_days: int = Query(30, ge=1, le=365),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> List[RULPrediction]:
    """Remaining useful life for instrumented machines, soonest first."""
    FeatureGate.require(db, tenant, "rul_prediction")

    if machine_id:
        machines = [get_tenant_machine(db, tenant, machine_id)]
    else:
        machines = list(
            db.execute(
                select(Machine).where(
                    Machine.tenant_id == tenant.id, Machine.has_sensors.is_(True)
                )
            ).scalars()
        )

    predictions = [MLService.predict_rul(db, tenant.id, m, window_days) for m in machines]
    # Machines with no detectable degradation sort last.
    predictions.sort(key=lambda p: (p.rul_hours is None, p.rul_hours or 0.0))
    return predictions


# ----------------------------------------------------------------------
# Level 4
# ----------------------------------------------------------------------
@router.get("/benchmark", response_model=List[dict])
def get_benchmark(
    window_days: int = Query(90, ge=7, le=1825),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> List[dict]:
    """Rank this tenant's sites on OEE, downtime and maintenance spend."""
    FeatureGate.require(db, tenant, "benchmarking")
    return AnalyticsService.site_benchmark(db, tenant.id, window_days)
