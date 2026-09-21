"""Level 4 enterprise analytics schemas.

Group and site rows carry a wide, evolving metric set, so they are typed as
open dictionaries rather than being pinned field by field - adding a metric to
``EnterpriseService._aggregate`` should not require a schema migration.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PortfolioTotals(BaseModel):
    """Organisation-wide figures, recomputed from raw counts."""

    machine_count: int
    machines_down: int
    maintenance_events: int
    reactive_events: int
    reactive_ratio: float = Field(..., ge=0, le=1)
    downtime_hours: float
    maintenance_cost: float
    produced_units: int
    quality_rate: float = Field(..., ge=0, le=1)
    weighted_avg_oee: float = Field(
        ..., ge=0, le=1, description="OEE weighted by machine count, not a mean of means"
    )
    cost_per_machine: float


class PortfolioRollup(BaseModel):
    """Multi-site rollup, grouped by site or region."""

    tenant_id: str
    window_days: int
    group_by: str
    group_count: int
    totals: PortfolioTotals
    groups: List[Dict[str, object]]


class MetricLeader(BaseModel):
    """Best and worst performer for one benchmark metric."""

    label: str
    higher_is_better: bool
    best_site: str
    best_value: Optional[float] = None
    worst_site: str
    worst_value: Optional[float] = None
    median: float


class BenchmarkOpportunity(BaseModel):
    """Value of bringing every site up to the best observed site."""

    benchmark_site: str
    benchmark_cost_per_machine: float
    benchmark_downtime_per_machine: float
    window_cost_gap: float
    annualised_saving: float
    annualised_downtime_hours: float
    worst_offenders: List[Dict[str, object]]
    assumptions: List[str]


class SiteBenchmark(BaseModel):
    """Sites ranked on every metric, with the gap priced."""

    tenant_id: str
    window_days: int
    site_count: int
    sites: List[Dict[str, object]]
    metric_leaders: Dict[str, MetricLeader]
    opportunity: Optional[BenchmarkOpportunity] = None


class FleetComparisonRow(BaseModel):
    """One asset class at one site."""

    machine_type: str
    site: str
    machine_count: int
    maintenance_events: int
    reactive_events: int
    reactive_ratio: float
    downtime_hours: float
    downtime_hours_per_machine: float
    maintenance_cost: float
    maintenance_cost_per_machine: float
    produced_units: int
    avg_oee: float
    mtbf_hours: Optional[float] = None
    is_best_in_class: bool = False
    is_worst_in_class: bool = False
    cost_vs_best: float = 0.0
    cost_ratio_vs_best: Optional[float] = None
