"""Maturity assessment and level progression."""

from app.services import FeatureGate, MaturityService


def test_empty_tenant_is_level_zero(db_session, make_tenant):
    tenant = make_tenant(slug="empty")
    assessment = MaturityService.assess(db_session, tenant)

    assert assessment.level == 0
    assert assessment.score == 0.0
    assert assessment.upgrade_path.next_level == 1
    assert assessment.upgrade_path.requirements


def test_cmms_data_reaches_level_one(level_one_tenant):
    assert level_one_tenant.maturity_level == 1
    assert level_one_tenant.maturity_score > 0


def test_production_data_reaches_level_two(level_two_tenant):
    assert level_two_tenant.maturity_level == 2


def test_sensor_data_reaches_level_three(level_three_tenant):
    assert level_three_tenant.maturity_level == 3


def test_sensor_data_alone_cannot_skip_to_level_three(
    db_session, make_tenant, make_machine, seed_sensors
):
    """Telemetry without maintenance or production history must not skip levels."""
    tenant = make_tenant(slug="sensors-only")
    machine = make_machine(tenant, code="SO-001", has_sensors=True)
    seed_sensors(tenant, machine, count=1000)

    assessment = MaturityService.assess(db_session, tenant)
    assert assessment.level == 0


def test_assessment_has_four_dimensions_and_bounded_score(level_three_tenant, db_session):
    assessment = MaturityService.assess(db_session, level_three_tenant)

    names = {d.name for d in assessment.dimensions}
    assert names == {"cmms", "production", "iot_sensors", "data_quality"}
    assert all(0 <= d.score <= 25 for d in assessment.dimensions)
    assert 0 <= assessment.score <= 100
    assert abs(sum(d.score for d in assessment.dimensions) - assessment.score) < 0.01


def test_upgrade_path_points_at_next_level(level_one_tenant, db_session):
    assessment = MaturityService.assess(db_session, level_one_tenant)

    assert assessment.upgrade_path.current_level == 1
    assert assessment.upgrade_path.next_level == 2
    assert assessment.upgrade_path.unlocks


def test_multi_site_reaches_level_four(
    db_session, make_tenant, make_machine, seed_maintenance, seed_production, seed_sensors
):
    tenant = make_tenant(slug="enterprise")
    for index, site in enumerate(["Plant A", "Plant B"], start=1):
        for offset in range(2):
            machine = make_machine(
                tenant,
                code=f"EN-{index}{offset}",
                site=site,
                line_position=offset + 1,
                has_sensors=True,
            )
            seed_maintenance(tenant, machine, count=20, spacing_days=12)
            seed_production(tenant, machine, count=40)
            seed_sensors(tenant, machine, count=400)

    assessment = MaturityService.assess(db_session, tenant)
    assert assessment.level == 4
    assert assessment.upgrade_path.next_level is None


def test_toggles_sync_after_assessment(db_session, level_two_tenant):
    toggles = FeatureGate.sync_toggles(db_session, level_two_tenant)
    enabled = {t.feature_key for t in toggles if t.is_enabled}

    assert "maintenance_stats" in enabled
    assert "cascade_impact_analysis" in enabled
    assert "rul_prediction" not in enabled
