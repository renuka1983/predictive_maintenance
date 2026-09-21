# API reference

Base URL: `http://localhost:8000/api/v1` · Interactive docs: `/docs`

## Authentication and tenant scope

Tenant-scoped endpoints require an `X-Tenant-ID` header carrying the tenant's
id **or** slug:

```bash
curl -H "X-Tenant-ID: tenant-b" localhost:8000/api/v1/machines
```

| Situation | Response |
|---|---|
| Header missing | `400` — `Missing required X-Tenant-ID header` |
| Unknown tenant | `404` |
| Inactive tenant | `403` |
| Row belongs to another tenant | `404` (never 403 — see ARCHITECTURE.md) |
| Feature not unlocked | `403` with a structured `detail` |

Tenant administration endpoints (`/tenants/**`) do not take the header.

> **Note.** There is no user authentication layer yet; see *Deliberate
> limitations* in ARCHITECTURE.md.

---

## Tenants

| Method | Path | Description |
|---|---|---|
| `POST` | `/tenants` | Onboard a tenant at Level 0 |
| `GET` | `/tenants` | List tenants (`limit`, `offset`, `is_active`) |
| `GET` | `/tenants/levels` | Reference: level names, pricing, features |
| `GET` | `/tenants/{id}` | Fetch by id or slug |
| `PATCH` | `/tenants/{id}` | Update mutable fields |
| `DELETE` | `/tenants/{id}` | Delete the tenant and all its data |
| `POST` | `/tenants/{id}/assess` | Re-run assessment, persist level, sync toggles |
| `GET` | `/tenants/{id}/maturity` | Assessment (`refresh=true` to persist) |
| `GET` | `/tenants/{id}/features` | Enabled and locked features |
| `PUT` | `/tenants/{id}/features/{key}` | Manual override — body `{"enabled": true}` |

**`POST /tenants/{id}/assess`**

```json
{
  "tenant_id": "…",
  "level": 2,
  "level_name": "Predictive (CMMS + Production)",
  "score": 75.0,
  "dimensions": [
    { "name": "cmms", "score": 25.0, "max_score": 25.0,
      "detail": "361 maintenance records across 15/15 machines (target 50+ records)" },
    { "name": "production", "score": 25.0, "max_score": 25.0, "detail": "4944 production batches (target 50+)" },
    { "name": "iot_sensors", "score": 0.0, "max_score": 25.0, "detail": "0 readings from 0/15 instrumented machines" },
    { "name": "data_quality", "score": 25.0, "max_score": 25.0, "detail": "machine metadata 100%, record completeness 100%, recency 100%" }
  ],
  "upgrade_path": {
    "current_level": 2,
    "next_level": 3,
    "requirements": [
      "Stream at least 500 sensor readings",
      "Flag instrumented machines with has_sensors so coverage is at least 50%"
    ],
    "unlocks": ["Sensor Telemetry", "Real-time Monitoring", "Anomaly Detection", "Remaining Useful Life"]
  }
}
```

---

## Machines — Level 1

| Method | Path | Description |
|---|---|---|
| `POST` | `/machines` | Register a machine |
| `GET` | `/machines` | List (`site`, `production_line`, `status`, `has_sensors`) |
| `GET` | `/machines/lines` | Distinct production line names |
| `GET` | `/machines/sites` | Distinct site names |
| `GET` | `/machines/status` | Health rollup for all machines, worst first |
| `GET` | `/machines/{id}` | Fetch by id or machine code |
| `PATCH` | `/machines/{id}` | Update |
| `DELETE` | `/machines/{id}` | Delete with history |
| `GET` | `/machines/{id}/status` | Health rollup for one machine |

`machine_code` is unique per tenant, so two tenants may both use `LINE-1-M001`.
Any endpoint taking `{id}` accepts the id or the machine code.

---

## Maintenance — Level 1

| Method | Path | Description |
|---|---|---|
| `POST` | `/maintenance` | Log a work order |
| `GET` | `/maintenance` | Search (`machine_id`, `maintenance_type`, `failure_mode`, `start_after`, `start_before`) |
| `GET` | `/maintenance/stats` | MTBF, MTTR, planned ratio, Pareto, monthly trend |
| `GET`/`PATCH`/`DELETE` | `/maintenance/{id}` | Fetch, correct, delete |

`total_cost` is derived from `labor_cost + parts_cost` when omitted, and
recomputed on PATCH when either component changes and the total is not set
explicitly.

---

## Production — Level 2 to read

| Method | Path | Gate |
|---|---|---|
| `POST` | `/production` | **none** — ingest is always allowed |
| `GET` | `/production` | L2 |
| `GET` | `/production/lines/{line}` | L2 — station OEE with bottleneck flagged |
| `GET`/`PATCH`/`DELETE` | `/production/{id}` | L2 |

Responses carry derived `yield_rate` and `oee` (availability × performance ×
quality).

---

## Sensors — Level 3 to read

| Method | Path | Gate |
|---|---|---|
| `POST` | `/sensors/readings` | **none** |
| `POST` | `/sensors/readings/batch` | **none** — up to 5,000 readings |
| `GET` | `/sensors/readings` | L3 |
| `GET` | `/sensors/latest` | L3 — latest value per channel (the polling feed) |
| `GET` | `/sensors/series` | L3 — downsampled series for charting |

Valid `sensor_type`: `vibration`, `temperature`, `pressure`, `current`,
`acoustic`, `rpm`, `oil_quality`. Valid `quality`: `good`, `suspect`, `bad`.

---

## Analytics

| Method | Path | Gate | Returns |
|---|---|---|---|
| `GET` | `/analytics/dashboard` | none | Maturity-shaped summary; locked sections are `null` |
| `GET` | `/analytics/reliability/weibull` | L1 | Shape, scale, MTBF, 30-day failure probability |
| `GET` | `/analytics/risk` | L2 | Failure probability per machine with drivers |
| `GET` | `/analytics/cascade/{machine_id}` | L2 | Line-wide cost of a stoppage |
| `POST` | `/analytics/simulate` | L2 | What-if stoppage (`machine_id`, `downtime_hours`) |
| `GET` | `/analytics/roi` | L2 | Preventable cost and annualised savings |
| `GET` | `/analytics/anomalies` | L3 | Outlier readings (`window_hours`, `contamination`) |
| `GET` | `/analytics/rul` | L3 | Remaining useful life, soonest first |
| `GET` | `/analytics/benchmark` | L4 | Sites ranked by OEE |

Every ML response carries `model_used`/`method` and `confidence`, so a caller
can tell a trained prediction from a heuristic fallback.

**Locked-feature response**

```json
{
  "detail": {
    "error": "feature_locked",
    "message": "'Remaining Useful Life' requires maturity Level 3 (Real-time (Full + IoT)). Your tenant is at Level 1.",
    "feature_key": "rul_prediction",
    "required_level": 3,
    "current_level": 1
  }
}
```

---

## Conventions

**Pagination** — list endpoints take `limit` (1–500, default 50) and `offset`,
and return:

```json
{ "items": [...], "total": 137, "limit": 50, "offset": 0 }
```

**Status codes** — `201` create · `200` read/update/delete · `400` bad request
· `403` feature locked or inactive tenant · `404` not found or not yours ·
`409` duplicate slug or machine code · `422` validation failure.
