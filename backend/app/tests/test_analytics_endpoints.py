"""Maturity-aware analytics endpoints and their gating."""

import pytest


@pytest.mark.parametrize(
    "endpoint,required_level",
    [
        ("/api/v1/analytics/risk", 2),
        ("/api/v1/analytics/roi", 2),
        ("/api/v1/analytics/anomalies", 3),
        ("/api/v1/analytics/rul", 3),
        ("/api/v1/analytics/benchmark", 4),
    ],
)
def test_locked_endpoints_403_for_level_one(
    client, level_one_tenant, endpoint, required_level
):
    response = client.get(endpoint, headers={"X-Tenant-ID": level_one_tenant.slug})

    assert response.status_code == 403
    assert response.json()["detail"]["required_level"] == required_level


def test_weibull_available_at_level_one(client, level_one_tenant):
    response = client.get(
        "/api/v1/analytics/reliability/weibull",
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    assert response.status_code == 200
    assert response.json()["sample_size"] > 0


def test_risk_endpoint_at_level_two(client, level_two_tenant):
    response = client.get(
        "/api/v1/analytics/risk", headers={"X-Tenant-ID": level_two_tenant.slug}
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 3
    assert body[0]["risk_band"] in {"low", "medium", "high", "critical"}


def test_cascade_endpoint_at_level_two(client, level_two_tenant):
    response = client.get(
        "/api/v1/analytics/cascade/L2-M002?downtime_hours=6",
        headers={"X-Tenant-ID": level_two_tenant.slug},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["downtime_hours"] == 6
    assert len(body["affected_machines"]) == 3


def test_simulator_endpoint(client, level_two_tenant):
    response = client.post(
        "/api/v1/analytics/simulate?machine_id=L2-M001&downtime_hours=12",
        headers={"X-Tenant-ID": level_two_tenant.slug},
    )
    assert response.status_code == 200
    assert response.json()["total_cost"] > 0


def test_simulator_rejects_non_positive_downtime(client, level_two_tenant):
    response = client.post(
        "/api/v1/analytics/simulate?machine_id=L2-M001&downtime_hours=0",
        headers={"X-Tenant-ID": level_two_tenant.slug},
    )
    assert response.status_code == 422


def test_rul_and_anomalies_at_level_three(client, level_three_tenant):
    headers = {"X-Tenant-ID": level_three_tenant.slug}

    rul = client.get("/api/v1/analytics/rul", headers=headers)
    anomalies = client.get("/api/v1/analytics/anomalies?window_hours=72", headers=headers)

    assert rul.status_code == 200
    assert len(rul.json()) == 3
    assert anomalies.status_code == 200
    assert anomalies.json()["readings_analysed"] > 0


# ----------------------------------------------------------------------
# Dashboard shape by level
# ----------------------------------------------------------------------
def test_dashboard_level_one_hides_higher_sections(client, level_one_tenant):
    body = client.get(
        "/api/v1/analytics/dashboard", headers={"X-Tenant-ID": level_one_tenant.slug}
    ).json()

    assert body["maturity_level"] == 1
    assert body["maintenance_summary"] is not None
    assert body["top_risks"] is None
    assert body["line_summary"] is None
    assert body["rul_watchlist"] is None
    assert body["site_benchmark"] is None


def test_dashboard_level_two_adds_risk_and_lines(client, level_two_tenant):
    body = client.get(
        "/api/v1/analytics/dashboard", headers={"X-Tenant-ID": level_two_tenant.slug}
    ).json()

    assert body["maturity_level"] == 2
    assert body["top_risks"]
    assert body["line_summary"]
    assert body["active_anomalies"] is None


def test_dashboard_level_three_adds_realtime(client, level_three_tenant):
    body = client.get(
        "/api/v1/analytics/dashboard", headers={"X-Tenant-ID": level_three_tenant.slug}
    ).json()

    assert body["maturity_level"] == 3
    assert body["active_anomalies"] is not None
    assert body["rul_watchlist"] is not None
    assert "rul_prediction" in body["enabled_features"]


def test_dashboard_for_empty_tenant_is_still_served(client, make_tenant):
    make_tenant(slug="blank", name="Blank Co")
    response = client.get(
        "/api/v1/analytics/dashboard", headers={"X-Tenant-ID": "blank"}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["maturity_level"] == 0
    assert body["machine_count"] == 0
    assert body["maintenance_summary"] is None


def test_override_unlocks_endpoint_end_to_end(client, level_one_tenant):
    """Granting a feature manually must make the gated endpoint work."""
    headers = {"X-Tenant-ID": level_one_tenant.slug}
    assert client.get("/api/v1/analytics/roi", headers=headers).status_code == 403

    client.put(
        f"/api/v1/tenants/{level_one_tenant.slug}/features/roi_analysis",
        json={"enabled": True},
    )

    assert client.get("/api/v1/analytics/roi", headers=headers).status_code == 200
