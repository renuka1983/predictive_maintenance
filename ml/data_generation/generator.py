"""Synthetic data generation for the three pilot tenants.

The generators produce data with realistic *structure*, not just random
numbers, so that the analytics and ML services have something meaningful to
find:

* Failures are drawn from a Weibull process, so Weibull fits recover the
  shape parameter that was used to create the data.
* Reactive failures are preceded by degraded production batches, so the risk
  model has a learnable signal.
* Sensor traces contain a slow upward drift on machines heading for failure
  plus injected spikes, so RUL and anomaly detection both have targets.

Each tenant is generated at a different data maturity:

* ``tenant-a`` - CMMS only               -> Level 1
* ``tenant-b`` - CMMS + production       -> Level 2
* ``tenant-c`` - CMMS + production + IoT -> Level 3
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

FAILURE_MODES = [
    "bearing_wear",
    "motor_overheat",
    "seal_leak",
    "belt_slip",
    "sensor_drift",
    "hydraulic_fault",
    "electrical_fault",
    "tool_wear",
]

MACHINE_TYPES = [
    ("CNC Mill", "Haas"),
    ("Injection Moulder", "Engel"),
    ("Hydraulic Press", "Schuler"),
    ("Conveyor", "Interroll"),
    ("Industrial Oven", "Despatch"),
    ("Packaging Line", "Bosch"),
    ("Robotic Welder", "Fanuc"),
    ("Grinder", "Okuma"),
]

TECHNICIANS = ["A. Okafor", "L. Fernandes", "M. Suzuki", "R. Patel", "K. Novak"]

# Sensor channel -> (unit, healthy mean, healthy sigma, drift per day when failing)
SENSOR_PROFILES: Dict[str, tuple] = {
    "vibration": ("mm/s", 2.4, 0.25, 0.10),
    "temperature": ("degC", 62.0, 2.0, 0.55),
    "pressure": ("bar", 5.2, 0.18, 0.0),
    "current": ("A", 18.5, 0.9, 0.16),
    "rpm": ("rpm", 1480.0, 22.0, 0.0),
}


@dataclass
class TenantSpec:
    """Everything needed to generate one pilot tenant."""

    slug: str
    name: str
    industry: str
    contact_email: str
    subscription_tier: str
    sites: List[str]
    lines_per_site: int
    machines_per_line: int
    history_days: int
    target_level: int
    with_production: bool = False
    with_sensors: bool = False
    sensor_hours: int = 72
    sensor_interval_minutes: int = 15
    seed: int = 42
    # Weibull shape used to draw times between failures (>1 = wear-out).
    weibull_shape: float = 1.8
    weibull_scale_hours: float = 1400.0
    # Optional registry metadata per site name: (region, country). Only the
    # enterprise tier needs it; Level 1-3 tenants leave it empty.
    site_regions: Dict[str, Tuple[str, str]] = field(default_factory=dict)


@dataclass
class GeneratedData:
    """In-memory payload produced by :func:`generate_tenant`."""

    tenant: Dict
    site_registry: List[Dict] = field(default_factory=list)
    machines: List[Dict] = field(default_factory=list)
    maintenance: List[Dict] = field(default_factory=list)
    production: List[Dict] = field(default_factory=list)
    sensors: List[Dict] = field(default_factory=list)

    def summary(self) -> Dict[str, int]:
        return {
            "sites": len(self.site_registry),
            "machines": len(self.machines),
            "maintenance_records": len(self.maintenance),
            "production_batches": len(self.production),
            "sensor_readings": len(self.sensors),
        }


# --------------------------------------------------------------------------
# Pilot tenant definitions
# --------------------------------------------------------------------------

PILOT_TENANTS: Dict[str, TenantSpec] = {
    "tenant-a": TenantSpec(
        slug="tenant-a",
        name="Aurora Metalworks",
        industry="Metal Fabrication",
        contact_email="ops@aurora-metalworks.example",
        subscription_tier="level_1",
        sites=["Sheffield Plant"],
        lines_per_site=2,
        machines_per_line=4,
        history_days=540,
        target_level=1,
        seed=11,
        weibull_shape=1.6,
        weibull_scale_hours=1500.0,
    ),
    "tenant-b": TenantSpec(
        slug="tenant-b",
        name="Borealis Plastics",
        industry="Injection Moulding",
        contact_email="maintenance@borealis-plastics.example",
        subscription_tier="level_2",
        sites=["Tampere Works"],
        lines_per_site=3,
        machines_per_line=5,
        history_days=540,
        target_level=2,
        with_production=True,
        seed=22,
        weibull_shape=2.1,
        weibull_scale_hours=1200.0,
    ),
    "tenant-c": TenantSpec(
        slug="tenant-c",
        name="Cascade Foods",
        industry="Food Processing",
        contact_email="reliability@cascade-foods.example",
        subscription_tier="level_3",
        sites=["Portland Line 1"],
        lines_per_site=3,
        machines_per_line=5,
        history_days=540,
        target_level=3,
        with_production=True,
        with_sensors=True,
        sensor_hours=96,
        sensor_interval_minutes=10,
        seed=33,
        weibull_shape=2.4,
        weibull_scale_hours=900.0,
    ),
    "tenant-d": TenantSpec(
        slug="tenant-d",
        name="Delta Industries",
        industry="Automotive Components",
        contact_email="group.reliability@delta-industries.example",
        subscription_tier="level_4",
        sites=["Detroit Works", "Monterrey Plant", "Brno Facility"],
        lines_per_site=2,
        machines_per_line=4,
        history_days=540,
        target_level=4,
        with_production=True,
        with_sensors=True,
        sensor_hours=96,
        sensor_interval_minutes=15,
        seed=44,
        weibull_shape=2.2,
        weibull_scale_hours=1100.0,
        site_regions={
            "Detroit Works": ("North America", "USA"),
            "Monterrey Plant": ("North America", "Mexico"),
            "Brno Facility": ("Europe", "Czechia"),
        },
    ),
}


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def _weibull_interval(rng: random.Random, shape: float, scale: float) -> float:
    """Draw a time-between-failures sample by inverse-transform sampling."""
    u = max(rng.random(), 1e-9)
    return scale * ((-math.log(u)) ** (1.0 / shape))


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _site_factor(spec: TenantSpec, site: Optional[str]) -> float:
    """How much worse than the flagship plant this site runs.

    Real estates are uneven, and a benchmark over identical sites would have
    nothing to report. Sites degrade down the list: the first is the
    best-in-class performer, each subsequent one fails more often, costs more
    to fix and yields less.
    """
    if not site or site not in spec.sites:
        return 1.0
    return 1.0 + 0.35 * spec.sites.index(site)


def _build_machines(spec: TenantSpec, rng: random.Random) -> List[Dict]:
    """Create the asset register, positioned along production lines."""
    machines: List[Dict] = []
    counter = 1

    for site in spec.sites:
        site_tag = "".join(word[0] for word in site.split())[:3].upper()
        for line_index in range(1, spec.lines_per_site + 1):
            line_name = f"{site_tag}-LINE-{line_index}"
            for position in range(1, spec.machines_per_line + 1):
                machine_type, manufacturer = MACHINE_TYPES[
                    (counter - 1) % len(MACHINE_TYPES)
                ]
                # Criticality peaks in the middle of the line, where a stop
                # starves the most downstream stations.
                midpoint = (spec.machines_per_line + 1) / 2
                criticality = max(
                    1, min(5, 5 - int(abs(position - midpoint)))
                )
                base_output = rng.uniform(80, 260)

                machines.append(
                    {
                        "machine_code": f"{site_tag}-M{counter:03d}",
                        "name": f"{machine_type} {counter:02d}",
                        "machine_type": machine_type,
                        "manufacturer": manufacturer,
                        "model_number": f"{manufacturer[:3].upper()}-{rng.randint(1000, 9999)}",
                        "site": site,
                        "production_line": line_name,
                        "line_position": position,
                        "criticality": criticality,
                        "status": "operational",
                        "installation_date": (
                            date.today() - timedelta(days=rng.randint(400, 3600))
                        ).isoformat(),
                        "hourly_output_units": round(base_output, 1),
                        "hourly_downtime_cost": round(
                            base_output * rng.uniform(6.0, 14.0), 2
                        ),
                        "has_sensors": spec.with_sensors,
                    }
                )
                counter += 1

    return machines


def _build_maintenance(
    spec: TenantSpec, machines: List[Dict], rng: random.Random, now: datetime
) -> List[Dict]:
    """Generate work orders: Weibull-timed failures plus a PM schedule."""
    records: List[Dict] = []
    start = now - timedelta(days=spec.history_days)
    order_number = 1

    for machine in machines:
        # --- Reactive failures from a Weibull process -------------------
        # Higher criticality machines run harder, so they fail sooner; weaker
        # sites compress the characteristic life further still.
        factor = _site_factor(spec, machine.get("site"))
        scale = (
            spec.weibull_scale_hours
            * (1.25 - 0.08 * machine["criticality"])
            / factor
        )
        cursor = start + timedelta(hours=rng.uniform(0, 400))

        while cursor < now:
            interval = _weibull_interval(rng, spec.weibull_shape, scale)
            cursor += timedelta(hours=interval)
            if cursor >= now:
                break

            downtime = round(max(0.5, rng.gauss(5.5, 2.4)), 2)
            labor_hours = round(downtime * rng.uniform(0.8, 1.6), 2)
            labor_cost = round(labor_hours * rng.uniform(55, 95) * factor, 2)
            parts_cost = round(rng.uniform(150, 3200) * factor, 2)

            records.append(
                {
                    "machine_code": machine["machine_code"],
                    "work_order_number": f"WO-{order_number:06d}",
                    "maintenance_type": "reactive",
                    "failure_mode": rng.choice(FAILURE_MODES),
                    "description": "Unplanned stoppage; line halted pending repair.",
                    "start_time": _iso(cursor),
                    "end_time": _iso(cursor + timedelta(hours=downtime)),
                    "downtime_hours": downtime,
                    "labor_hours": labor_hours,
                    "labor_cost": labor_cost,
                    "parts_cost": parts_cost,
                    "total_cost": round(labor_cost + parts_cost, 2),
                    "technician": rng.choice(TECHNICIANS),
                }
            )
            order_number += 1

        # --- Planned preventive maintenance every ~45 days --------------
        pm_cursor = start + timedelta(days=rng.uniform(0, 45))
        while pm_cursor < now:
            downtime = round(max(0.5, rng.gauss(2.2, 0.7)), 2)
            labor_hours = round(downtime * rng.uniform(0.9, 1.3), 2)
            labor_cost = round(labor_hours * rng.uniform(50, 80), 2)
            parts_cost = round(rng.uniform(40, 600), 2)

            records.append(
                {
                    "machine_code": machine["machine_code"],
                    "work_order_number": f"WO-{order_number:06d}",
                    "maintenance_type": rng.choice(["planned", "preventive"]),
                    "failure_mode": "scheduled_service",
                    "description": "Routine service: lubrication, inspection, calibration.",
                    "start_time": _iso(pm_cursor),
                    "end_time": _iso(pm_cursor + timedelta(hours=downtime)),
                    "downtime_hours": downtime,
                    "labor_hours": labor_hours,
                    "labor_cost": labor_cost,
                    "parts_cost": parts_cost,
                    "total_cost": round(labor_cost + parts_cost, 2),
                    "technician": rng.choice(TECHNICIANS),
                }
            )
            order_number += 1
            pm_cursor += timedelta(days=rng.uniform(38, 52))

    records.sort(key=lambda r: r["start_time"])
    return records


def _build_production(
    spec: TenantSpec,
    machines: List[Dict],
    maintenance: List[Dict],
    rng: random.Random,
    now: datetime,
) -> List[Dict]:
    """Generate daily batches whose quality dips ahead of a failure.

    That dip is the signal the Level 2 risk model learns from: degraded yield
    and OEE in the days before a reactive work order.
    """
    batches: List[Dict] = []
    # Production history is shorter than the CMMS history - typical of a
    # customer that connected its MES after its CMMS.
    days = min(spec.history_days, 400)
    start = now - timedelta(days=days)

    failures_by_machine: Dict[str, List[datetime]] = {}
    for record in maintenance:
        if record["maintenance_type"] == "reactive":
            failures_by_machine.setdefault(record["machine_code"], []).append(
                datetime.fromisoformat(record["start_time"])
            )

    batch_number = 1
    for machine in machines:
        failures = sorted(failures_by_machine.get(machine["machine_code"], []))
        rated = machine["hourly_output_units"]

        for day in range(days):
            day_start = start + timedelta(days=day, hours=6)
            if day_start.weekday() >= 5 and rng.random() < 0.6:
                continue  # Reduced weekend running.

            # How close is the next failure? Degradation ramps in over 10 days.
            next_failure = next((f for f in failures if f > day_start), None)
            days_to_failure = (
                (next_failure - day_start).total_seconds() / 86400
                if next_failure
                else 999
            )
            degradation = (
                max(0.0, (10 - days_to_failure) / 10) if days_to_failure < 10 else 0.0
            )

            shift_hours = rng.uniform(7.0, 8.0)
            planned_units = int(rated * shift_hours)
            # Performance and quality both decay as failure approaches, and
            # start lower at the weaker sites.
            site_drag = (_site_factor(spec, machine.get("site")) - 1.0) * 0.12
            performance = max(
                0.35, rng.gauss(0.93, 0.05) - 0.35 * degradation - site_drag
            )
            produced = int(planned_units * performance)
            defect_rate = min(
                0.35,
                max(0.005, rng.gauss(0.02, 0.008) + 0.10 * degradation + site_drag * 0.25),
            )
            defective = int(produced * defect_rate)
            scrap = int(produced * defect_rate * 0.35)

            planned_runtime = round(shift_hours * 60, 1)
            downtime_minutes = round(
                max(0.0, rng.gauss(18, 12) + 90 * degradation), 1
            )
            actual_runtime = round(max(30.0, planned_runtime - downtime_minutes), 1)

            batches.append(
                {
                    "machine_code": machine["machine_code"],
                    "batch_number": f"B-{batch_number:07d}",
                    "product_code": f"P-{rng.randint(100, 140)}",
                    "start_time": _iso(day_start),
                    "end_time": _iso(day_start + timedelta(hours=shift_hours)),
                    "planned_units": planned_units,
                    "produced_units": produced,
                    "defective_units": defective,
                    "scrap_units": scrap,
                    "planned_runtime_minutes": planned_runtime,
                    "actual_runtime_minutes": actual_runtime,
                    "downtime_minutes": downtime_minutes,
                }
            )
            batch_number += 1

    batches.sort(key=lambda b: b["start_time"])
    return batches


def _build_sensors(
    spec: TenantSpec, machines: List[Dict], rng: random.Random, now: datetime
) -> List[Dict]:
    """Generate recent telemetry with drift on degrading machines and spikes.

    A third of the fleet is put on a degradation path so that RUL prediction
    returns a finite answer, and rare spikes give anomaly detection targets.
    """
    readings: List[Dict] = []
    start = now - timedelta(hours=spec.sensor_hours)
    step = timedelta(minutes=spec.sensor_interval_minutes)
    steps = int(spec.sensor_hours * 60 / spec.sensor_interval_minutes)

    for index, machine in enumerate(machines):
        # Every third machine is degrading; the rest run healthy.
        degrading = index % 3 == 0
        channels = ["vibration", "temperature", "current", "pressure", "rpm"]

        for channel in channels:
            unit, mean, sigma, drift_per_day = SENSOR_PROFILES[channel]
            for tick in range(steps):
                timestamp = start + step * tick
                elapsed_days = (timestamp - start).total_seconds() / 86400

                value = rng.gauss(mean, sigma)
                if degrading and drift_per_day:
                    # Mild upward drift with slight acceleration. Calibrated so
                    # that over the generated window the signal rises clearly
                    # above noise but stays below the 3-sigma alarm threshold,
                    # leaving a finite remaining useful life to predict.
                    value += drift_per_day * elapsed_days ** 1.2

                quality = "good"
                # Rare transient spike -> anomaly detection target.
                if rng.random() < 0.004:
                    value += rng.choice([-1, 1]) * sigma * rng.uniform(6, 12)
                    quality = "suspect"

                readings.append(
                    {
                        "machine_code": machine["machine_code"],
                        "sensor_type": channel,
                        "value": round(value, 4),
                        "unit": unit,
                        "quality": quality,
                        "recorded_at": _iso(timestamp),
                    }
                )

    return readings


def generate_tenant(spec: TenantSpec, now: Optional[datetime] = None) -> GeneratedData:
    """Generate a complete dataset for one tenant specification."""
    rng = random.Random(spec.seed)
    now = now or datetime.now(timezone.utc)

    data = GeneratedData(
        tenant={
            "slug": spec.slug,
            "name": spec.name,
            "industry": spec.industry,
            "contact_email": spec.contact_email,
            "subscription_tier": spec.subscription_tier,
        }
    )

    data.site_registry = [
        {
            "name": site,
            "display_name": site,
            "region": spec.site_regions.get(site, (None, None))[0],
            "country": spec.site_regions.get(site, (None, None))[1],
        }
        for site in spec.sites
    ]
    data.machines = _build_machines(spec, rng)
    data.maintenance = _build_maintenance(spec, data.machines, rng, now)

    if spec.with_production:
        data.production = _build_production(
            spec, data.machines, data.maintenance, rng, now
        )
    if spec.with_sensors:
        data.sensors = _build_sensors(spec, data.machines, rng, now)

    return data


def generate_all(now: Optional[datetime] = None) -> Dict[str, GeneratedData]:
    """Generate all three pilot tenants."""
    return {slug: generate_tenant(spec, now) for slug, spec in PILOT_TENANTS.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant",
        choices=sorted(PILOT_TENANTS) + ["all"],
        default="all",
        help="Which pilot tenant to generate",
    )
    args = parser.parse_args()

    targets = (
        PILOT_TENANTS if args.tenant == "all" else {args.tenant: PILOT_TENANTS[args.tenant]}
    )
    for slug, spec in targets.items():
        data = generate_tenant(spec)
        counts = data.summary()
        print(f"{slug} ({spec.name}) - target Level {spec.target_level}")
        for key, value in counts.items():
            print(f"    {key:22} {value:>8,}")


if __name__ == "__main__":
    main()
