"""Shared pytest fixtures.

Tests run against a file-backed SQLite database created fresh per test, so the
suite needs no Docker or PostgreSQL and every test starts from a clean schema.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# Must be set before app.config is imported anywhere.
os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Machine,
    MaintenanceRecord,
    ProductionBatch,
    SensorReading,
    Site,
    Tenant,
)
from app.services import FeatureGate, MaturityService  # noqa: E402


@pytest.fixture()
def db_session():
    """An isolated in-memory database session for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """TestClient wired to the per-test database session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def make_tenant(db_session) -> Callable[..., Tenant]:
    """Factory creating a tenant directly in the database."""

    def _make(slug: str = "acme", name: str = "Acme Manufacturing", **kwargs) -> Tenant:
        tenant = Tenant(slug=slug, name=name, **kwargs)
        db_session.add(tenant)
        db_session.commit()
        db_session.refresh(tenant)
        return tenant

    return _make


@pytest.fixture()
def make_machine(db_session) -> Callable[..., Machine]:
    """Factory creating a machine for a tenant."""

    def _make(tenant: Tenant, code: str = "M-001", **kwargs) -> Machine:
        defaults: Dict = {
            "name": f"Machine {code}",
            "machine_type": "CNC Mill",
            "site": "Plant 1",
            "production_line": "LINE-1",
            "line_position": 1,
            "criticality": 3,
            "hourly_output_units": 100.0,
            "hourly_downtime_cost": 900.0,
        }
        defaults.update(kwargs)
        machine = Machine(tenant_id=tenant.id, machine_code=code, **defaults)
        db_session.add(machine)
        db_session.commit()
        db_session.refresh(machine)
        return machine

    return _make


@pytest.fixture()
def seed_maintenance(db_session, now) -> Callable[..., int]:
    """Factory writing maintenance history for a machine."""

    def _seed(
        tenant: Tenant,
        machine: Machine,
        count: int = 30,
        maintenance_type: str = "reactive",
        spacing_days: float = 10.0,
        downtime_hours: float = 4.0,
    ) -> int:
        for index in range(count):
            start = now - timedelta(days=spacing_days * (count - index))
            db_session.add(
                MaintenanceRecord(
                    tenant_id=tenant.id,
                    machine_id=machine.id,
                    work_order_number=f"WO-{index:04d}",
                    maintenance_type=maintenance_type,
                    failure_mode="bearing_wear",
                    start_time=start,
                    end_time=start + timedelta(hours=downtime_hours),
                    downtime_hours=downtime_hours,
                    labor_hours=downtime_hours,
                    labor_cost=100.0,
                    parts_cost=400.0,
                    total_cost=500.0,
                )
            )
        db_session.commit()
        return count

    return _seed


@pytest.fixture()
def seed_production(db_session, now) -> Callable[..., int]:
    """Factory writing production batches for a machine."""

    def _seed(
        tenant: Tenant, machine: Machine, count: int = 60, produced: int = 800
    ) -> int:
        for index in range(count):
            start = now - timedelta(days=count - index)
            db_session.add(
                ProductionBatch(
                    tenant_id=tenant.id,
                    machine_id=machine.id,
                    batch_number=f"B-{index:04d}",
                    product_code="P-100",
                    start_time=start,
                    end_time=start + timedelta(hours=8),
                    planned_units=1000,
                    produced_units=produced,
                    defective_units=20,
                    scrap_units=10,
                    planned_runtime_minutes=480.0,
                    actual_runtime_minutes=450.0,
                    downtime_minutes=30.0,
                )
            )
        db_session.commit()
        return count

    return _seed


@pytest.fixture()
def seed_sensors(db_session, now) -> Callable[..., int]:
    """Factory writing a rising vibration trace for a machine."""

    def _seed(
        tenant: Tenant,
        machine: Machine,
        count: int = 600,
        sensor_type: str = "vibration",
        base: float = 2.0,
        drift: float = 0.002,
    ) -> int:
        for index in range(count):
            recorded = now - timedelta(minutes=10 * (count - index))
            db_session.add(
                SensorReading(
                    tenant_id=tenant.id,
                    machine_id=machine.id,
                    sensor_type=sensor_type,
                    value=base + drift * index,
                    unit="mm/s",
                    quality="good",
                    recorded_at=recorded,
                )
            )
        db_session.commit()
        return count

    return _seed


@pytest.fixture()
def level_one_tenant(db_session, make_tenant, make_machine, seed_maintenance):
    """A tenant with CMMS data only - assessed to Level 1."""
    tenant = make_tenant(slug="l1-tenant", name="Level One Ltd")
    for index in range(1, 4):
        machine = make_machine(tenant, code=f"L1-M{index:03d}", line_position=index)
        seed_maintenance(tenant, machine, count=20, spacing_days=12)
        seed_maintenance(
            tenant, machine, count=6, maintenance_type="planned", spacing_days=40
        )
    MaturityService.assess(db_session, tenant)
    FeatureGate.sync_toggles(db_session, tenant)
    return tenant


@pytest.fixture()
def level_two_tenant(
    db_session, make_tenant, make_machine, seed_maintenance, seed_production
):
    """A tenant with CMMS + production data - assessed to Level 2."""
    tenant = make_tenant(slug="l2-tenant", name="Level Two Ltd")
    for index in range(1, 4):
        machine = make_machine(tenant, code=f"L2-M{index:03d}", line_position=index)
        seed_maintenance(tenant, machine, count=20, spacing_days=12)
        seed_production(tenant, machine, count=40)
    MaturityService.assess(db_session, tenant)
    FeatureGate.sync_toggles(db_session, tenant)
    return tenant


@pytest.fixture()
def level_three_tenant(
    db_session,
    make_tenant,
    make_machine,
    seed_maintenance,
    seed_production,
    seed_sensors,
):
    """A tenant with CMMS + production + IoT data - assessed to Level 3."""
    tenant = make_tenant(slug="l3-tenant", name="Level Three Ltd")
    for index in range(1, 4):
        machine = make_machine(
            tenant, code=f"L3-M{index:03d}", line_position=index, has_sensors=True
        )
        seed_maintenance(tenant, machine, count=20, spacing_days=12)
        seed_production(tenant, machine, count=40)
        seed_sensors(tenant, machine, count=400)
    MaturityService.assess(db_session, tenant)
    FeatureGate.sync_toggles(db_session, tenant)
    return tenant


@pytest.fixture()
def make_site(db_session) -> Callable[..., Site]:
    """Factory registering a site for a tenant."""

    def _make(tenant: Tenant, name: str, **kwargs) -> Site:
        site = Site(tenant_id=tenant.id, name=name, **kwargs)
        db_session.add(site)
        db_session.commit()
        db_session.refresh(site)
        return site

    return _make


@pytest.fixture()
def level_four_tenant(
    db_session,
    make_tenant,
    make_site,
    make_machine,
    seed_maintenance,
    seed_production,
    seed_sensors,
):
    """A multi-site enterprise tenant - assessed to Level 4.

    The three plants are deliberately uneven: Detroit is the best performer,
    Brno the worst. Benchmarking over identical sites would have nothing to
    report, so the fixture bakes in the spread the tests assert on.
    """
    tenant = make_tenant(slug="l4-tenant", name="Level Four Group")

    # Benchmarks read a trailing 90-day window, so the plants must differ in
    # failure *density* rather than total count - spreading more records over
    # proportionally more days would look identical inside the window.
    plants = [
        # (site, region, count, spacing_days, downtime hours, produced units)
        ("Detroit", "North America", 10, 12.0, 2.0, 950),
        ("Monterrey", "North America", 20, 6.0, 4.0, 800),
        ("Brno", "Europe", 40, 3.0, 7.0, 650),
    ]
    for site, region, count, spacing, downtime, produced in plants:
        make_site(tenant, site, region=region, country="Testland")
        for index in range(1, 3):
            machine = make_machine(
                tenant,
                code=f"{site[:3].upper()}-M{index:03d}",
                site=site,
                machine_type="CNC Mill" if index == 1 else "Conveyor",
                line_position=index,
                has_sensors=True,
            )
            seed_maintenance(
                tenant, machine, count=count, spacing_days=spacing,
                downtime_hours=downtime,
            )
            seed_production(tenant, machine, count=40, produced=produced)
            seed_sensors(tenant, machine, count=400)

    MaturityService.assess(db_session, tenant)
    FeatureGate.sync_toggles(db_session, tenant)
    return tenant
