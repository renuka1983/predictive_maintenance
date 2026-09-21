"""Load generated pilot-tenant data straight into the database.

Runs in-process against the backend's own models, so it works against local
SQLite as well as the Dockerised PostgreSQL:

    python -m ml.data_generation.load_to_db --tenant all --reset
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
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
from ml.data_generation.generator import (  # noqa: E402
    PILOT_TENANTS,
    GeneratedData,
    generate_tenant,
)

SENSOR_CHUNK = 5000


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_tenant(data: GeneratedData, reset: bool = False) -> Dict[str, object]:
    """Insert one generated tenant and assess its resulting maturity."""
    db = SessionLocal()
    try:
        slug = data.tenant["slug"]
        existing = db.execute(
            select(Tenant).where(Tenant.slug == slug)
        ).scalar_one_or_none()

        if existing and not reset:
            raise SystemExit(
                f"Tenant '{slug}' already exists. Re-run with --reset to replace it."
            )
        if existing:
            db.delete(existing)
            db.commit()

        tenant = Tenant(**data.tenant)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        # --- site registry (Level 4 grouping metadata) ------------------
        for row in data.site_registry:
            db.add(Site(tenant_id=tenant.id, **row))
        db.commit()

        # --- machines ---------------------------------------------------
        code_to_id: Dict[str, str] = {}
        for row in data.machines:
            payload = dict(row)
            install = payload.pop("installation_date", None)
            machine = Machine(tenant_id=tenant.id, **payload)
            if install:
                machine.installation_date = datetime.fromisoformat(install).date()
            db.add(machine)
            db.flush()
            code_to_id[machine.machine_code] = machine.id
        db.commit()

        # --- maintenance ------------------------------------------------
        for row in data.maintenance:
            payload = dict(row)
            code = payload.pop("machine_code")
            payload["start_time"] = _parse(payload["start_time"])
            payload["end_time"] = _parse(payload["end_time"])
            db.add(
                MaintenanceRecord(
                    tenant_id=tenant.id, machine_id=code_to_id[code], **payload
                )
            )
        db.commit()

        # --- production -------------------------------------------------
        for row in data.production:
            payload = dict(row)
            code = payload.pop("machine_code")
            payload["start_time"] = _parse(payload["start_time"])
            payload["end_time"] = _parse(payload["end_time"])
            db.add(
                ProductionBatch(
                    tenant_id=tenant.id, machine_id=code_to_id[code], **payload
                )
            )
        db.commit()

        # --- sensors (chunked; this is the high-volume table) -----------
        buffer = []
        for row in data.sensors:
            payload = dict(row)
            code = payload.pop("machine_code")
            payload["recorded_at"] = _parse(payload["recorded_at"])
            buffer.append(
                SensorReading(
                    tenant_id=tenant.id, machine_id=code_to_id[code], **payload
                )
            )
            if len(buffer) >= SENSOR_CHUNK:
                db.bulk_save_objects(buffer)
                db.commit()
                buffer = []
        if buffer:
            db.bulk_save_objects(buffer)
            db.commit()

        # --- assess + unlock features -----------------------------------
        assessment = MaturityService.assess(db, tenant)
        FeatureGate.sync_toggles(db, tenant)

        return {
            "slug": slug,
            "tenant_id": tenant.id,
            "level": assessment.level,
            "score": assessment.score,
            **data.summary(),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tenant", choices=sorted(PILOT_TENANTS) + ["all"], default="all"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Replace the tenant if it already exists"
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    targets = (
        PILOT_TENANTS
        if args.tenant == "all"
        else {args.tenant: PILOT_TENANTS[args.tenant]}
    )

    print(f"Loading into: {engine.url.render_as_string(hide_password=True)}\n")
    for slug, spec in targets.items():
        data = generate_tenant(spec)
        result = load_tenant(data, reset=args.reset)
        expected = spec.target_level
        mark = "OK " if result["level"] == expected else "!! "
        print(
            f"{mark}{slug:10} {spec.name:22} "
            f"Level {result['level']} (expected {expected})  "
            f"score {result['score']:.1f}"
        )
        print(
            f"    sites={result['sites']} "
            f"machines={result['machines']} "
            f"maintenance={result['maintenance_records']} "
            f"production={result['production_batches']} "
            f"sensors={result['sensor_readings']}"
        )


if __name__ == "__main__":
    main()
