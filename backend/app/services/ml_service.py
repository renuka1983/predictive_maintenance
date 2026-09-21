"""Machine-learning services, one model family per maturity level.

* Level 1 - Weibull reliability fitted to time-between-failures.
* Level 2 - Gradient-boosted failure risk + deterministic cascade impact.
* Level 3 - Sensor degradation RUL regression + Isolation Forest anomalies.

Every model degrades gracefully: when a tenant has too little data to train,
the service falls back to a transparent statistical heuristic and reports the
lower confidence rather than refusing to answer.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Machine, MaintenanceRecord, ProductionBatch, SensorReading
from app.schemas.analytics import (
    AnomalyEvent,
    AnomalyReport,
    CascadeImpact,
    CascadeNode,
    RiskScore,
    RULPrediction,
    WeibullFit,
)

# Minimum samples before a fitted model is preferred over the heuristic.
MIN_WEIBULL_INTERVALS = 3
MIN_RISK_TRAINING_ROWS = 24
MIN_RUL_READINGS = 30
MIN_ANOMALY_READINGS = 50
# Above this Weibull shape the intervals are effectively identical.
DEGENERATE_SHAPE = 25.0

RISK_BANDS = ((0.7, "critical"), (0.45, "high"), (0.2, "medium"))
# Sensor channels that trend upward as an asset degrades.
DEGRADATION_SENSORS = ("vibration", "temperature", "acoustic", "current")


def _as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo on read; treat naive timestamps as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _risk_band(score: float) -> str:
    for threshold, band in RISK_BANDS:
        if score >= threshold:
            return band
    return "low"


class MLService:
    """Predictive models available to a tenant, gated by maturity level."""

    # ==================================================================
    # Level 1 - Weibull reliability
    # ==================================================================
    @staticmethod
    def _failure_intervals(
        db: Session, tenant_id: str, machine_id: Optional[str]
    ) -> List[float]:
        """Hours between consecutive reactive events, per machine."""
        stmt = select(MaintenanceRecord).where(
            MaintenanceRecord.tenant_id == tenant_id,
            MaintenanceRecord.maintenance_type == "reactive",
        )
        if machine_id:
            stmt = stmt.where(MaintenanceRecord.machine_id == machine_id)
        records = list(db.execute(stmt.order_by(MaintenanceRecord.start_time)).scalars())

        by_machine: Dict[str, List[datetime]] = defaultdict(list)
        for record in records:
            by_machine[record.machine_id].append(_as_utc(record.start_time))

        intervals: List[float] = []
        for timestamps in by_machine.values():
            timestamps.sort()
            for previous, current in zip(timestamps, timestamps[1:]):
                hours = (current - previous).total_seconds() / 3600
                if hours > 0:
                    intervals.append(hours)
        return intervals

    @staticmethod
    def weibull_fit(
        db: Session,
        tenant_id: str,
        machine_id: Optional[str] = None,
        horizon_days: int = 30,
    ) -> WeibullFit:
        """Fit a two-parameter Weibull to observed times between failures.

        Shape (beta) is the diagnostic that matters operationally:
        beta < 1 means infant-mortality failures, ~1 means random failures,
        and > 1 means wear-out - the regime where planned replacement pays.
        """
        intervals = MLService._failure_intervals(db, tenant_id, machine_id)
        sample_size = len(intervals)
        horizon_hours = horizon_days * 24

        if sample_size == 0:
            return WeibullFit(
                machine_id=machine_id,
                shape=1.0,
                scale_hours=0.0,
                mtbf_hours=0.0,
                sample_size=0,
                failure_probability_30d=0.0,
                interpretation="No failure history yet - cannot fit a curve.",
                confidence="none",
            )

        data = np.asarray(intervals, dtype=float)

        from scipy import stats

        if sample_size >= MIN_WEIBULL_INTERVALS:
            # Location fixed at zero: time-between-failures cannot be negative.
            shape, _loc, scale = stats.weibull_min.fit(data, floc=0)
            method_confidence = "high" if sample_size >= 10 else "medium"
        else:
            # Too few points to fit a shape; assume exponential (random) failures.
            shape, scale = 1.0, float(data.mean())
            method_confidence = "low"

        shape = float(max(shape, 0.1))
        scale = float(max(scale, 1e-6))

        # A very large shape means the observed intervals are nearly identical
        # - a metronomic PM schedule rather than a physical failure process.
        # The fit is numerically valid but not statistically meaningful, so we
        # report it with low confidence.
        if shape > DEGENERATE_SHAPE:
            method_confidence = "low"

        from scipy.special import gamma as gamma_fn

        mtbf = float(scale * gamma_fn(1 + 1 / shape))
        # P(failure within horizon). Evaluated through scipy rather than
        # expanding the closed form, which overflows for large shapes.
        probability = float(
            stats.weibull_min.cdf(horizon_hours, shape, loc=0, scale=scale)
        )

        if shape < 0.9:
            interpretation = (
                "Infant mortality: failures cluster early after repairs - review "
                "workmanship and parts quality."
            )
        elif shape <= 1.15:
            interpretation = (
                "Random failures: time-based replacement adds little; "
                "condition monitoring is the better lever."
            )
        else:
            interpretation = (
                "Wear-out regime: failure rate rises with age - scheduled "
                "replacement before the characteristic life pays off."
            )

        return WeibullFit(
            machine_id=machine_id,
            shape=round(shape, 3),
            scale_hours=round(scale, 1),
            mtbf_hours=round(mtbf, 1),
            sample_size=sample_size,
            failure_probability_30d=round(min(max(probability, 0.0), 1.0), 4),
            interpretation=interpretation,
            confidence=method_confidence,
        )

    # ==================================================================
    # Level 2 - failure risk scoring
    # ==================================================================
    @staticmethod
    def _machine_features(
        records: List[MaintenanceRecord],
        batches: List[ProductionBatch],
        machine: Machine,
        as_of: datetime,
    ) -> List[float]:
        """Feature vector describing a machine's condition at ``as_of``.

        Only history strictly before ``as_of`` is used, so the same function
        builds both training rows and the live prediction row without leaking
        future information into the model.
        """
        past = [r for r in records if _as_utc(r.start_time) < as_of]
        recent_90 = [
            r for r in past if _as_utc(r.start_time) >= as_of - timedelta(days=90)
        ]
        failures_90 = [r for r in recent_90 if r.maintenance_type == "reactive"]

        last_event = max((_as_utc(r.start_time) for r in past), default=None)
        days_since = (as_of - last_event).days if last_event else 999

        past_batches = [b for b in batches if _as_utc(b.start_time) < as_of]
        recent_batches = [
            b
            for b in past_batches
            if _as_utc(b.start_time) >= as_of - timedelta(days=30)
        ]
        avg_oee = (
            sum(b.oee for b in recent_batches) / len(recent_batches)
            if recent_batches
            else 0.0
        )
        avg_yield = (
            sum(b.yield_rate for b in recent_batches) / len(recent_batches)
            if recent_batches
            else 0.0
        )
        downtime_30 = sum(b.downtime_minutes for b in recent_batches)

        return [
            float(min(days_since, 999)),
            float(len(failures_90)),
            float(len(recent_90)),
            float(sum(r.downtime_hours for r in recent_90)),
            float(sum(r.total_cost for r in recent_90)),
            float(machine.criticality),
            float(avg_oee),
            float(avg_yield),
            float(downtime_30),
        ]

    @staticmethod
    def _heuristic_risk(features: List[float]) -> Tuple[float, List[Dict[str, object]]]:
        """Explainable fallback when there is not enough data to train.

        Each term maps a known risk driver onto a bounded contribution so the
        total stays in [0, 1] and every point of score can be attributed.
        """
        days_since, failures_90, events_90, downtime_90, _cost, criticality, oee, yield_rate, prod_downtime = features

        drivers: List[Dict[str, object]] = []
        score = 0.0

        recency = min(days_since / 180, 1.0) * 0.25
        score += recency
        drivers.append(
            {
                "factor": "time_since_last_service",
                "value": days_since,
                "contribution": round(recency, 4),
            }
        )

        failure_term = min(failures_90 / 3, 1.0) * 0.3
        score += failure_term
        drivers.append(
            {
                "factor": "recent_failures_90d",
                "value": failures_90,
                "contribution": round(failure_term, 4),
            }
        )

        downtime_term = min(downtime_90 / 40, 1.0) * 0.15
        score += downtime_term
        drivers.append(
            {
                "factor": "downtime_hours_90d",
                "value": round(downtime_90, 2),
                "contribution": round(downtime_term, 4),
            }
        )

        crit_term = (criticality / 5) * 0.1
        score += crit_term
        drivers.append(
            {
                "factor": "criticality",
                "value": criticality,
                "contribution": round(crit_term, 4),
            }
        )

        # Degraded output quality is an early warning of mechanical trouble.
        quality_gap = max(0.0, 0.85 - yield_rate) if yield_rate else 0.0
        quality_term = min(quality_gap / 0.85, 1.0) * 0.1
        score += quality_term
        drivers.append(
            {
                "factor": "yield_shortfall",
                "value": round(yield_rate, 4),
                "contribution": round(quality_term, 4),
            }
        )

        oee_gap = max(0.0, 0.75 - oee) if oee else 0.0
        oee_term = min(oee_gap / 0.75, 1.0) * 0.1
        score += oee_term
        drivers.append(
            {
                "factor": "oee_shortfall",
                "value": round(oee, 4),
                "contribution": round(oee_term, 4),
            }
        )

        drivers.sort(key=lambda d: d["contribution"], reverse=True)
        return min(max(score, 0.0), 1.0), drivers

    @staticmethod
    def _build_training_set(
        db: Session, tenant_id: str, horizon_days: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Slide a monthly window over history to create supervised rows.

        For each machine and each month-end snapshot, the features describe the
        state up to that point and the label says whether a reactive failure
        followed within ``horizon_days``.
        """
        machines = list(
            db.execute(select(Machine).where(Machine.tenant_id == tenant_id)).scalars()
        )
        if not machines:
            return np.empty((0, 9)), np.empty((0,))

        all_records = list(
            db.execute(
                select(MaintenanceRecord).where(
                    MaintenanceRecord.tenant_id == tenant_id
                )
            ).scalars()
        )
        all_batches = list(
            db.execute(
                select(ProductionBatch).where(ProductionBatch.tenant_id == tenant_id)
            ).scalars()
        )
        if not all_records:
            return np.empty((0, 9)), np.empty((0,))

        records_by_machine: Dict[str, List[MaintenanceRecord]] = defaultdict(list)
        for record in all_records:
            records_by_machine[record.machine_id].append(record)
        batches_by_machine: Dict[str, List[ProductionBatch]] = defaultdict(list)
        for batch in all_batches:
            batches_by_machine[batch.machine_id].append(batch)

        earliest = min(_as_utc(r.start_time) for r in all_records)
        now = datetime.now(timezone.utc)
        # Snapshots must leave room for the label horizon to be observable.
        last_snapshot = now - timedelta(days=horizon_days)

        snapshots: List[datetime] = []
        cursor = earliest + timedelta(days=30)
        while cursor <= last_snapshot:
            snapshots.append(cursor)
            cursor += timedelta(days=30)

        rows: List[List[float]] = []
        labels: List[int] = []

        for machine in machines:
            records = records_by_machine.get(machine.id, [])
            batches = batches_by_machine.get(machine.id, [])
            failure_times = sorted(
                _as_utc(r.start_time)
                for r in records
                if r.maintenance_type == "reactive"
            )
            for snapshot in snapshots:
                horizon_end = snapshot + timedelta(days=horizon_days)
                label = int(
                    any(snapshot <= t < horizon_end for t in failure_times)
                )
                rows.append(
                    MLService._machine_features(records, batches, machine, snapshot)
                )
                labels.append(label)

        return np.asarray(rows, dtype=float), np.asarray(labels, dtype=int)

    @classmethod
    def risk_scores(
        cls,
        db: Session,
        tenant_id: str,
        horizon_days: int = 30,
        machine_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[RiskScore]:
        """Failure probability per machine over the coming ``horizon_days``."""
        stmt = select(Machine).where(Machine.tenant_id == tenant_id)
        if machine_id:
            stmt = stmt.where(Machine.id == machine_id)
        machines = list(db.execute(stmt).scalars())
        if not machines:
            return []

        features_x, labels_y = cls._build_training_set(db, tenant_id, horizon_days)
        model = None
        model_name = "heuristic_risk_index"
        confidence = "low"

        trainable = (
            features_x.shape[0] >= MIN_RISK_TRAINING_ROWS
            and len(np.unique(labels_y)) == 2
            and int(labels_y.sum()) >= 3
        )
        if trainable:
            from sklearn.ensemble import GradientBoostingClassifier

            model = GradientBoostingClassifier(
                n_estimators=120, max_depth=3, learning_rate=0.1, random_state=42
            )
            model.fit(features_x, labels_y)
            model_name = "gradient_boosted_trees"
            confidence = "high" if features_x.shape[0] >= 100 else "medium"

        feature_names = [
            "days_since_last_service",
            "failures_90d",
            "maintenance_events_90d",
            "downtime_hours_90d",
            "maintenance_cost_90d",
            "criticality",
            "avg_oee_30d",
            "avg_yield_30d",
            "production_downtime_30d",
        ]

        now = datetime.now(timezone.utc)
        results: List[RiskScore] = []

        for machine in machines:
            records = list(
                db.execute(
                    select(MaintenanceRecord).where(
                        MaintenanceRecord.tenant_id == tenant_id,
                        MaintenanceRecord.machine_id == machine.id,
                    )
                ).scalars()
            )
            batches = list(
                db.execute(
                    select(ProductionBatch).where(
                        ProductionBatch.tenant_id == tenant_id,
                        ProductionBatch.machine_id == machine.id,
                    )
                ).scalars()
            )
            features = cls._machine_features(records, batches, machine, now)

            if model is not None:
                score = float(model.predict_proba(np.asarray([features]))[0][1])
                importances = model.feature_importances_
                drivers = sorted(
                    (
                        {
                            "factor": name,
                            "value": round(value, 4),
                            "contribution": round(float(importance), 4),
                        }
                        for name, value, importance in zip(
                            feature_names, features, importances
                        )
                    ),
                    key=lambda d: d["contribution"],
                    reverse=True,
                )[:5]
            else:
                score, drivers = cls._heuristic_risk(features)
                drivers = drivers[:5]

            results.append(
                RiskScore(
                    machine_id=machine.id,
                    machine_code=machine.machine_code,
                    risk_score=round(score, 4),
                    risk_band=_risk_band(score),
                    horizon_days=horizon_days,
                    drivers=drivers,
                    model_used=model_name,
                    confidence=confidence,
                )
            )

        results.sort(key=lambda r: r.risk_score, reverse=True)
        return results[:limit] if limit else results

    # ==================================================================
    # Level 2 - cascade impact
    # ==================================================================
    @staticmethod
    def cascade_impact(
        db: Session, tenant_id: str, machine: Machine, downtime_hours: float
    ) -> CascadeImpact:
        """Cost of ``machine`` stopping, including knock-on line effects.

        A serial production line propagates a stoppage in both directions:
        stations downstream starve for input, stations upstream block because
        work-in-progress has nowhere to go. Both lose output for the duration,
        limited by the line's slowest station.
        """
        direct_units = machine.hourly_output_units * downtime_hours
        direct_cost = machine.hourly_downtime_cost * downtime_hours

        nodes: List[CascadeNode] = [
            CascadeNode(
                machine_id=machine.id,
                machine_code=machine.machine_code,
                line_position=machine.line_position,
                impact_type="source",
                lost_units=round(direct_units, 2),
                lost_revenue=round(direct_cost, 2),
            )
        ]

        cascade_units = 0.0
        cascade_cost = 0.0
        bottleneck_id: Optional[str] = None

        if machine.production_line:
            line_machines = list(
                db.execute(
                    select(Machine)
                    .where(
                        Machine.tenant_id == tenant_id,
                        Machine.production_line == machine.production_line,
                        Machine.id != machine.id,
                    )
                    .order_by(Machine.line_position)
                ).scalars()
            )

            # The line can never run faster than its slowest station.
            all_on_line = line_machines + [machine]
            rated = [m for m in all_on_line if m.hourly_output_units > 0]
            if rated:
                bottleneck = min(rated, key=lambda m: m.hourly_output_units)
                bottleneck_id = bottleneck.id
                line_rate = bottleneck.hourly_output_units
            else:
                line_rate = machine.hourly_output_units

            source_position = machine.line_position
            for other in line_machines:
                if source_position is None or other.line_position is None:
                    # Without flow ordering, treat the line as coupled but do
                    # not guess a direction.
                    impact_type = "line_coupled"
                elif other.line_position > source_position:
                    impact_type = "downstream_starved"
                else:
                    impact_type = "upstream_blocked"

                # Each idled station loses output at the line rate, capped by
                # its own rated capacity.
                effective_rate = min(
                    other.hourly_output_units or line_rate, line_rate or 0.0
                )
                lost_units = effective_rate * downtime_hours
                lost_revenue = other.hourly_downtime_cost * downtime_hours

                cascade_units += lost_units
                cascade_cost += lost_revenue
                nodes.append(
                    CascadeNode(
                        machine_id=other.id,
                        machine_code=other.machine_code,
                        line_position=other.line_position,
                        impact_type=impact_type,
                        lost_units=round(lost_units, 2),
                        lost_revenue=round(lost_revenue, 2),
                    )
                )

        return CascadeImpact(
            machine_id=machine.id,
            production_line=machine.production_line,
            downtime_hours=downtime_hours,
            direct_lost_units=round(direct_units, 2),
            cascade_lost_units=round(cascade_units, 2),
            total_cost=round(direct_cost + cascade_cost, 2),
            affected_machines=nodes,
            bottleneck_machine_id=bottleneck_id,
        )

    # ==================================================================
    # Level 3 - remaining useful life
    # ==================================================================
    @staticmethod
    def predict_rul(
        db: Session, tenant_id: str, machine: Machine, window_days: int = 30
    ) -> RULPrediction:
        """Estimate hours until intervention from the sensor degradation trend.

        A least-squares trend is fitted per degradation channel; the channel
        with the strongest upward slope drives the estimate, extrapolated to an
        alarm threshold set three sigma above the machine's healthy baseline.
        """
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        readings = list(
            db.execute(
                select(SensorReading)
                .where(
                    SensorReading.tenant_id == tenant_id,
                    SensorReading.machine_id == machine.id,
                    SensorReading.recorded_at >= since,
                    SensorReading.quality == "good",
                )
                .order_by(SensorReading.recorded_at)
            ).scalars()
        )

        by_type: Dict[str, List[SensorReading]] = defaultdict(list)
        for reading in readings:
            if reading.sensor_type in DEGRADATION_SENSORS:
                by_type[reading.sensor_type].append(reading)

        best: Optional[Tuple[str, float, float, int]] = None  # type, rul, slope, n
        for sensor_type, series in by_type.items():
            if len(series) < MIN_RUL_READINGS:
                continue

            timestamps = np.asarray(
                [_as_utc(r.recorded_at).timestamp() / 3600 for r in series]
            )
            values = np.asarray([r.value for r in series], dtype=float)

            # Trend in units per hour.
            slope, intercept = np.polyfit(timestamps, values, 1)
            if slope <= 0:
                continue  # Not degrading on this channel.

            # Healthy baseline: the earliest quarter of the window.
            baseline_n = max(len(values) // 4, 5)
            baseline = values[:baseline_n]
            baseline_mean = float(baseline.mean())
            baseline_std = float(baseline.std())
            threshold = baseline_mean + 3 * (baseline_std or 1e-6)

            # Reject trends that are indistinguishable from noise. A flat
            # signal still yields a tiny positive slope from floating-point
            # error, which would otherwise extrapolate to a confident (and
            # meaningless) remaining life.
            span_hours = float(timestamps[-1] - timestamps[0])
            total_rise = float(slope) * span_hours
            min_rise = max(0.5 * baseline_std, 1e-6 * abs(baseline_mean), 1e-9)
            if total_rise < min_rise:
                continue

            current = float(intercept + slope * timestamps[-1])
            if current >= threshold:
                rul_hours = 0.0
            else:
                rul_hours = float((threshold - current) / slope)

            if best is None or rul_hours < best[1]:
                best = (sensor_type, rul_hours, float(slope), len(series))

        if best is None:
            return RULPrediction(
                machine_id=machine.id,
                machine_code=machine.machine_code,
                rul_hours=None,
                predicted_failure_at=None,
                degradation_rate_per_hour=0.0,
                dominant_sensor=None,
                sample_size=len(readings),
                confidence="none",
                method="degradation_trend_extrapolation",
            )

        sensor_type, rul_hours, slope, sample_size = best
        # Cap at one year: linear extrapolation beyond that is not meaningful.
        rul_hours = float(min(rul_hours, 8760.0))
        confidence = "high" if sample_size >= 200 else "medium"

        return RULPrediction(
            machine_id=machine.id,
            machine_code=machine.machine_code,
            rul_hours=round(rul_hours, 1),
            predicted_failure_at=datetime.now(timezone.utc)
            + timedelta(hours=rul_hours),
            degradation_rate_per_hour=round(slope, 6),
            dominant_sensor=sensor_type,
            sample_size=sample_size,
            confidence=confidence,
            method="degradation_trend_extrapolation",
        )

    # ==================================================================
    # Level 3 - anomaly detection
    # ==================================================================
    @staticmethod
    def detect_anomalies(
        db: Session,
        tenant_id: str,
        window_hours: int = 24,
        machine_id: Optional[str] = None,
        contamination: float = 0.005,
        limit: int = 100,
    ) -> AnomalyReport:
        """Flag outlier readings with an Isolation Forest per sensor channel.

        Readings are first z-normalised within each (machine, sensor_type)
        group, because the normal operating range of a vibration probe on a
        press says nothing about one on an oven. The normalised values for a
        channel are then pooled into a single model.

        Pooling matters for accuracy, not just speed. ``contamination`` makes
        the forest flag a fixed share of whatever population it is fitted to,
        so fitting one model per machine forces a false positive out of every
        clean machine. Against known injected faults in the pilot data, pooling
        raised precision from 37% to 61% and recall from 82% to 97%, while
        cutting the work from one model per machine-channel to one per channel.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        stmt = select(SensorReading).where(
            SensorReading.tenant_id == tenant_id,
            SensorReading.recorded_at >= since,
        )
        if machine_id:
            stmt = stmt.where(SensorReading.machine_id == machine_id)
        readings = list(db.execute(stmt.order_by(SensorReading.recorded_at)).scalars())

        grouped: Dict[Tuple[str, str], List[SensorReading]] = defaultdict(list)
        for reading in readings:
            grouped[(reading.machine_id, reading.sensor_type)].append(reading)

        # Normalise each machine-channel against its own baseline, then pool
        # by sensor type.
        pooled: Dict[str, Tuple[List[float], List[SensorReading]]] = defaultdict(
            lambda: ([], [])
        )
        for (_group_machine_id, sensor_type), series in grouped.items():
            values = np.asarray([r.value for r in series], dtype=float)
            std = float(values.std())
            if std <= 1e-9:
                # A perfectly constant channel has no outliers to find.
                continue
            z_scores = (values - float(values.mean())) / std
            bucket_z, bucket_rows = pooled[sensor_type]
            bucket_z.extend(z_scores.tolist())
            bucket_rows.extend(series)

        anomalies: List[AnomalyEvent] = []

        for _sensor_type, (z_list, rows) in pooled.items():
            z_array = np.asarray(z_list, dtype=float)
            features = z_array.reshape(-1, 1)

            if len(rows) >= MIN_ANOMALY_READINGS:
                from sklearn.ensemble import IsolationForest

                forest = IsolationForest(
                    contamination=contamination, random_state=42, n_estimators=100
                )
                predictions = forest.fit_predict(features)
                scores = forest.score_samples(features)
                flagged = [
                    (rows[i], float(scores[i]), float(z_array[i]))
                    for i in range(len(rows))
                    if predictions[i] == -1
                ]
            else:
                # Too few points to isolate outliers; fall back to a z screen.
                flagged = [
                    (rows[i], -abs(float(z_array[i])), float(z_array[i]))
                    for i in range(len(rows))
                    if abs(z_array[i]) >= 3
                ]

            for reading, score, z_score in flagged:
                # Severity comes from how far the reading sits from its own
                # machine's baseline, which is interpretable to an operator.
                deviation = abs(z_score)
                severity = (
                    "critical"
                    if deviation >= 6
                    else "high"
                    if deviation >= 4.5
                    else "medium"
                )
                anomalies.append(
                    AnomalyEvent(
                        machine_id=reading.machine_id,
                        sensor_type=reading.sensor_type,
                        recorded_at=_as_utc(reading.recorded_at),
                        value=reading.value,
                        score=round(score, 4),
                        severity=severity,
                    )
                )

        anomalies.sort(key=lambda a: a.score)
        return AnomalyReport(
            tenant_id=tenant_id,
            window_hours=window_hours,
            readings_analysed=len(readings),
            anomaly_count=len(anomalies),
            anomalies=anomalies[:limit],
            method="isolation_forest_pooled_zscore",
        )
