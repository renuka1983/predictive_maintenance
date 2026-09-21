"""API endpoint behaviour: CRUD, validation and status codes."""

from datetime import timedelta


# ----------------------------------------------------------------------
# System
# ----------------------------------------------------------------------
def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_root_endpoint(client):
    assert client.get("/").status_code == 200


def test_openapi_schema_builds(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/tenants" in response.json()["paths"]


# ----------------------------------------------------------------------
# Tenants
# ----------------------------------------------------------------------
def test_create_tenant(client):
    response = client.post(
        "/api/v1/tenants",
        json={
            "slug": "new-co",
            "name": "New Co",
            "industry": "Automotive",
            "contact_email": "ops@new-co.example",
        },
    )
    body = response.json()

    assert response.status_code == 201
    assert body["slug"] == "new-co"
    assert body["maturity_level"] == 0


def test_duplicate_slug_conflicts(client):
    payload = {"slug": "dupe", "name": "Dupe Co"}
    assert client.post("/api/v1/tenants", json=payload).status_code == 201
    assert client.post("/api/v1/tenants", json=payload).status_code == 409


def test_invalid_slug_rejected(client):
    response = client.post(
        "/api/v1/tenants", json={"slug": "Not A Slug!", "name": "Bad"}
    )
    assert response.status_code == 422


def test_invalid_email_rejected(client):
    response = client.post(
        "/api/v1/tenants",
        json={"slug": "bad-email", "name": "X", "contact_email": "not-an-email"},
    )
    assert response.status_code == 422


def test_get_tenant_by_slug_and_id(client, level_one_tenant):
    by_slug = client.get(f"/api/v1/tenants/{level_one_tenant.slug}")
    by_id = client.get(f"/api/v1/tenants/{level_one_tenant.id}")

    assert by_slug.status_code == 200
    assert by_id.status_code == 200
    assert by_slug.json()["id"] == by_id.json()["id"]


def test_get_unknown_tenant_404(client):
    assert client.get("/api/v1/tenants/nope").status_code == 404


def test_update_and_delete_tenant(client, level_one_tenant):
    updated = client.patch(
        f"/api/v1/tenants/{level_one_tenant.slug}", json={"name": "Renamed Ltd"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Ltd"

    deleted = client.delete(f"/api/v1/tenants/{level_one_tenant.slug}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/tenants/{level_one_tenant.slug}").status_code == 404


def test_list_tenants_paginates(client, level_one_tenant, level_two_tenant):
    response = client.get("/api/v1/tenants?limit=1")
    body = response.json()

    assert response.status_code == 200
    assert len(body["items"]) == 1
    assert body["total"] >= 2


def test_assess_endpoint_persists_level(client, db_session, level_one_tenant):
    response = client.post(f"/api/v1/tenants/{level_one_tenant.slug}/assess")
    body = response.json()

    assert response.status_code == 200
    assert body["level"] == 1
    assert body["level_name"]
    assert len(body["dimensions"]) == 4


def test_features_endpoint_lists_locked_and_enabled(client, level_one_tenant):
    response = client.get(f"/api/v1/tenants/{level_one_tenant.slug}/features")
    body = response.json()

    assert response.status_code == 200
    assert {f["feature_key"] for f in body["enabled"]}
    assert "rul_prediction" in {f["feature_key"] for f in body["locked"]}


def test_feature_override_endpoint(client, level_one_tenant):
    response = client.put(
        f"/api/v1/tenants/{level_one_tenant.slug}/features/rul_prediction",
        json={"enabled": True},
    )
    assert response.status_code == 200
    assert "rul_prediction" in {f["feature_key"] for f in response.json()["enabled"]}


def test_override_unknown_feature_404(client, level_one_tenant):
    response = client.put(
        f"/api/v1/tenants/{level_one_tenant.slug}/features/bogus",
        json={"enabled": True},
    )
    assert response.status_code == 404


def test_levels_reference_endpoint(client):
    response = client.get("/api/v1/tenants/levels")
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 5
    assert body[0]["level"] == 0


# ----------------------------------------------------------------------
# Machines
# ----------------------------------------------------------------------
def test_create_machine(client, make_tenant):
    make_tenant(slug="mfg")
    response = client.post(
        "/api/v1/machines",
        json={
            "machine_code": "CNC-01",
            "name": "CNC Mill 1",
            "machine_type": "CNC Mill",
            "production_line": "LINE-1",
            "line_position": 1,
            "criticality": 4,
            "hourly_output_units": 120,
            "hourly_downtime_cost": 1500,
        },
        headers={"X-Tenant-ID": "mfg"},
    )
    assert response.status_code == 201
    assert response.json()["machine_code"] == "CNC-01"


def test_duplicate_machine_code_conflicts(client, make_tenant):
    make_tenant(slug="mfg")
    payload = {"machine_code": "CNC-01", "name": "CNC Mill 1"}
    headers = {"X-Tenant-ID": "mfg"}

    assert client.post("/api/v1/machines", json=payload, headers=headers).status_code == 201
    assert client.post("/api/v1/machines", json=payload, headers=headers).status_code == 409


def test_same_machine_code_allowed_across_tenants(client, make_tenant):
    make_tenant(slug="mfg-a")
    make_tenant(slug="mfg-b")
    payload = {"machine_code": "SHARED-01", "name": "Press"}

    assert client.post(
        "/api/v1/machines", json=payload, headers={"X-Tenant-ID": "mfg-a"}
    ).status_code == 201
    assert client.post(
        "/api/v1/machines", json=payload, headers={"X-Tenant-ID": "mfg-b"}
    ).status_code == 201


def test_invalid_machine_status_rejected(client, make_tenant):
    make_tenant(slug="mfg")
    response = client.post(
        "/api/v1/machines",
        json={"machine_code": "X-1", "name": "X", "status": "exploded"},
        headers={"X-Tenant-ID": "mfg"},
    )
    assert response.status_code == 422


def test_criticality_out_of_range_rejected(client, make_tenant):
    make_tenant(slug="mfg")
    response = client.post(
        "/api/v1/machines",
        json={"machine_code": "X-1", "name": "X", "criticality": 9},
        headers={"X-Tenant-ID": "mfg"},
    )
    assert response.status_code == 422


def test_machine_lookup_by_code(client, level_one_tenant):
    response = client.get(
        "/api/v1/machines/L1-M001", headers={"X-Tenant-ID": level_one_tenant.slug}
    )
    assert response.status_code == 200
    assert response.json()["machine_code"] == "L1-M001"


def test_machine_filters(client, make_tenant, make_machine):
    tenant = make_tenant(slug="mfg")
    make_machine(tenant, code="A-1", production_line="LINE-1", status="operational")
    make_machine(tenant, code="A-2", production_line="LINE-2", status="down")
    headers = {"X-Tenant-ID": "mfg"}

    by_line = client.get("/api/v1/machines?production_line=LINE-2", headers=headers)
    by_status = client.get("/api/v1/machines?status=down", headers=headers)

    assert [m["machine_code"] for m in by_line.json()["items"]] == ["A-2"]
    assert [m["machine_code"] for m in by_status.json()["items"]] == ["A-2"]


def test_lines_and_sites_endpoints(client, level_one_tenant):
    headers = {"X-Tenant-ID": level_one_tenant.slug}
    assert client.get("/api/v1/machines/lines", headers=headers).json() == ["LINE-1"]
    assert client.get("/api/v1/machines/sites", headers=headers).json() == ["Plant 1"]


def test_machine_status_rollup(client, level_one_tenant):
    response = client.get(
        "/api/v1/machines/L1-M001/status",
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["maintenance_count"] > 0
    assert 0 <= body["health_score"] <= 100
    assert body["mtbf_hours"] is not None


def test_machine_status_list_sorted_worst_first(client, level_one_tenant):
    response = client.get(
        "/api/v1/machines/status", headers={"X-Tenant-ID": level_one_tenant.slug}
    )
    scores = [m["health_score"] for m in response.json()]

    assert response.status_code == 200
    assert scores == sorted(scores)


# ----------------------------------------------------------------------
# Maintenance
# ----------------------------------------------------------------------
def test_create_maintenance_derives_total_cost(client, level_one_tenant, now):
    machine_id = client.get(
        "/api/v1/machines/L1-M001", headers={"X-Tenant-ID": level_one_tenant.slug}
    ).json()["id"]

    response = client.post(
        "/api/v1/maintenance",
        json={
            "machine_id": machine_id,
            "maintenance_type": "reactive",
            "failure_mode": "seal_leak",
            "start_time": now.isoformat(),
            "downtime_hours": 3,
            "labor_cost": 200,
            "parts_cost": 550,
        },
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    assert response.status_code == 201
    assert response.json()["total_cost"] == 750.0


def test_maintenance_end_before_start_rejected(client, level_one_tenant, now):
    response = client.post(
        "/api/v1/maintenance",
        json={
            "machine_id": "L1-M001",
            "start_time": now.isoformat(),
            "end_time": (now - timedelta(hours=2)).isoformat(),
        },
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    assert response.status_code == 422


def test_invalid_maintenance_type_rejected(client, level_one_tenant, now):
    response = client.post(
        "/api/v1/maintenance",
        json={
            "machine_id": "L1-M001",
            "maintenance_type": "wishful",
            "start_time": now.isoformat(),
        },
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    assert response.status_code == 422


def test_maintenance_update_recomputes_total(client, level_one_tenant, now):
    headers = {"X-Tenant-ID": level_one_tenant.slug}
    created = client.post(
        "/api/v1/maintenance",
        json={
            "machine_id": "L1-M001",
            "start_time": now.isoformat(),
            "labor_cost": 100,
            "parts_cost": 100,
        },
        headers=headers,
    ).json()

    updated = client.patch(
        f"/api/v1/maintenance/{created['id']}",
        json={"parts_cost": 900},
        headers=headers,
    )
    assert updated.json()["total_cost"] == 1000.0


def test_maintenance_delete_and_404(client, level_one_tenant, now):
    headers = {"X-Tenant-ID": level_one_tenant.slug}
    created = client.post(
        "/api/v1/maintenance",
        json={"machine_id": "L1-M001", "start_time": now.isoformat()},
        headers=headers,
    ).json()

    assert client.delete(f"/api/v1/maintenance/{created['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/maintenance/{created['id']}", headers=headers).status_code == 404


def test_maintenance_type_filter(client, level_one_tenant):
    response = client.get(
        "/api/v1/maintenance?maintenance_type=planned&limit=500",
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    items = response.json()["items"]

    assert items
    assert all(item["maintenance_type"] == "planned" for item in items)


def test_maintenance_stats(client, level_one_tenant):
    response = client.get(
        "/api/v1/maintenance/stats", headers={"X-Tenant-ID": level_one_tenant.slug}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["total_records"] > 0
    assert body["reactive_count"] > 0
    assert 0 <= body["planned_ratio"] <= 1
    assert body["top_failure_modes"]
    assert body["monthly_trend"]


# ----------------------------------------------------------------------
# Production
# ----------------------------------------------------------------------
def test_production_ingest_allowed_below_level_two(client, level_one_tenant, now):
    """A tenant must be able to send production data in order to reach L2."""
    response = client.post(
        "/api/v1/production",
        json={
            "machine_id": "L1-M001",
            "start_time": now.isoformat(),
            "planned_units": 100,
            "produced_units": 90,
            "defective_units": 5,
            "planned_runtime_minutes": 480,
            "actual_runtime_minutes": 470,
        },
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    assert response.status_code == 201


def test_production_read_blocked_below_level_two(client, level_one_tenant):
    response = client.get(
        "/api/v1/production", headers={"X-Tenant-ID": level_one_tenant.slug}
    )
    assert response.status_code == 403
    assert response.json()["detail"]["required_level"] == 2


def test_production_defects_exceeding_output_rejected(client, level_two_tenant, now):
    response = client.post(
        "/api/v1/production",
        json={
            "machine_id": "L2-M001",
            "start_time": now.isoformat(),
            "produced_units": 10,
            "defective_units": 8,
            "scrap_units": 8,
        },
        headers={"X-Tenant-ID": level_two_tenant.slug},
    )
    assert response.status_code == 422


def test_production_response_includes_derived_metrics(client, level_two_tenant):
    response = client.get(
        "/api/v1/production?limit=1", headers={"X-Tenant-ID": level_two_tenant.slug}
    )
    item = response.json()["items"][0]

    assert 0 <= item["yield_rate"] <= 1
    assert 0 <= item["oee"] <= 1


def test_production_line_view(client, level_two_tenant):
    response = client.get(
        "/api/v1/production/lines/LINE-1",
        headers={"X-Tenant-ID": level_two_tenant.slug},
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body["stations"]) == 3
    assert body["bottleneck_machine_id"]
    assert sum(1 for s in body["stations"] if s["is_bottleneck"]) == 1


# ----------------------------------------------------------------------
# Sensors
# ----------------------------------------------------------------------
def test_sensor_ingest_allowed_below_level_three(client, level_two_tenant, now):
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "machine_id": "L2-M001",
            "sensor_type": "vibration",
            "value": 2.4,
            "unit": "mm/s",
            "recorded_at": now.isoformat(),
        },
        headers={"X-Tenant-ID": level_two_tenant.slug},
    )
    assert response.status_code == 201


def test_sensor_read_blocked_below_level_three(client, level_two_tenant):
    response = client.get(
        "/api/v1/sensors/readings", headers={"X-Tenant-ID": level_two_tenant.slug}
    )
    assert response.status_code == 403


def test_invalid_sensor_type_rejected(client, level_three_tenant, now):
    response = client.post(
        "/api/v1/sensors/readings",
        json={
            "machine_id": "L3-M001",
            "sensor_type": "vibes",
            "value": 1.0,
            "recorded_at": now.isoformat(),
        },
        headers={"X-Tenant-ID": level_three_tenant.slug},
    )
    assert response.status_code == 422


def test_sensor_batch_ingest(client, level_three_tenant, now):
    payload = {
        "readings": [
            {
                "machine_id": "L3-M001",
                "sensor_type": "temperature",
                "value": 60 + index,
                "unit": "degC",
                "recorded_at": (now - timedelta(minutes=index)).isoformat(),
            }
            for index in range(25)
        ]
    }
    response = client.post(
        "/api/v1/sensors/readings/batch",
        json=payload,
        headers={"X-Tenant-ID": level_three_tenant.slug},
    )
    assert response.status_code == 201
    assert response.json()["ingested"] == 25


def test_empty_sensor_batch_rejected(client, level_three_tenant):
    response = client.post(
        "/api/v1/sensors/readings/batch",
        json={"readings": []},
        headers={"X-Tenant-ID": level_three_tenant.slug},
    )
    assert response.status_code == 422


def test_sensor_series_downsamples(client, level_three_tenant):
    response = client.get(
        "/api/v1/sensors/series?machine_id=L3-M001&sensor_type=vibration"
        "&window_hours=200&max_points=50",
        headers={"X-Tenant-ID": level_three_tenant.slug},
    )
    body = response.json()

    assert response.status_code == 200
    assert 0 < len(body["points"]) <= 60
    assert body["minimum"] <= body["mean"] <= body["maximum"]


def test_sensor_latest_snapshot(client, level_three_tenant):
    response = client.get(
        "/api/v1/sensors/latest", headers={"X-Tenant-ID": level_three_tenant.slug}
    )
    body = response.json()

    assert response.status_code == 200
    assert len(body) == 3
    assert body[0]["readings"]
