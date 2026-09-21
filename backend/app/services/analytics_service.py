"""Descriptive analytics over maintenance, production and sensor data.

All queries here take a ``tenant_id`` and filter on it - there is no code path
that reads rows without a tenant predicate.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Machine, MaintenanceRecord, ProductionBatch, SensorReading
from app.schemas.analytics import ROIEstimate
from app.schemas.machine import MachineStatus
from app.schemas.maintenance import MaintenanceStats
from app.schemas.production import LineStationSummary, ProductionLineView

# Share of reactive maintenance cost that a predictive programme can avoid.
# Conservative industry figure used for the ROI business case.
PREVENTABLE_SHARE = 0.35


def _window_start(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise naive timestamps (SQLite loses tzinfo) to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class AnalyticsService:
    """Level-aware analytics. Callers are responsible for feature gating."""

    # ------------------------------------------------------------------
    # Level 1 - maintenance
    # ------------------------------------------------------------------
    @staticmethod
    def maintenance_stats(
        db: Session, tenant_id: str, window_days: int = 365
    ) -> MaintenanceStats:
        """Headline CMMS KPIs for the trailing ``window_days``."""
        since = _window_start(window_days)
        records = list(
            db.execute(
                select(MaintenanceRecord).where(
                    MaintenanceRecord.tenant_id == tenant_id,
                    MaintenanceRecord.start_time >= since,
                )
            ).scalars()
        )

        machine_count = int(
            db.execute(
                select(func.count()).select_from(Machine).where(
                    Machine.tenant_id == tenant_id
                )
            ).scalar_one()
            or 0
        )

        total = len(records)
        reactive = [r for r in records if r.maintenance_type == "reactive"]
        planned = [r for r in records if r.maintenance_type != "reactive"]

        total_downtime = sum(r.downtime_hours for r in records)
        total_cost = sum(r.total_cost for r in records)
        labor_cost = sum(r.labor_cost for r in records)
        parts_cost = sum(r.parts_cost for r in records)

        mean_repair = (total_downtime / total) if total else 0.0

        # MTBF: operating hours in the window divided by failures observed.
        mtbf: Optional[float] = None
        if reactive and machine_count:
            operating_hours = window_days * 24 * machine_count
            mtbf = round((operating_hours - total_downtime) / len(reactive), 1)

        # Failure mode Pareto.
        by_mode: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"count": 0, "cost": 0.0, "downtime_hours": 0.0}
        )
        for record in records:
            mode = record.failure_mode or "unspecified"
            by_mode[mode]["count"] += 1
            by_mode[mode]["cost"] += record.total_cost
            by_mode[mode]["downtime_hours"] += record.downtime_hours
        top_modes = sorted(
            (
                {
                    "failure_mode": mode,
                    "count": int(values["count"]),
                    "cost": round(values["cost"], 2),
                    "downtime_hours": round(values["downtime_hours"], 2),
                }
                for mode, values in by_mode.items()
            ),
            key=lambda item: item["cost"],
            reverse=True,
        )[:10]

        # Month-by-month trend for charting.
        by_month: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"count": 0, "reactive": 0, "cost": 0.0, "downtime_hours": 0.0}
        )
        for record in records:
            start = _as_utc(record.start_time)
            key = start.strftime("%Y-%m")
            by_month[key]["count"] += 1
            by_month[key]["cost"] += record.total_cost
            by_month[key]["downtime_hours"] += record.downtime_hours
            if record.maintenance_type == "reactive":
                by_month[key]["reactive"] += 1
        trend = [
            {
                "month": month,
                "count": int(values["count"]),
                "reactive_count": int(values["reactive"]),
                "cost": round(values["cost"], 2),
                "downtime_hours": round(values["downtime_hours"], 2),
            }
            for month, values in sorted(by_month.items())
        ]

        return MaintenanceStats(
            tenant_id=tenant_id,
            window_days=window_days,
            total_records=total,
            planned_count=len(planned),
            reactive_count=len(reactive),
            planned_ratio=round(len(planned) / total, 4) if total else 0.0,
            total_downtime_hours=round(total_downtime, 2),
            total_cost=round(total_cost, 2),
            labor_cost=round(labor_cost, 2),
            parts_cost=round(parts_cost, 2),
            mean_repair_hours=round(mean_repair, 2),
            mtbf_hours=mtbf,
            cost_per_machine=(
                round(total_cost / machine_count, 2) if machine_count else 0.0
            ),
            top_failure_modes=top_modes,
            monthly_trend=trend,
        )

    @staticmethod
    def machine_status(
        db: Session, tenant_id: str, machine: Machine, window_days: int = 365
    ) -> MachineStatus:
        """Per-machine health rollup derived from its maintenance history."""
        since = _window_start(window_days)
        records = list(
            db.execute(
                select(MaintenanceRecord).where(
                    MaintenanceRecord.tenant_id == tenant_id,
                    MaintenanceRecord.machine_id == machine.id,
                    MaintenanceRecord.start_time >= since,
                )
            ).scalars()
        )

        failures = [r for r in records if r.maintenance_type == "reactive"]
        downtime = sum(r.downtime_hours for r in records)
        cost = sum(r.total_cost for r in records)

        last_start = max((_as_utc(r.start_time) for r in records), default=None)
        days_since = (
            (datetime.now(timezone.utc) - last_start).days if last_start else None
        )

        mtbf = None
        if failures:
            operating_hours = window_days * 24
            mtbf = round((operating_hours - downtime) / len(failures), 1)

        # Health score: start at 100 and deduct for failures, downtime and a
        # hard status signal, weighted by how critical the asset is.
        weight = 0.6 + 0.2 * machine.criticality  # 0.8 (C1) .. 1.6 (C5)
        penalty = (len(failures) * 6 + downtime * 0.5) * weight
        if machine.status == "down":
            penalty += 40
        elif machine.status == "degraded":
            penalty += 20
        elif machine.status == "maintenance":
            penalty += 10
        health = max(0.0, min(100.0, 100.0 - penalty))

        return MachineStatus(
            machine_id=machine.id,
            machine_code=machine.machine_code,
            name=machine.name,
            status=machine.status,
            criticality=machine.criticality,
            days_since_last_maintenance=days_since,
            maintenance_count=len(records),
            failure_count=len(failures),
            total_downtime_hours=round(downtime, 2),
            total_maintenance_cost=round(cost, 2),
            mtbf_hours=mtbf,
            health_score=round(health, 1),
        )

    # ------------------------------------------------------------------
    # Level 2 - production
    # ------------------------------------------------------------------
    @staticmethod
    def production_line_view(
        db: Session, tenant_id: str, production_line: str, window_days: int = 30
    ) -> ProductionLineView:
        """Station-by-station OEE for one line, flagging the bottleneck."""
        since = _window_start(window_days)
        machines = list(
            db.execute(
                select(Machine)
                .where(
                    Machine.tenant_id == tenant_id,
                    Machine.production_line == production_line,
                )
                .order_by(Machine.line_position, Machine.machine_code)
            ).scalars()
        )

        stations: List[LineStationSummary] = []
        total_produced = 0
        total_downtime = 0.0

        for machine in machines:
            batches = list(
                db.execute(
                    select(ProductionBatch).where(
                        ProductionBatch.tenant_id == tenant_id,
                        ProductionBatch.machine_id == machine.id,
                        ProductionBatch.start_time >= since,
                    )
                ).scalars()
            )
            produced = sum(b.produced_units for b in batches)
            downtime = sum(b.downtime_minutes for b in batches)
            oee = (sum(b.oee for b in batches) / len(batches)) if batches else 0.0
            yield_rate = (
                sum(b.yield_rate for b in batches) / len(batches) if batches else 0.0
            )

            total_produced += produced
            total_downtime += downtime
            stations.append(
                LineStationSummary(
                    machine_id=machine.id,
                    machine_code=machine.machine_code,
                    name=machine.name,
                    line_position=machine.line_position,
                    status=machine.status,
                    criticality=machine.criticality,
                    oee=round(oee, 4),
                    yield_rate=round(yield_rate, 4),
                    produced_units=produced,
                    downtime_minutes=round(downtime, 2),
                )
            )

        # The bottleneck is the station with the lowest OEE among stations
        # that actually ran.
        active = [s for s in stations if s.produced_units > 0]
        bottleneck_id: Optional[str] = None
        if active:
            bottleneck = min(active, key=lambda s: s.oee)
            bottleneck_id = bottleneck.machine_id
            for station in stations:
                station.is_bottleneck = station.machine_id == bottleneck_id

        line_oee = (
            round(sum(s.oee for s in active) / len(active), 4) if active else 0.0
        )

        return ProductionLineView(
            tenant_id=tenant_id,
            production_line=production_line,
            window_days=window_days,
            stations=stations,
            line_oee=line_oee,
            bottleneck_machine_id=bottleneck_id,
            total_produced_units=total_produced,
            total_downtime_minutes=round(total_downtime, 2),
        )

    @staticmethod
    def roi_estimate(
        db: Session, tenant_id: str, window_days: int = 365
    ) -> ROIEstimate:
        """Value of avoiding a realistic share of reactive maintenance."""
        since = _window_start(window_days)
        reactive = list(
            db.execute(
                select(MaintenanceRecord).where(
                    MaintenanceRecord.tenant_id == tenant_id,
                    MaintenanceRecord.maintenance_type == "reactive",
                    MaintenanceRecord.start_time >= since,
                )
            ).scalars()
        )

        downtime_costs = dict(
            db.execute(
                select(Machine.id, Machine.hourly_downtime_cost).where(
                    Machine.tenant_id == tenant_id
                )
            ).all()
        )

        repair_cost = sum(r.total_cost for r in reactive)
        lost_production = sum(
            r.downtime_hours * downtime_costs.get(r.machine_id, 0.0) for r in reactive
        )
        reactive_cost = repair_cost + lost_production
        preventable = reactive_cost * PREVENTABLE_SHARE
        downtime_avoided = sum(r.downtime_hours for r in reactive) * PREVENTABLE_SHARE

        # Annualise a window that may be shorter or longer than a year.
        annual_factor = 365 / window_days if window_days else 1.0

        return ROIEstimate(
            tenant_id=tenant_id,
            window_days=window_days,
            reactive_cost=round(reactive_cost, 2),
            preventable_cost=round(preventable, 2),
            estimated_annual_savings=round(preventable * annual_factor, 2),
            downtime_hours_avoided=round(downtime_avoided, 2),
            assumptions=[
                f"{PREVENTABLE_SHARE:.0%} of reactive events are preventable with "
                "predictive maintenance",
                "Lost production valued at each machine's hourly_downtime_cost",
                f"Observed window of {window_days} days annualised linearly",
            ],
        )

    # ------------------------------------------------------------------
    # Level 3 - sensors
    # ------------------------------------------------------------------
    @staticmethod
    def sensor_coverage(db: Session, tenant_id: str) -> Dict[str, object]:
        """How much of the estate is instrumented and streaming."""
        machine_count = int(
            db.execute(
                select(func.count()).select_from(Machine).where(
                    Machine.tenant_id == tenant_id
                )
            ).scalar_one()
            or 0
        )
        instrumented = int(
            db.execute(
                select(func.count()).select_from(Machine).where(
                    Machine.tenant_id == tenant_id, Machine.has_sensors.is_(True)
                )
            ).scalar_one()
            or 0
        )
        readings = int(
            db.execute(
                select(func.count()).select_from(SensorReading).where(
                    SensorReading.tenant_id == tenant_id
                )
            ).scalar_one()
            or 0
        )
        sensor_types = [
            row[0]
            for row in db.execute(
                select(SensorReading.sensor_type)
                .where(SensorReading.tenant_id == tenant_id)
                .distinct()
            ).all()
        ]
        return {
            "machine_count": machine_count,
            "instrumented_machines": instrumented,
            "coverage": round(instrumented / machine_count, 4) if machine_count else 0.0,
            "total_readings": readings,
            "sensor_types": sorted(sensor_types),
        }

    # ------------------------------------------------------------------
    # Level 4 - enterprise
    # ------------------------------------------------------------------
    @staticmethod
    def site_benchmark(
        db: Session, tenant_id: str, window_days: int = 90
    ) -> List[Dict[str, object]]:
        """Compare sites on downtime, spend and throughput."""
        since = _window_start(window_days)
        machines = list(
            db.execute(
                select(Machine).where(Machine.tenant_id == tenant_id)
            ).scalars()
        )

        by_site: Dict[str, List[Machine]] = defaultdict(list)
        for machine in machines:
            by_site[machine.site or "unassigned"].append(machine)

        results: List[Dict[str, object]] = []
        for site, site_machines in sorted(by_site.items()):
            machine_ids = [m.id for m in site_machines]
            records = list(
                db.execute(
                    select(MaintenanceRecord).where(
                        MaintenanceRecord.tenant_id == tenant_id,
                        MaintenanceRecord.machine_id.in_(machine_ids),
                        MaintenanceRecord.start_time >= since,
                    )
                ).scalars()
            )
            batches = list(
                db.execute(
                    select(ProductionBatch).where(
                        ProductionBatch.tenant_id == tenant_id,
                        ProductionBatch.machine_id.in_(machine_ids),
                        ProductionBatch.start_time >= since,
                    )
                ).scalars()
            )
            downtime = sum(r.downtime_hours for r in records)
            cost = sum(r.total_cost for r in records)
            oee = (sum(b.oee for b in batches) / len(batches)) if batches else 0.0

            results.append(
                {
                    "site": site,
                    "machine_count": len(site_machines),
                    "maintenance_events": len(records),
                    "downtime_hours": round(downtime, 2),
                    "maintenance_cost": round(cost, 2),
                    "cost_per_machine": (
                        round(cost / len(site_machines), 2) if site_machines else 0.0
                    ),
                    "avg_oee": round(oee, 4),
                    "produced_units": sum(b.produced_units for b in batches),
                }
            )

        results.sort(key=lambda row: row["avg_oee"], reverse=True)
        for rank, row in enumerate(results, start=1):
            row["rank"] = rank
        return results
