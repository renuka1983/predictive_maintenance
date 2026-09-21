"""The canonical catalogue of product features and the level each requires.

This is the single source of truth for feature gating. Adding a capability to
the platform means adding one entry here; the maturity engine, the feature
toggle table and the frontend navigation all read from it.
"""

from dataclasses import dataclass
from typing import Dict, List

LEVEL_NAMES: Dict[int, str] = {
    0: "Onboarding",
    1: "Reactive (CMMS)",
    2: "Predictive (CMMS + Production)",
    3: "Real-time (Full + IoT)",
    4: "Enterprise (Multi-site)",
}

LEVEL_PRICING: Dict[int, str] = {
    0: "Free",
    1: "$199/mo",
    2: "$499/mo",
    3: "$1,499/mo",
    4: "$2,999/mo",
}


@dataclass(frozen=True)
class Feature:
    key: str
    name: str
    description: str
    required_level: int
    category: str


FEATURES: List[Feature] = [
    # --- Level 0: onboarding ------------------------------------------
    Feature(
        key="data_import",
        name="Data Import",
        description="Upload CMMS, production and sensor data to get started.",
        required_level=0,
        category="onboarding",
    ),
    Feature(
        key="maturity_assessment",
        name="Maturity Assessment",
        description="See your data maturity score and what unlocks next.",
        required_level=0,
        category="onboarding",
    ),
    # --- Level 1: descriptive maintenance analytics -------------------
    Feature(
        key="machine_registry",
        name="Machine Registry",
        description="Central asset register with criticality and status.",
        required_level=1,
        category="core",
    ),
    Feature(
        key="maintenance_history",
        name="Maintenance History",
        description="Searchable work-order log with cost and downtime.",
        required_level=1,
        category="core",
    ),
    Feature(
        key="maintenance_stats",
        name="Maintenance KPIs",
        description="MTBF, MTTR, planned vs reactive ratio and cost trends.",
        required_level=1,
        category="analytics",
    ),
    Feature(
        key="weibull_reliability",
        name="Weibull Reliability Curves",
        description="Fit failure distributions to estimate failure probability.",
        required_level=1,
        category="ml",
    ),
    # --- Level 2: predictive + production context ---------------------
    Feature(
        key="production_tracking",
        name="Production Tracking",
        description="Batch level throughput, yield and OEE.",
        required_level=2,
        category="core",
    ),
    Feature(
        key="failure_risk_scoring",
        name="Failure Risk Scoring",
        description="Machine-learning probability of failure per machine.",
        required_level=2,
        category="ml",
    ),
    Feature(
        key="cascade_impact_analysis",
        name="Cascade Impact Analysis",
        description="Model knock-on losses when one station stops the line.",
        required_level=2,
        category="analytics",
    ),
    Feature(
        key="impact_simulator",
        name="Downtime Impact Simulator",
        description="What-if simulation of downtime cost across the line.",
        required_level=2,
        category="analytics",
    ),
    Feature(
        key="roi_analysis",
        name="ROI Analysis",
        description="Quantify savings from avoiding reactive maintenance.",
        required_level=2,
        category="analytics",
    ),
    # --- Level 3: real-time IoT ---------------------------------------
    Feature(
        key="sensor_telemetry",
        name="Sensor Telemetry",
        description="Stream and chart live IoT measurements per machine.",
        required_level=3,
        category="core",
    ),
    Feature(
        key="realtime_monitoring",
        name="Real-time Monitoring",
        description="Live plant floor view refreshed continuously.",
        required_level=3,
        category="core",
    ),
    Feature(
        key="anomaly_detection",
        name="Anomaly Detection",
        description="Isolation Forest outlier detection over telemetry.",
        required_level=3,
        category="ml",
    ),
    Feature(
        key="rul_prediction",
        name="Remaining Useful Life",
        description="Hours of life left before a machine needs intervention.",
        required_level=3,
        category="ml",
    ),
    # --- Level 4: enterprise ------------------------------------------
    Feature(
        key="multi_site",
        name="Multi-site Rollup",
        description="Roll up performance across every plant and region.",
        required_level=4,
        category="enterprise",
    ),
    Feature(
        key="benchmarking",
        name="Site Benchmarking",
        description="Rank sites on every metric and price the gap to best-in-class.",
        required_level=4,
        category="enterprise",
    ),
    Feature(
        key="fleet_comparison",
        name="Fleet Comparison",
        description="Compare the same class of asset across every site.",
        required_level=4,
        category="enterprise",
    ),
    Feature(
        key="site_registry",
        name="Site Registry",
        description="Register plants with region and country for grouped rollups.",
        required_level=4,
        category="enterprise",
    ),
]

FEATURES_BY_KEY: Dict[str, Feature] = {feature.key: feature for feature in FEATURES}


def features_for_level(level: int) -> List[Feature]:
    """All features a tenant at ``level`` can use."""
    return [f for f in FEATURES if f.required_level <= level]


def features_above_level(level: int) -> List[Feature]:
    """All features still locked for a tenant at ``level``."""
    return [f for f in FEATURES if f.required_level > level]


def features_unlocked_at(level: int) -> List[Feature]:
    """Features that become available exactly at ``level``."""
    return [f for f in FEATURES if f.required_level == level]
