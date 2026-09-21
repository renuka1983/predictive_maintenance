"""ML and analytics service behaviour."""

import math
from datetime import timedelta

from app.services import AnalyticsService, MLService


# ----------------------------------------------------------------------
# Weibull
# ----------------------------------------------------------------------
def test_weibull_with_no_history_is_empty(db_session, make_tenant, make_machine):
    tenant = make_tenant(slug="fresh")
    make_machine(tenant, code="F-1")

    fit = MLService.weibull_fit(db_session, tenant.id)

    assert fit.sample_size == 0
    assert fit.confidence == "none"
    assert fit.failure_probability_30d == 0.0


def test_weibull_recovers_regular_interval(db_session, level_one_tenant):
    """Failures every 12 days should give a scale close to 288 hours."""
    fit = MLService.weibull_fit(db_session, level_one_tenant.id)

    assert fit.sample_size > 0
    assert 200 < fit.scale_hours < 400
    assert 0 <= fit.failure_probability_30d <= 1
    assert fit.interpretation


def test_weibull_shape_flags_wear_out(db_session, level_one_tenant):
    """Evenly spaced failures are a wear-out pattern (shape well above 1)."""
    fit = MLService.weibull_fit(db_session, level_one_tenant.id)

    assert fit.shape > 1.5
    assert "wear-out" in fit.interpretation.lower()


def test_weibull_scoped_to_one_machine(db_session, level_one_tenant):
    from app.models import Machine
    from sqlalchemy import select

    machine = db_session.execute(
        select(Machine).where(Machine.tenant_id == level_one_tenant.id)
    ).scalars().first()

    fleet = MLService.weibull_fit(db_session, level_one_tenant.id)
    single = MLService.weibull_fit(db_session, level_one_tenant.id, machine.id)

    assert single.sample_size < fleet.sample_size
    assert single.machine_id == machine.id


# ----------------------------------------------------------------------
# Risk scoring
# ----------------------------------------------------------------------
def test_risk_scores_returned_for_every_machine(db_session, level_two_tenant):
    scores = MLService.risk_scores(db_session, level_two_tenant.id)

    assert len(scores) == 3
    assert all(0 <= s.risk_score <= 1 for s in scores)
    assert all(s.drivers for s in scores)
    assert scores == sorted(scores, key=lambda s: s.risk_score, reverse=True)


def test_risk_falls_back_to_heuristic_without_training_data(
    db_session, make_tenant, make_machine
):
    tenant = make_tenant(slug="sparse")
    make_machine(tenant, code="SP-1")

    scores = MLService.risk_scores(db_session, tenant.id)

    assert len(scores) == 1
    assert scores[0].model_used == "heuristic_risk_index"
    assert scores[0].confidence == "low"


def test_risk_band_thresholds():
    assert MLService._heuristic_risk([999, 5, 6, 60, 9000, 5, 0.4, 0.4, 500])[0] > 0.7


def test_risk_limit_applies(db_session, level_two_tenant):
    assert len(MLService.risk_scores(db_session, level_two_tenant.id, limit=2)) == 2


# ----------------------------------------------------------------------
# Cascade impact
# ----------------------------------------------------------------------
def test_cascade_includes_whole_line(db_session, level_two_tenant, make_machine):
    from app.models import Machine
    from sqlalchemy import select

    machine = db_session.execute(
        select(Machine).where(
            Machine.tenant_id == level_two_tenant.id, Machine.line_position == 2
        )
    ).scalars().one()

    impact = MLService.cascade_impact(db_session, level_two_tenant.id, machine, 4.0)

    assert impact.direct_lost_units == machine.hourly_output_units * 4.0
    assert len(impact.affected_machines) == 3
    types = {n.impact_type for n in impact.affected_machines}
    assert {"source", "upstream_blocked", "downstream_starved"} == types
    assert impact.total_cost > machine.hourly_downtime_cost * 4.0


def test_cascade_scales_with_downtime(db_session, level_two_tenant):
    from app.models import Machine
    from sqlalchemy import select

    machine = db_session.execute(
        select(Machine).where(Machine.tenant_id == level_two_tenant.id)
    ).scalars().first()

    short = MLService.cascade_impact(db_session, level_two_tenant.id, machine, 2.0)
    long = MLService.cascade_impact(db_session, level_two_tenant.id, machine, 8.0)

    assert math.isclose(long.total_cost, short.total_cost * 4, rel_tol=1e-6)


def test_cascade_on_standalone_machine_has_no_neighbours(
    db_session, make_tenant, make_machine
):
    tenant = make_tenant(slug="solo")
    machine = make_machine(
        tenant, code="SL-1", production_line=None, hourly_output_units=50.0
    )

    impact = MLService.cascade_impact(db_session, tenant.id, machine, 3.0)

    assert impact.cascade_lost_units == 0.0
    assert len(impact.affected_machines) == 1


# ----------------------------------------------------------------------
# RUL
# ----------------------------------------------------------------------
def test_rul_detects_upward_trend(db_session, level_three_tenant):
    from app.models import Machine
    from sqlalchemy import select

    machine = db_session.execute(
        select(Machine).where(Machine.tenant_id == level_three_tenant.id)
    ).scalars().first()

    prediction = MLService.predict_rul(db_session, level_three_tenant.id, machine)

    assert prediction.rul_hours is not None
    assert prediction.rul_hours >= 0
    assert prediction.dominant_sensor == "vibration"
    assert prediction.degradation_rate_per_hour > 0
    assert prediction.predicted_failure_at is not None


def test_rul_is_none_without_sensor_data(db_session, make_tenant, make_machine):
    tenant = make_tenant(slug="blind")
    machine = make_machine(tenant, code="BL-1", has_sensors=True)

    prediction = MLService.predict_rul(db_session, tenant.id, machine)

    assert prediction.rul_hours is None
    assert prediction.confidence == "none"


def test_rul_ignores_flat_signal(
    db_session, make_tenant, make_machine, seed_sensors
):
    """A stable machine has no degradation trend, so no RUL is reported."""
    tenant = make_tenant(slug="stable")
    machine = make_machine(tenant, code="ST-1", has_sensors=True)
    seed_sensors(tenant, machine, count=400, drift=0.0)

    prediction = MLService.predict_rul(db_session, tenant.id, machine)

    assert prediction.rul_hours is None


# ----------------------------------------------------------------------
# Anomalies
# ----------------------------------------------------------------------
def test_anomaly_detection_flags_injected_spike(
    db_session, make_tenant, make_machine, seed_sensors, now
):
    from app.models import SensorReading

    tenant = make_tenant(slug="spiky")
    machine = make_machine(tenant, code="SK-1", has_sensors=True)
    seed_sensors(tenant, machine, count=200, drift=0.0)

    db_session.add(
        SensorReading(
            tenant_id=tenant.id,
            machine_id=machine.id,
            sensor_type="vibration",
            value=95.0,  # Far outside the normal band.
            unit="mm/s",
            quality="good",
            recorded_at=now - timedelta(minutes=1),
        )
    )
    db_session.commit()

    report = MLService.detect_anomalies(db_session, tenant.id, window_hours=72)
    values = [a.value for a in report.anomalies]

    assert report.anomaly_count >= 1
    assert 95.0 in values


def test_anomaly_detection_quiet_on_clean_data(
    db_session, make_tenant, make_machine, seed_sensors
):
    tenant = make_tenant(slug="calm")
    machine = make_machine(tenant, code="CM-1", has_sensors=True)
    seed_sensors(tenant, machine, count=200, drift=0.0)

    report = MLService.detect_anomalies(
        db_session, tenant.id, window_hours=72, contamination=0.005
    )

    # A constant-slope synthetic trace has no true outliers; the forest may
    # still flag its contamination quota, so just assert it stays small.
    assert report.anomaly_count <= 0.02 * report.readings_analysed


# ----------------------------------------------------------------------
# Analytics service
# ----------------------------------------------------------------------
def test_roi_estimate(db_session, level_two_tenant):
    roi = AnalyticsService.roi_estimate(db_session, level_two_tenant.id)

    assert roi.reactive_cost > 0
    assert 0 < roi.preventable_cost < roi.reactive_cost
    assert roi.estimated_annual_savings > 0
    assert roi.assumptions


def test_site_benchmark_ranks_sites(
    db_session, make_tenant, make_machine, seed_maintenance, seed_production
):
    tenant = make_tenant(slug="multi")
    for site in ("Plant A", "Plant B"):
        machine = make_machine(tenant, code=f"{site[-1]}-1", site=site)
        seed_maintenance(tenant, machine, count=10)
        seed_production(tenant, machine, count=20)

    rows = AnalyticsService.site_benchmark(db_session, tenant.id)

    assert len(rows) == 2
    assert [row["rank"] for row in rows] == [1, 2]
    assert rows[0]["avg_oee"] >= rows[1]["avg_oee"]


def test_machine_status_penalises_down_machines(
    db_session, make_tenant, make_machine, seed_maintenance
):
    tenant = make_tenant(slug="health")
    healthy = make_machine(tenant, code="H-1", status="operational")
    broken = make_machine(tenant, code="H-2", status="down")
    seed_maintenance(tenant, healthy, count=2)
    seed_maintenance(tenant, broken, count=2)

    healthy_status = AnalyticsService.machine_status(db_session, tenant.id, healthy)
    broken_status = AnalyticsService.machine_status(db_session, tenant.id, broken)

    assert broken_status.health_score < healthy_status.health_score


def test_maintenance_stats_window_filters_old_records(
    db_session, make_tenant, make_machine, seed_maintenance
):
    tenant = make_tenant(slug="windowed")
    machine = make_machine(tenant, code="W-1")
    seed_maintenance(tenant, machine, count=20, spacing_days=30)

    wide = AnalyticsService.maintenance_stats(db_session, tenant.id, window_days=1000)
    narrow = AnalyticsService.maintenance_stats(db_session, tenant.id, window_days=100)

    assert narrow.total_records < wide.total_records
