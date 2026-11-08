# Manufacturing AI SaaS

A multi-tenant predictive-maintenance platform whose feature surface **expands
with each customer's data maturity**. A plant with nothing but a spreadsheet of
work orders gets real reliability analytics on day one; a plant streaming IoT
telemetry gets remaining-useful-life predictions. Nobody is asked to buy the
Level 3 product before they have Level 3 data.

```
Level 0  Onboarding                    Free        import data, see your score
Level 1  Reactive (CMMS)               $199/mo     MTBF, cost trends, Weibull curves
Level 2  Predictive (+ Production)     $499/mo     ML risk scoring, cascade impact, ROI
Level 3  Real-time (+ IoT sensors)     $1,499/mo   live monitoring, anomalies, RUL
Level 4  Enterprise (multi-site)       $2,999/mo   multi-site rollup, benchmarking
```

> **Also in this repo:** [`warehouse_twin/`](warehouse_twin/README.md) is an interactive 3D warehouse
> digital twin PoC for bundle tracking and truck dispatch assurance. It is self-contained, with its own backend,
> frontend and Docker Compose stack.

---

## Quick start

### Docker (full stack)

```bash
cp .env.example .env
./scripts/start_dev.sh          # postgres + backend + frontend
./scripts/load_pilot_data.sh    # three pilot tenants at Levels 1, 2 and 3
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| PgAdmin (optional) | `docker compose --profile tools up -d pgadmin` → http://localhost:5050 |

### Without Docker (SQLite)

Everything runs against SQLite, so you can evaluate the whole system with no
database server:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

export DATABASE_URL="sqlite:///$(pwd)/dev.db"
python -m ml.data_generation.load_to_db --tenant all --reset
uvicorn app.main:app --app-dir backend --reload

# in a second shell
cd frontend && npm install && npm run dev
```

### Tests

```bash
./scripts/run_tests.sh
# 107 passed · 95% statement coverage
```

---

## How maturity assessment works

Each tenant is scored on four 25-point dimensions for a 100-point total:

| Dimension | What it measures |
|---|---|
| `cmms` | Volume of maintenance records **and** how many machines they cover |
| `production` | Volume of MES/ERP production batches |
| `iot_sensors` | Reading volume **and** share of machines instrumented |
| `data_quality` | Field completeness, cost/failure-mode coverage, and recency |

The **level is derived from which data domains are populated**, not from the
score alone. Each level requires the previous domain to be materially present
(≥ 60% of its dimension score), so a tenant cannot skip to Level 3 by dumping
sensor data with no maintenance history — a property the test-suite pins down
(`test_sensor_data_alone_cannot_skip_to_level_three`).

Assessment runs on demand:

```bash
curl -X POST localhost:8000/api/v1/tenants/tenant-b/assess
```

It returns the score breakdown *and* the upgrade path — the specific things the
customer must send to reach the next level, and what that would unlock.

---

## Feature gating

One catalogue (`backend/app/services/feature_catalog.py`) is the single source
of truth. It drives the gate, the persisted toggle table, the upgrade path and
the frontend navigation, so adding a capability is a one-line change.

```python
FeatureGate.require(db, tenant, "cascade_impact_analysis")
```

A locked feature returns **403 with an actionable body**, not a bare error:

```json
{
  "detail": {
    "error": "feature_locked",
    "message": "'Cascade Impact Analysis' requires maturity Level 2 (Predictive (CMMS + Production)). Your tenant is at Level 1.",
    "feature_key": "cascade_impact_analysis",
    "required_level": 2,
    "current_level": 1
  }
}
```

Two deliberate design decisions:

- **Ingest is never gated.** A tenant must be able to POST production and
  sensor data *in order to earn* the level that unlocks reading it back.
  Gating ingest would make the upgrade path impossible to walk.
- **Manual overrides beat maturity and survive re-assessment**, so sales can
  run a trial of a higher tier without faking the customer's data.

---

## Level 4: the enterprise tier

Levels 1-3 answer "which machine is about to fail?". Level 4 answers a
different question — "which of my plants is worst, by how much, and what is
closing that gap worth?" — so every enterprise endpoint returns a *quantified
comparison* rather than a ranked list.

**Sites become first-class.** `Machine.site` stays a plain string, so Level 1-3
tenants need no site registry at all. The `sites` table is additive: it attaches
region and country to a site *name*, which is the join key. Sites used by
machines but absent from the registry still appear in rollups — they simply
cannot be grouped by region. `POST /sites/sync` registers every name already in
use.

**Portfolio rollup** (`/analytics/portfolio`) groups by site or region. Two
things it deliberately does not do: totals are recomputed from raw counts
rather than averaged from group rows, and headline OEE is machine-weighted —
otherwise a four-machine plant would swing the number as hard as a forty-machine
one.

**Benchmarking** (`/analytics/benchmark`) ranks sites on five metrics with
**direction-normalised percentiles**, so 1.0 means best-in-class whether the
metric is one to maximise (OEE, MTBF) or minimise (cost, downtime, reactive
ratio). That normalisation is what makes the composite score meaningful rather
than an average of incomparable numbers.

The headline is priced:

```
Benchmark site: Detroit Works @ $5,572/machine
Annualised saving if every plant matched it: $402,587
Biggest gap: Brno Facility ($70,732 over the window)
```

The target is the **best observed site, not a theoretical ideal** — which makes
the number defensible as "already achieved somewhere in your own estate".

**Fleet comparison** (`/analytics/fleet`) holds the asset class constant and
varies the site. Site-level benchmarking can hide the cause: a plant may look
expensive only because it runs more of one troublesome asset class. On the pilot
data this immediately surfaces that Robotic Welders are the one class where
Detroit is *not* best — Monterrey runs them at 1.6x less cost — which a
site-level ranking alone would never reveal.

---

## Multi-tenant isolation

Tenant scope travels in the `X-Tenant-ID` header (id or slug) and is resolved
by one dependency that every resource endpoint depends on. Every query filters
on `tenant_id`; there is no code path that reads a tenant-owned table without
that predicate.

```bash
curl -H "X-Tenant-ID: tenant-b" localhost:8000/api/v1/machines
```

A row belonging to another tenant is reported as **404, not 403** — the API
never confirms that another customer's assets exist. Nine tests in
`test_tenant_isolation.py` cover read, update, delete, cross-tenant writes and
analytics leakage.

---

## The models

Each model degrades gracefully: when a tenant has too little data to train, the
service falls back to a transparent statistical method and *reports the lower
confidence* rather than refusing to answer or bluffing.

| Level | Model | Fallback when data is thin |
|---|---|---|
| 1 | **Weibull** fitted to times between failures | exponential (shape = 1) below 3 intervals |
| 2 | **Gradient-boosted trees** over sliding monthly snapshots | explainable weighted risk index |
| 2 | **Cascade impact** — deterministic line propagation | — |
| 3 | **Degradation-trend RUL** — least-squares extrapolation to a 3σ alarm threshold | reports `null` when no trend clears the noise floor |
| 3 | **Isolation Forest** anomaly detection, pooled per channel | z-score screen below 50 readings |

Two notes on the modelling choices:

**Anomaly detection pools per sensor channel.** Readings are z-normalised
within each `(machine, sensor_type)` group, then pooled by channel into one
model. This is not just faster — `contamination` makes a forest flag a fixed
*share* of whatever population it sees, so fitting one model per machine
forces a false positive out of every clean machine. Measured against known
injected faults in the pilot data:

| Approach | Precision | Recall | Time |
|---|---|---|---|
| One forest per machine-channel (75 models) | 37% | 82% | 6.5s |
| Pooled per channel (5 models) | **61%** | **97%** | **0.6s** |

**RUL requires a trend that clears the noise floor.** A flat signal still
produces a tiny positive slope from floating-point error, which would
extrapolate to a confident and meaningless remaining life. The service requires
the fitted rise across the window to exceed half the baseline standard
deviation before it will report a number.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the reasoning in full.

---

## Project layout

```
backend/app/
  models/        7 SQLAlchemy models, tenant_id on every table
  schemas/       Pydantic v2 request/response types with domain validation
  services/      business logic: maturity, analytics, ML, enterprise, gating
  routers/       57 endpoints across 7 routers
  tests/         146 tests, 96% coverage
database/        PostgreSQL DDL with production indexes + seeds
ml/data_generation/   synthetic pilot tenants at Levels 1-4
frontend/src/
  pages/         15 pages, one per capability tier
  components/    navigation, feature gate, chart primitives
  hooks/         API + tenant context
docs/            architecture, API and development guides
```

---

## Pilot data

Three generated tenants, each landing on its intended level:

| Tenant | Company | Data | Level |
|---|---|---|---|
| `tenant-a` | Aurora Metalworks | CMMS only | **1** |
| `tenant-b` | Borealis Plastics | CMMS + production | **2** |
| `tenant-c` | Cascade Foods | CMMS + production + IoT | **3** |
| `tenant-d` | Delta Industries | 3 plants across 2 regions | **4** |

The generator builds structure, not just noise, so the models have something
real to find: failures are drawn from a Weibull process (a fit recovers the
shape parameter used to create them), production quality decays in the days
before a failure (which is what the risk model learns), and sensor traces carry
drift plus injected spikes (RUL and anomaly targets respectively). The
enterprise tenant's three plants are deliberately uneven — Detroit is
best-in-class, Brno runs ~2.6x its cost per machine — because a benchmark over
identical sites has nothing to report.

```bash
python ml/data_generation/generator.py            # preview counts
python -m ml.data_generation.load_to_db --reset   # generate and load
```

---

## API overview

Full interactive documentation at `/docs`. Tenant-scoped endpoints require the
`X-Tenant-ID` header.

| Group | Endpoints | Gate |
|---|---|---|
| `/tenants` | CRUD, `/assess`, `/maturity`, `/features` | none |
| `/machines` | CRUD, `/status`, `/lines`, `/sites` | L1 |
| `/maintenance` | CRUD, `/stats` | L1 |
| `/production` | CRUD, `/lines/{line}` | write: none · read: L2 |
| `/sensors` | `/readings`, `/readings/batch`, `/latest`, `/series` | write: none · read: L3 |
| `/analytics` | `/dashboard`, `/reliability/weibull`, `/risk`, `/cascade`, `/simulate`, `/roi`, `/anomalies`, `/rul`, `/portfolio`, `/benchmark`, `/fleet` | per feature |
| `/sites` | CRUD, `/sync`, `/unregistered`, `/regions` | L4 |

`/analytics/dashboard` returns one maturity-shaped payload: sections the tenant
has not unlocked come back as `null` rather than an error, so the UI renders an
upgrade prompt in their place without a second round of requests that would
only 403.
