"""Level 4 enterprise analytics: multi-site rollup and benchmarking.

The Level 4 value proposition is comparative, not diagnostic. A single-plant
customer already gets failure prediction at Level 3; what an enterprise buys
at Level 4 is the answer to "which of my plants is worst, by how much, and
what is closing that gap worth?"

Every function here therefore returns a *quantified* comparison rather than a
ranked list: percentile ranks that are directionally normalised, gaps measured
against best-in-class, and those gaps priced in dollars.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Machine, MaintenanceRecord, ProductionBatch, Site

# Benchmark metrics and whether a higher raw value is better. Percentile
# ranks are normalised against this so that "higher percentile = better"
# holds for every metric, which is what makes a composite score meaningful.
BENCHMARK_METRICS: Dict[str, bool] = {
    "avg_oee": True,
    "mtbf_hours": True,
    "downtime_hours_per_machine": False,
    "maintenance_cost_per_machine": False,
    "reactive_ratio": False,
}

METRIC_LABELS: Dict[str, str] = {
    "avg_oee": "Average OEE",
    "mtbf_hours": "Mean time between failures",
    "downtime_hours_per_machine": "Downtime hours per machine",
    "maintenance_cost_per_machine": "Maintenance cost per machine",
    "reactive_ratio": "Reactive maintenance ratio",
}

UNASSIGNED = "unassigned"


def _window_start(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


class EnterpriseService:
    """Cross-site analytics. Callers are responsible for feature gating."""

    # ------------------------------------------------------------------
    # Shared aggregation
    # ------------------------------------------------------------------
    @staticmethod
    def _site_metadata(db: Session, tenant_id: str) -> Dict[str, Site]:
        """Registered sites keyed by the name that machines join on."""
        rows = db.execute(select(Site).where(Site.tenant_id == tenant_id)).scalars()
        return {row.name: row for row in rows}

    @staticmethod
    def _aggregate(
        machines: Sequence[Machine],
        records: Sequence[MaintenanceRecord],
        batches: Sequence[ProductionBatch],
        window_days: int,
    ) -> Dict[str, object]:
        """Reduce one group's raw rows to the comparable metric set.

        Everything is expressed *per machine* so that a 40-machine plant and a
        4-machine plant can be compared without size dominating the result.
        """
        machine_count = len(machines)
        reactive = [r for r in records if r.maintenance_type == "reactive"]

        downtime = sum(r.downtime_hours for r in records)
        cost = sum(r.total_cost for r in records)
        produced = sum(b.produced_units for b in batches)
        good = sum(b.good_units for b in batches)
        oee = (sum(b.oee for b in batches) / len(batches)) if batches else 0.0

        mtbf: Optional[float] = None
        if reactive and machine_count:
            operating_hours = window_days * 24 * machine_count
            mtbf = round((operating_hours - downtime) / len(reactive), 1)

        return {
            "machine_count": machine_count,
            "maintenance_events": len(records),
            "reactive_events": len(reactive),
            "reactive_ratio": round(len(reactive) / len(records), 4) if records else 0.0,
            "downtime_hours": round(downtime, 2),
            "downtime_hours_per_machine": (
                round(downtime / machine_count, 2) if machine_count else 0.0
            ),
            "maintenance_cost": round(cost, 2),
            "maintenance_cost_per_machine": (
                round(cost / machine_count, 2) if machine_count else 0.0
            ),
            "produced_units": produced,
            "good_units": good,
            "quality_rate": round(good / produced, 4) if produced else 0.0,
            "avg_oee": round(oee, 4),
            "mtbf_hours": mtbf,
            "machines_down": sum(1 for m in machines if m.status == "down"),
        }

    @classmethod
    def _grouped_rows(
        cls,
        db: Session,
        tenant_id: str,
        window_days: int,
        group_by: str = "site",
    ) -> Tuple[Dict[str, Dict[str, object]], Dict[str, List[Machine]]]:
        """Aggregate every machine into groups keyed by site or region.

        All maintenance and production rows are fetched in two queries and
        bucketed in memory; querying per group would be an N+1 that grows with
        the customer's plant count.
        """
        machines = list(
            db.execute(select(Machine).where(Machine.tenant_id == tenant_id)).scalars()
        )
        if not machines:
            return {}, {}

        sites = cls._site_metadata(db, tenant_id)

        def key_for(machine: Machine) -> str:
            site_name = machine.site or UNASSIGNED
            if group_by == "region":
                site = sites.get(site_name)
                return (site.region if site and site.region else None) or UNASSIGNED
            return site_name

        grouped: Dict[str, List[Machine]] = defaultdict(list)
        for machine in machines:
            grouped[key_for(machine)].append(machine)

        machine_to_group = {m.id: key_for(m) for m in machines}
        since = _window_start(window_days)
        machine_ids = list(machine_to_group)

        records_by_group: Dict[str, List[MaintenanceRecord]] = defaultdict(list)
        for record in db.execute(
            select(MaintenanceRecord).where(
                MaintenanceRecord.tenant_id == tenant_id,
                MaintenanceRecord.machine_id.in_(machine_ids),
                MaintenanceRecord.start_time >= since,
            )
        ).scalars():
            records_by_group[machine_to_group[record.machine_id]].append(record)

        batches_by_group: Dict[str, List[ProductionBatch]] = defaultdict(list)
        for batch in db.execute(
            select(ProductionBatch).where(
                ProductionBatch.tenant_id == tenant_id,
                ProductionBatch.machine_id.in_(machine_ids),
                ProductionBatch.start_time >= since,
            )
        ).scalars():
            batches_by_group[machine_to_group[batch.machine_id]].append(batch)

        aggregates = {
            group: cls._aggregate(
                group_machines,
                records_by_group.get(group, []),
                batches_by_group.get(group, []),
                window_days,
            )
            for group, group_machines in grouped.items()
        }
        return aggregates, grouped

    # ------------------------------------------------------------------
    # Multi-site rollup
    # ------------------------------------------------------------------
    @classmethod
    def portfolio_rollup(
        cls,
        db: Session,
        tenant_id: str,
        window_days: int = 90,
        group_by: str = "site",
    ) -> Dict[str, object]:
        """Organisation-wide totals plus a per-site (or per-region) breakdown.

        Totals are recomputed from raw counts rather than averaged from the
        group rows: averaging per-machine averages would weight a 4-machine
        plant the same as a 40-machine one.
        """
        if group_by not in ("site", "region"):
            raise ValueError("group_by must be 'site' or 'region'")

        aggregates, grouped = cls._grouped_rows(db, tenant_id, window_days, group_by)
        sites = cls._site_metadata(db, tenant_id)

        groups: List[Dict[str, object]] = []
        for name, metrics in aggregates.items():
            row: Dict[str, object] = {"name": name, **metrics}
            if group_by == "site":
                site = sites.get(name)
                row["region"] = site.region if site else None
                row["country"] = site.country if site else None
                row["display_name"] = (site.display_name if site else None) or name
                row["is_registered"] = site is not None
            groups.append(row)

        groups.sort(key=lambda r: r["avg_oee"], reverse=True)

        total_machines = sum(r["machine_count"] for r in groups)
        total_events = sum(r["maintenance_events"] for r in groups)
        total_reactive = sum(r["reactive_events"] for r in groups)
        total_downtime = sum(r["downtime_hours"] for r in groups)
        total_cost = sum(r["maintenance_cost"] for r in groups)
        total_produced = sum(r["produced_units"] for r in groups)
        total_good = sum(r["good_units"] for r in groups)

        # Machine-weighted OEE so large plants count proportionally.
        weighted_oee = (
            sum(r["avg_oee"] * r["machine_count"] for r in groups) / total_machines
            if total_machines
            else 0.0
        )

        return {
            "tenant_id": tenant_id,
            "window_days": window_days,
            "group_by": group_by,
            "group_count": len(groups),
            "totals": {
                "machine_count": total_machines,
                "machines_down": sum(r["machines_down"] for r in groups),
                "maintenance_events": total_events,
                "reactive_events": total_reactive,
                "reactive_ratio": (
                    round(total_reactive / total_events, 4) if total_events else 0.0
                ),
                "downtime_hours": round(total_downtime, 2),
                "maintenance_cost": round(total_cost, 2),
                "produced_units": total_produced,
                "quality_rate": (
                    round(total_good / total_produced, 4) if total_produced else 0.0
                ),
                "weighted_avg_oee": round(weighted_oee, 4),
                "cost_per_machine": (
                    round(total_cost / total_machines, 2) if total_machines else 0.0
                ),
            },
            "groups": groups,
        }

    # ------------------------------------------------------------------
    # Benchmarking
    # ------------------------------------------------------------------
    @staticmethod
    def _percentile_rank(value: float, population: List[float], higher_is_better: bool) -> float:
        """Share of the population this value beats, on a 0-1 scale.

        Normalised by direction so that 1.0 always means best-in-class,
        whether the underlying metric is one to maximise or minimise.
        """
        if len(population) <= 1:
            return 1.0
        if higher_is_better:
            beaten = sum(1 for other in population if value > other)
        else:
            beaten = sum(1 for other in population if value < other)
        return round(beaten / (len(population) - 1), 4)

    @classmethod
    def benchmark_sites(
        cls, db: Session, tenant_id: str, window_days: int = 90
    ) -> Dict[str, object]:
        """Rank sites on every metric, with best-in-class gaps priced.

        The headline figure is the annualised saving available if every site
        matched the best site's maintenance cost per machine - the number an
        operations director can take to a budget meeting.
        """
        aggregates, _ = cls._grouped_rows(db, tenant_id, window_days, "site")
        sites_meta = cls._site_metadata(db, tenant_id)

        # Only sites that actually ran machines can be benchmarked.
        comparable = {
            name: metrics
            for name, metrics in aggregates.items()
            if metrics["machine_count"] > 0
        }
        if not comparable:
            return {
                "tenant_id": tenant_id,
                "window_days": window_days,
                "site_count": 0,
                "sites": [],
                "metric_leaders": {},
                "opportunity": None,
            }

        populations: Dict[str, List[float]] = {}
        for metric in BENCHMARK_METRICS:
            values = [
                float(m[metric]) for m in comparable.values() if m.get(metric) is not None
            ]
            populations[metric] = values

        rows: List[Dict[str, object]] = []
        for name, metrics in comparable.items():
            site = sites_meta.get(name)
            percentiles: Dict[str, float] = {}
            for metric, higher_is_better in BENCHMARK_METRICS.items():
                value = metrics.get(metric)
                if value is None or not populations[metric]:
                    continue
                percentiles[metric] = cls._percentile_rank(
                    float(value), populations[metric], higher_is_better
                )

            composite = (
                round(sum(percentiles.values()) / len(percentiles), 4)
                if percentiles
                else 0.0
            )
            rows.append(
                {
                    "site": name,
                    "display_name": (site.display_name if site else None) or name,
                    "region": site.region if site else None,
                    **metrics,
                    "percentiles": percentiles,
                    "composite_score": composite,
                }
            )

        # Composite rank: the single ordering that accounts for every metric.
        rows.sort(key=lambda r: r["composite_score"], reverse=True)
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank

        metric_leaders: Dict[str, object] = {}
        for metric, higher_is_better in BENCHMARK_METRICS.items():
            candidates = [r for r in rows if r.get(metric) is not None]
            if not candidates:
                continue
            best = (max if higher_is_better else min)(
                candidates, key=lambda r: float(r[metric])
            )
            worst = (min if higher_is_better else max)(
                candidates, key=lambda r: float(r[metric])
            )
            metric_leaders[metric] = {
                "label": METRIC_LABELS[metric],
                "higher_is_better": higher_is_better,
                "best_site": best["site"],
                "best_value": best[metric],
                "worst_site": worst["site"],
                "worst_value": worst[metric],
                "median": round(median([float(r[metric]) for r in candidates]), 4),
            }

        return {
            "tenant_id": tenant_id,
            "window_days": window_days,
            "site_count": len(rows),
            "sites": rows,
            "metric_leaders": metric_leaders,
            "opportunity": cls._opportunity(rows, window_days),
        }

    @staticmethod
    def _opportunity(rows: List[Dict[str, object]], window_days: int) -> Optional[Dict[str, object]]:
        """Price the gap between every site and the best performer.

        Deliberately conservative: the target is the *best actually observed*
        site, not a theoretical ideal, so the number is defensible as "already
        achieved somewhere in your own estate".
        """
        if len(rows) < 2:
            return None

        best_cost = min(float(r["maintenance_cost_per_machine"]) for r in rows)
        best_downtime = min(float(r["downtime_hours_per_machine"]) for r in rows)
        best_site = min(
            rows, key=lambda r: float(r["maintenance_cost_per_machine"])
        )["site"]

        cost_gap = 0.0
        downtime_gap = 0.0
        per_site: List[Dict[str, object]] = []

        for row in rows:
            machines = int(row["machine_count"])
            site_cost_gap = (
                float(row["maintenance_cost_per_machine"]) - best_cost
            ) * machines
            site_downtime_gap = (
                float(row["downtime_hours_per_machine"]) - best_downtime
            ) * machines
            cost_gap += site_cost_gap
            downtime_gap += site_downtime_gap
            if site_cost_gap > 0:
                per_site.append(
                    {
                        "site": row["site"],
                        "cost_gap": round(site_cost_gap, 2),
                        "downtime_gap_hours": round(site_downtime_gap, 2),
                    }
                )

        per_site.sort(key=lambda r: r["cost_gap"], reverse=True)
        annual_factor = 365 / window_days if window_days else 1.0

        return {
            "benchmark_site": best_site,
            "benchmark_cost_per_machine": round(best_cost, 2),
            "benchmark_downtime_per_machine": round(best_downtime, 2),
            "window_cost_gap": round(cost_gap, 2),
            "annualised_saving": round(cost_gap * annual_factor, 2),
            "annualised_downtime_hours": round(downtime_gap * annual_factor, 2),
            "worst_offenders": per_site[:5],
            "assumptions": [
                f"Target is the best observed site ({best_site}), not a theoretical ideal",
                "Gap is measured per machine, so plant size does not distort it",
                f"Observed window of {window_days} days annualised linearly",
            ],
        }

    # ------------------------------------------------------------------
    # Fleet comparison
    # ------------------------------------------------------------------
    @classmethod
    def fleet_comparison(
        cls,
        db: Session,
        tenant_id: str,
        machine_type: Optional[str] = None,
        window_days: int = 90,
    ) -> List[Dict[str, object]]:
        """Compare the same class of asset across sites.

        Site-level benchmarking can hide the cause: a plant may look expensive
        only because it runs more of one troublesome asset class. Holding the
        machine type constant and varying the site isolates whether the
        difference is the equipment or the operation.
        """
        machines = list(
            db.execute(select(Machine).where(Machine.tenant_id == tenant_id)).scalars()
        )
        if machine_type:
            machines = [m for m in machines if m.machine_type == machine_type]
        if not machines:
            return []

        since = _window_start(window_days)
        machine_ids = [m.id for m in machines]

        records_by_machine: Dict[str, List[MaintenanceRecord]] = defaultdict(list)
        for record in db.execute(
            select(MaintenanceRecord).where(
                MaintenanceRecord.tenant_id == tenant_id,
                MaintenanceRecord.machine_id.in_(machine_ids),
                MaintenanceRecord.start_time >= since,
            )
        ).scalars():
            records_by_machine[record.machine_id].append(record)

        batches_by_machine: Dict[str, List[ProductionBatch]] = defaultdict(list)
        for batch in db.execute(
            select(ProductionBatch).where(
                ProductionBatch.tenant_id == tenant_id,
                ProductionBatch.machine_id.in_(machine_ids),
                ProductionBatch.start_time >= since,
            )
        ).scalars():
            batches_by_machine[batch.machine_id].append(batch)

        # (machine_type, site) -> the machines of that class at that plant.
        cells: Dict[Tuple[str, str], List[Machine]] = defaultdict(list)
        for machine in machines:
            cells[(machine.machine_type or "unspecified", machine.site or UNASSIGNED)].append(
                machine
            )

        rows: List[Dict[str, object]] = []
        for (asset_type, site), cell_machines in cells.items():
            records = [r for m in cell_machines for r in records_by_machine.get(m.id, [])]
            batches = [b for m in cell_machines for b in batches_by_machine.get(m.id, [])]
            metrics = cls._aggregate(cell_machines, records, batches, window_days)
            rows.append({"machine_type": asset_type, "site": site, **metrics})

        # Within each asset class, mark the best and worst site so the
        # outlier is visible without reading every number.
        by_type: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for row in rows:
            by_type[row["machine_type"]].append(row)

        for asset_type, group in by_type.items():
            costs = [float(r["maintenance_cost_per_machine"]) for r in group]
            best, worst = min(costs), max(costs)
            for row in group:
                cost = float(row["maintenance_cost_per_machine"])
                row["is_best_in_class"] = len(group) > 1 and cost == best
                row["is_worst_in_class"] = len(group) > 1 and cost == worst and worst > best
                # How much more this cell costs than the best site running
                # the same equipment.
                row["cost_vs_best"] = round(cost - best, 2)
                row["cost_ratio_vs_best"] = round(cost / best, 2) if best > 0 else None

        rows.sort(key=lambda r: (r["machine_type"], -float(r["maintenance_cost_per_machine"])))
        return rows
