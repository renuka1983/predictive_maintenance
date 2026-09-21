# Development guide

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
```

## Running

The backend works against SQLite, so no database server is needed to develop:

```bash
export DATABASE_URL="sqlite:///$(pwd)/dev.db"
python -m ml.data_generation.load_to_db --tenant all --reset
uvicorn app.main:app --app-dir backend --reload
```

```bash
cd frontend && npm run dev   # proxies /api to :8000
```

Against Postgres instead:

```bash
docker compose up -d postgres
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/manufacturing_ai"
```

## Tests

```bash
./scripts/run_tests.sh                                  # all, with coverage
DATABASE_URL=sqlite:// pytest backend/app/tests -k isolation -v
```

Each test gets a fresh in-memory SQLite database via the `db_session` fixture;
`client` wires a `TestClient` to that same session through a dependency
override, so API tests and service tests see identical data.

Fixtures worth knowing (`app/tests/conftest.py`):

| Fixture | Gives you |
|---|---|
| `make_tenant`, `make_machine` | factories |
| `seed_maintenance`, `seed_production`, `seed_sensors` | history factories |
| `level_one_tenant` | CMMS only, assessed to L1 |
| `level_two_tenant` | + production, assessed to L2 |
| `level_three_tenant` | + sensors, assessed to L3 |

## Adding a feature

1. Add a `Feature` to `backend/app/services/feature_catalog.py` with its
   `required_level`. That one entry drives the gate, the toggle table, the
   upgrade path and the frontend nav.
2. Implement the logic in a service — not in a router.
3. Add the endpoint, calling `FeatureGate.require(db, tenant, "<key>")` first.
4. Add the page/route under `frontend/src/pages/` and register it in
   `Navigation.jsx` and `App.jsx` (wrap in `<FeatureGate>`).
5. Test both sides of the gate: available at its level, 403 below it.

## Conventions

**Every query filters by tenant.** If you write a `select()` against a
tenant-owned table without a `tenant_id` predicate, that is a bug. Use
`get_tenant_machine` rather than `db.get(Machine, id)`.

**Routers stay thin.** Validation, gating, status codes. Analytics belong in
services, which take a `Session` and return schema objects.

**ML degrades, never bluffs.** A model with too little data falls back to a
documented statistical method and reports lower `confidence`. It does not
return a confident number it cannot support, and it does not 500.

**Timestamps are UTC.** SQLite drops `tzinfo` on read; use the `_as_utc`
helpers when comparing stored timestamps to `datetime.now(timezone.utc)`.

## Data generation

```bash
python ml/data_generation/generator.py --tenant tenant-c   # preview counts
python ml/data_generation/generate_tenant_c.py --dry-run   # single tenant
python -m ml.data_generation.load_to_db --tenant all --reset
```

Tenant specs live in `PILOT_TENANTS` in `generator.py`. Each is seeded, so runs
are reproducible. If you change generation parameters, re-check that each
tenant still lands on its `target_level` — the loader prints `OK`/`!!` per
tenant for exactly this reason.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `400 Missing required X-Tenant-ID header` | Tenant-scoped endpoint called without the header |
| `403 feature_locked` | Expected below the feature's level — run `/assess` after loading data |
| Tenant stuck at Level 0 | No machines, or CMMS dimension below 12.5/25 — check `GET /tenants/{id}/maturity` `dimensions[].detail` |
| Level does not change after loading data | Assessment is not automatic; `POST /tenants/{id}/assess` |
| Frontend shows "Cannot reach the API" | Backend not running, or `VITE_API_BASE_URL` unset while not using the dev proxy |
| RUL returns `null` | No degradation trend clears the noise floor — expected on healthy machines |
