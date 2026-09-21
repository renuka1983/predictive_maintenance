"""Multi-tenant isolation - the platform's most important security property."""


def test_machines_are_scoped_to_the_calling_tenant(
    client, make_tenant, make_machine
):
    tenant_a = make_tenant(slug="iso-a", name="Tenant A")
    tenant_b = make_tenant(slug="iso-b", name="Tenant B")
    make_machine(tenant_a, code="A-001")
    make_machine(tenant_b, code="B-001")
    make_machine(tenant_b, code="B-002")

    response = client.get("/api/v1/machines", headers={"X-Tenant-ID": "iso-a"})
    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert [m["machine_code"] for m in body["items"]] == ["A-001"]


def test_cannot_read_another_tenants_machine(client, make_tenant, make_machine):
    tenant_a = make_tenant(slug="iso-a")
    tenant_b = make_tenant(slug="iso-b")
    make_machine(tenant_a, code="A-001")
    foreign = make_machine(tenant_b, code="B-001")

    response = client.get(
        f"/api/v1/machines/{foreign.id}", headers={"X-Tenant-ID": "iso-a"}
    )

    # Reported as 404 rather than 403 so the API never confirms that another
    # tenant's asset exists.
    assert response.status_code == 404


def test_cannot_update_another_tenants_machine(client, make_tenant, make_machine):
    tenant_a = make_tenant(slug="iso-a")
    tenant_b = make_tenant(slug="iso-b")
    make_machine(tenant_a, code="A-001")
    foreign = make_machine(tenant_b, code="B-001")

    response = client.patch(
        f"/api/v1/machines/{foreign.id}",
        json={"status": "down"},
        headers={"X-Tenant-ID": "iso-a"},
    )
    assert response.status_code == 404


def test_cannot_delete_another_tenants_machine(client, make_tenant, make_machine):
    tenant_a = make_tenant(slug="iso-a")
    tenant_b = make_tenant(slug="iso-b")
    make_machine(tenant_a, code="A-001")
    foreign = make_machine(tenant_b, code="B-001")

    response = client.delete(
        f"/api/v1/machines/{foreign.id}", headers={"X-Tenant-ID": "iso-a"}
    )
    assert response.status_code == 404


def test_cannot_log_maintenance_against_another_tenants_machine(
    client, make_tenant, make_machine, now
):
    tenant_a = make_tenant(slug="iso-a")
    tenant_b = make_tenant(slug="iso-b")
    foreign = make_machine(tenant_b, code="B-001")

    response = client.post(
        "/api/v1/maintenance",
        json={
            "machine_id": foreign.id,
            "maintenance_type": "reactive",
            "start_time": now.isoformat(),
            "downtime_hours": 3,
        },
        headers={"X-Tenant-ID": "iso-a"},
    )
    assert response.status_code == 404


def test_maintenance_search_never_returns_other_tenants_rows(
    client, make_tenant, make_machine, seed_maintenance, level_one_tenant
):
    other = make_tenant(slug="iso-other", name="Other Co")
    other_machine = make_machine(other, code="OT-001")
    seed_maintenance(other, other_machine, count=15)

    response = client.get(
        "/api/v1/maintenance?limit=500",
        headers={"X-Tenant-ID": level_one_tenant.slug},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["total"] > 0
    assert all(item["tenant_id"] == level_one_tenant.id for item in body["items"])


def test_missing_tenant_header_is_rejected(client):
    response = client.get("/api/v1/machines")
    assert response.status_code == 400
    assert "X-Tenant-ID" in response.json()["detail"]


def test_unknown_tenant_header_is_404(client):
    response = client.get("/api/v1/machines", headers={"X-Tenant-ID": "ghost"})
    assert response.status_code == 404


def test_inactive_tenant_is_rejected(client, make_tenant):
    make_tenant(slug="dormant", is_active=False)
    response = client.get("/api/v1/machines", headers={"X-Tenant-ID": "dormant"})
    assert response.status_code == 403


def test_analytics_are_scoped_to_the_calling_tenant(
    client, level_one_tenant, make_tenant, make_machine, seed_maintenance
):
    """A second tenant's history must not inflate the first tenant's KPIs."""
    baseline = client.get(
        "/api/v1/maintenance/stats", headers={"X-Tenant-ID": level_one_tenant.slug}
    ).json()

    noisy = make_tenant(slug="noisy", name="Noisy Neighbour")
    noisy_machine = make_machine(noisy, code="NO-001")
    seed_maintenance(noisy, noisy_machine, count=50, downtime_hours=20)

    after = client.get(
        "/api/v1/maintenance/stats", headers={"X-Tenant-ID": level_one_tenant.slug}
    ).json()

    assert after["total_records"] == baseline["total_records"]
    assert after["total_cost"] == baseline["total_cost"]
