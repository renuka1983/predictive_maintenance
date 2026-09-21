"""Level 4 enterprise features: site registry, rollup, benchmark, fleet."""

import pytest

from app.services import EnterpriseService, MaturityService


# ----------------------------------------------------------------------
# Level promotion
# ----------------------------------------------------------------------
def test_multi_site_tenant_reaches_level_four(level_four_tenant):
    assert level_four_tenant.maturity_level == 4


def test_single_site_tenant_stays_at_level_three(level_three_tenant):
    """Level 4 is about estate breadth, not more of the same data."""
    assert level_three_tenant.maturity_level == 3


def test_level_four_is_the_top(db_session, level_four_tenant):
    assessment = MaturityService.assess(db_session, level_four_tenant)
    assert assessment.upgrade_path.next_level is None
    assert assessment.upgrade_path.requirements == []


# ----------------------------------------------------------------------
# Site registry
# ----------------------------------------------------------------------
def test_site_registry_lists_machine_counts(client, level_four_tenant):
    response = client.get("/api/v1/sites", headers={"X-Tenant-ID": "l4-tenant"})
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 3
    assert all(site["machine_count"] == 2 for site in body)


def test_site_registry_is_gated_below_level_four(client, level_three_tenant):
    response = client.get(
        "/api/v1/sites", headers={"X-Tenant-ID": level_three_tenant.slug}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["required_level"] == 4


def test_create_and_update_site(client, level_four_tenant):
    headers = {"X-Tenant-ID": "l4-tenant"}
    created = client.post(
        "/api/v1/sites",
        json={"name": "Osaka", "region": "APAC", "country": "Japan"},
        headers=headers,
    )
    assert created.status_code == 201

    updated = client.patch(
        "/api/v1/sites/Osaka", json={"region": "Asia Pacific"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["region"] == "Asia Pacific"


def test_duplicate_site_conflicts(client, level_four_tenant):
    headers = {"X-Tenant-ID": "l4-tenant"}
    response = client.post("/api/v1/sites", json={"name": "Detroit"}, headers=headers)
    assert response.status_code == 409


def test_unregistered_sites_are_reported(
    client, level_four_tenant, make_machine
):
    make_machine(level_four_tenant, code="NEW-001", site="Gdansk")

    response = client.get(
        "/api/v1/sites/unregistered", headers={"X-Tenant-ID": "l4-tenant"}
    )
    assert response.json() == ["Gdansk"]


def test_sync_registers_every_used_site(client, level_four_tenant, make_machine):
    make_machine(level_four_tenant, code="NEW-001", site="Gdansk")
    headers = {"X-Tenant-ID": "l4-tenant"}

    synced = client.post("/api/v1/sites/sync", headers=headers)

    assert synced.status_code == 200
    assert "Gdansk" in {site["name"] for site in synced.json()}
    assert client.get("/api/v1/sites/unregistered", headers=headers).json() == []


def test_regions_endpoint(client, level_four_tenant):
    response = client.get(
        "/api/v1/sites/regions", headers={"X-Tenant-ID": "l4-tenant"}
    )
    assert response.json() == ["Europe", "North America"]


def test_deleting_a_site_leaves_machines_intact(client, level_four_tenant):
    headers = {"X-Tenant-ID": "l4-tenant"}
    assert client.delete("/api/v1/sites/Brno", headers=headers).status_code == 200

    machines = client.get(
        "/api/v1/machines?site=Brno&limit=100", headers=headers
    ).json()
    assert machines["total"] == 2

    # The site still groups machines in rollups; it has just lost its region.
    rollup = client.get("/api/v1/analytics/portfolio", headers=headers).json()
    brno = next(g for g in rollup["groups"] if g["name"] == "Brno")
    assert brno["region"] is None
    assert brno["is_registered"] is False


def test_sites_are_tenant_scoped(client, level_four_tenant, make_tenant, make_site):
    other = make_tenant(slug="other-group", name="Other Group")
    make_site(other, "Secret Plant", region="Nowhere")

    response = client.get("/api/v1/sites", headers={"X-Tenant-ID": "l4-tenant"})
    assert "Secret Plant" not in {site["name"] for site in response.json()}


# ----------------------------------------------------------------------
# Portfolio rollup
# ----------------------------------------------------------------------
def test_portfolio_rollup_by_site(client, level_four_tenant):
    response = client.get(
        "/api/v1/analytics/portfolio", headers={"X-Tenant-ID": "l4-tenant"}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["group_count"] == 3
    assert body["totals"]["machine_count"] == 6
    assert {g["name"] for g in body["groups"]} == {"Detroit", "Monterrey", "Brno"}


def test_portfolio_rollup_by_region(client, level_four_tenant):
    body = client.get(
        "/api/v1/analytics/portfolio?group_by=region",
        headers={"X-Tenant-ID": "l4-tenant"},
    ).json()

    assert body["group_count"] == 2
    north_america = next(g for g in body["groups"] if g["name"] == "North America")
    # Detroit and Monterrey, two machines each.
    assert north_america["machine_count"] == 4


def test_portfolio_totals_come_from_raw_counts(client, level_four_tenant):
    """Totals must not be a mean of per-site means."""
    body = client.get(
        "/api/v1/analytics/portfolio", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()

    totals = body["totals"]
    assert totals["maintenance_events"] == sum(
        g["maintenance_events"] for g in body["groups"]
    )
    assert totals["downtime_hours"] == pytest.approx(
        sum(g["downtime_hours"] for g in body["groups"]), rel=1e-6
    )
    assert totals["cost_per_machine"] == pytest.approx(
        totals["maintenance_cost"] / totals["machine_count"], rel=1e-6
    )


def test_weighted_oee_accounts_for_plant_size(
    db_session, make_tenant, make_site, make_machine, seed_production, seed_maintenance
):
    """A four-machine plant must count more than a one-machine plant."""
    tenant = make_tenant(slug="weighted")
    make_site(tenant, "Big", region="R1")
    make_site(tenant, "Small", region="R1")

    for index in range(4):
        machine = make_machine(tenant, code=f"BIG-{index}", site="Big")
        seed_production(tenant, machine, count=20, produced=900)
        seed_maintenance(tenant, machine, count=4)
    small = make_machine(tenant, code="SML-0", site="Small")
    seed_production(tenant, small, count=20, produced=200)
    seed_maintenance(tenant, small, count=4)

    rollup = EnterpriseService.portfolio_rollup(db_session, tenant.id)
    groups = {g["name"]: g for g in rollup["groups"]}
    weighted = rollup["totals"]["weighted_avg_oee"]
    naive = (groups["Big"]["avg_oee"] + groups["Small"]["avg_oee"]) / 2

    # Weighted must sit closer to the four-machine plant than a plain mean.
    assert weighted > naive
    assert abs(weighted - groups["Big"]["avg_oee"]) < abs(
        naive - groups["Big"]["avg_oee"]
    )


def test_portfolio_rejects_bad_group_by(client, level_four_tenant):
    response = client.get(
        "/api/v1/analytics/portfolio?group_by=continent",
        headers={"X-Tenant-ID": "l4-tenant"},
    )
    assert response.status_code == 422


def test_machines_without_a_site_group_as_unassigned(
    db_session, level_four_tenant, make_machine
):
    make_machine(level_four_tenant, code="ORPHAN-1", site=None)

    rollup = EnterpriseService.portfolio_rollup(db_session, level_four_tenant.id)
    assert "unassigned" in {g["name"] for g in rollup["groups"]}


# ----------------------------------------------------------------------
# Benchmarking
# ----------------------------------------------------------------------
def test_benchmark_ranks_best_site_first(client, level_four_tenant):
    body = client.get(
        "/api/v1/analytics/benchmark", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()

    assert body["site_count"] == 3
    assert body["sites"][0]["site"] == "Detroit"
    assert body["sites"][0]["rank"] == 1
    assert body["sites"][-1]["site"] == "Brno"


def test_percentile_rank_is_direction_normalised():
    """1.0 must mean best for both maximise and minimise metrics."""
    population = [0.2, 0.5, 0.9]

    # Higher is better: the largest value wins.
    assert EnterpriseService._percentile_rank(0.9, population, True) == 1.0
    assert EnterpriseService._percentile_rank(0.2, population, True) == 0.0
    # Lower is better: the smallest value wins.
    assert EnterpriseService._percentile_rank(0.2, population, False) == 1.0
    assert EnterpriseService._percentile_rank(0.9, population, False) == 0.0


def test_percentile_rank_with_single_site():
    assert EnterpriseService._percentile_rank(5.0, [5.0], True) == 1.0


def test_benchmark_percentiles_favour_the_best_site(client, level_four_tenant):
    body = client.get(
        "/api/v1/analytics/benchmark", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()
    sites = {s["site"]: s for s in body["sites"]}

    # Detroit has the lowest cost and the highest OEE, so it must top both
    # despite the metrics pointing in opposite directions.
    assert sites["Detroit"]["percentiles"]["maintenance_cost_per_machine"] == 1.0
    assert sites["Detroit"]["percentiles"]["avg_oee"] == 1.0
    assert sites["Brno"]["percentiles"]["maintenance_cost_per_machine"] == 0.0


def test_metric_leaders_identify_best_and_worst(client, level_four_tenant):
    body = client.get(
        "/api/v1/analytics/benchmark", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()
    leaders = body["metric_leaders"]

    assert leaders["avg_oee"]["best_site"] == "Detroit"
    assert leaders["avg_oee"]["higher_is_better"] is True
    assert leaders["maintenance_cost_per_machine"]["best_site"] == "Detroit"
    assert leaders["maintenance_cost_per_machine"]["higher_is_better"] is False
    assert leaders["maintenance_cost_per_machine"]["worst_site"] == "Brno"


def test_opportunity_prices_the_gap(client, level_four_tenant):
    body = client.get(
        "/api/v1/analytics/benchmark", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()
    opportunity = body["opportunity"]

    assert opportunity["benchmark_site"] == "Detroit"
    assert opportunity["annualised_saving"] > 0
    # The benchmark site sets the target, so it is never its own offender.
    assert "Detroit" not in {o["site"] for o in opportunity["worst_offenders"]}
    assert opportunity["worst_offenders"][0]["site"] == "Brno"


def test_opportunity_is_none_for_a_single_site(
    db_session, make_tenant, make_site, make_machine, seed_maintenance
):
    """There is no gap to close when there is nothing to compare against."""
    tenant = make_tenant(slug="one-plant")
    make_site(tenant, "Only", region="R")
    machine = make_machine(tenant, code="ON-1", site="Only")
    seed_maintenance(tenant, machine, count=5)

    benchmark = EnterpriseService.benchmark_sites(db_session, tenant.id)
    assert benchmark["site_count"] == 1
    assert benchmark["opportunity"] is None


def test_benchmark_handles_a_tenant_with_no_machines(db_session, make_tenant):
    tenant = make_tenant(slug="empty-group")
    benchmark = EnterpriseService.benchmark_sites(db_session, tenant.id)

    assert benchmark["site_count"] == 0
    assert benchmark["sites"] == []
    assert benchmark["opportunity"] is None


# ----------------------------------------------------------------------
# Fleet comparison
# ----------------------------------------------------------------------
def test_fleet_comparison_covers_every_type_and_site(client, level_four_tenant):
    rows = client.get(
        "/api/v1/analytics/fleet", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()

    # Two asset classes across three sites.
    assert len(rows) == 6
    assert {r["machine_type"] for r in rows} == {"CNC Mill", "Conveyor"}


def test_fleet_comparison_marks_best_and_worst_per_class(client, level_four_tenant):
    rows = client.get(
        "/api/v1/analytics/fleet", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()

    for machine_type in ("CNC Mill", "Conveyor"):
        group = [r for r in rows if r["machine_type"] == machine_type]
        assert sum(1 for r in group if r["is_best_in_class"]) == 1
        assert sum(1 for r in group if r["is_worst_in_class"]) == 1

        best = next(r for r in group if r["is_best_in_class"])
        assert best["cost_vs_best"] == 0.0
        assert best["cost_ratio_vs_best"] == 1.0


def test_fleet_comparison_filters_by_machine_type(client, level_four_tenant):
    rows = client.get(
        "/api/v1/analytics/fleet?machine_type=CNC%20Mill",
        headers={"X-Tenant-ID": "l4-tenant"},
    ).json()

    assert len(rows) == 3
    assert {r["machine_type"] for r in rows} == {"CNC Mill"}


def test_fleet_comparison_unknown_type_is_empty(client, level_four_tenant):
    rows = client.get(
        "/api/v1/analytics/fleet?machine_type=Loom",
        headers={"X-Tenant-ID": "l4-tenant"},
    ).json()
    assert rows == []


def test_single_site_class_is_neither_best_nor_worst(
    db_session, make_tenant, make_site, make_machine, seed_maintenance
):
    """With one site there is no comparison, so no flag should be set."""
    tenant = make_tenant(slug="solo-fleet")
    make_site(tenant, "Only")
    machine = make_machine(
        tenant, code="ON-1", site="Only", machine_type="Press"
    )
    seed_maintenance(tenant, machine, count=5)

    rows = EnterpriseService.fleet_comparison(db_session, tenant.id)
    assert len(rows) == 1
    assert rows[0]["is_best_in_class"] is False
    assert rows[0]["is_worst_in_class"] is False


# ----------------------------------------------------------------------
# Gating and dashboard
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/analytics/portfolio",
        "/api/v1/analytics/benchmark",
        "/api/v1/analytics/fleet",
        "/api/v1/sites",
        "/api/v1/sites/regions",
    ],
)
def test_enterprise_endpoints_are_gated(client, level_three_tenant, endpoint):
    response = client.get(
        endpoint, headers={"X-Tenant-ID": level_three_tenant.slug}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["required_level"] == 4


def test_dashboard_adds_enterprise_sections_at_level_four(client, level_four_tenant):
    body = client.get(
        "/api/v1/analytics/dashboard", headers={"X-Tenant-ID": "l4-tenant"}
    ).json()

    assert body["maturity_level"] == 4
    assert body["site_benchmark"]
    assert body["benchmark_opportunity"]["annualised_saving"] > 0
    assert body["portfolio_totals"]["machine_count"] == 6


def test_dashboard_omits_enterprise_sections_below_level_four(
    client, level_three_tenant
):
    body = client.get(
        "/api/v1/analytics/dashboard",
        headers={"X-Tenant-ID": level_three_tenant.slug},
    ).json()

    assert body["site_benchmark"] is None
    assert body["benchmark_opportunity"] is None
    assert body["portfolio_totals"] is None


def test_enterprise_analytics_are_tenant_scoped(
    db_session, level_four_tenant, make_tenant, make_site, make_machine, seed_maintenance
):
    """Another group's plants must not appear in this tenant's rollup."""
    baseline = EnterpriseService.portfolio_rollup(db_session, level_four_tenant.id)

    other = make_tenant(slug="rival-group")
    make_site(other, "Rival Plant", region="Europe")
    rival = make_machine(other, code="RV-1", site="Rival Plant")
    seed_maintenance(other, rival, count=40, downtime_hours=30)

    after = EnterpriseService.portfolio_rollup(db_session, level_four_tenant.id)

    assert after["group_count"] == baseline["group_count"]
    assert "Rival Plant" not in {g["name"] for g in after["groups"]}
    assert after["totals"]["maintenance_cost"] == baseline["totals"]["maintenance_cost"]
