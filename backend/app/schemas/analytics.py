"""Analytics and ML response schemas."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class WeibullFit(BaseModel):
    """Level 1: reliability curve fitted to time-between-failures."""

    machine_id: Optional[str] = None
    shape: float = Field(..., description="Weibull beta; >1 means wear-out failures")
    scale_hours: float = Field(..., description="Weibull eta, characteristic life")
    mtbf_hours: float
    sample_size: int
    failure_probability_30d: float = Field(..., ge=0, le=1)
    interpretation: str
    confidence: str


class RiskScore(BaseModel):
    """Level 2: probability that a machine fails in the coming window."""

    machine_id: str
    machine_code: str
    risk_score: float = Field(..., ge=0, le=1)
    risk_band: str
    horizon_days: int
    drivers: List[Dict[str, object]] = []
    model_used: str
    confidence: str


class CascadeNode(BaseModel):
    machine_id: str
    machine_code: str
    line_position: Optional[int] = None
    impact_type: str  # "source" | "downstream_starved" | "upstream_blocked"
    lost_units: float
    lost_revenue: float


class CascadeImpact(BaseModel):
    """Level 2: knock-on effect of one machine stopping a whole line."""

    machine_id: str
    production_line: Optional[str] = None
    downtime_hours: float
    direct_lost_units: float
    cascade_lost_units: float
    total_cost: float
    affected_machines: List[CascadeNode]
    bottleneck_machine_id: Optional[str] = None


class ROIEstimate(BaseModel):
    """Business case for acting on predictive maintenance insight."""

    tenant_id: str
    window_days: int
    reactive_cost: float
    preventable_cost: float
    estimated_annual_savings: float
    downtime_hours_avoided: float
    assumptions: List[str]


class RULPrediction(BaseModel):
    """Level 3: remaining useful life from sensor degradation trend."""

    machine_id: str
    machine_code: str
    rul_hours: Optional[float] = None
    predicted_failure_at: Optional[datetime] = None
    degradation_rate_per_hour: float
    dominant_sensor: Optional[str] = None
    sample_size: int
    confidence: str
    method: str


class AnomalyEvent(BaseModel):
    machine_id: str
    sensor_type: str
    recorded_at: datetime
    value: float
    score: float = Field(..., description="Lower is more anomalous")
    severity: str


class AnomalyReport(BaseModel):
    """Level 3: outliers detected across recent telemetry."""

    tenant_id: str
    window_hours: int
    readings_analysed: int
    anomaly_count: int
    anomalies: List[AnomalyEvent]
    method: str


class DashboardSummary(BaseModel):
    """Maturity-aware landing-page payload.

    Only the sections the tenant has unlocked are populated; the rest are
    ``None`` so the frontend can render an upgrade prompt in their place.
    """

    tenant_id: str
    tenant_name: str
    maturity_level: int
    maturity_score: float
    machine_count: int
    machines_down: int
    enabled_features: List[str]
    # Level 1
    maintenance_summary: Optional[Dict[str, object]] = None
    # Level 2
    top_risks: Optional[List[RiskScore]] = None
    line_summary: Optional[List[Dict[str, object]]] = None
    # Level 3
    active_anomalies: Optional[int] = None
    rul_watchlist: Optional[List[RULPrediction]] = None
    # Level 4
    site_benchmark: Optional[List[Dict[str, object]]] = None
