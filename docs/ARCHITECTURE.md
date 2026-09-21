# Architecture

## The core idea

Most predictive-maintenance products assume the customer already has IoT
telemetry. Most factories do not — they have a CMMS export and a spreadsheet.
This platform inverts that: it assesses what data a customer actually has and
serves the most advanced analytics that data can honestly support, then shows
them exactly what to send to unlock the next tier.

That single decision shapes everything below.

## Layers

```
routers/     HTTP: validation, status codes, feature gating. Thin.
services/    All business logic. Pure functions over a Session.
models/      SQLAlchemy ORM. tenant_id on every table.
schemas/     Pydantic v2 boundary types.
```

Routers do not contain analytics. Services do not raise HTTP errors except
through `FeatureGate.require`, which is the one deliberate crossover — it
exists so that every 403 in the product has an identical, actionable shape.

## Multi-tenancy

**Isolation model:** shared database, shared schema, `tenant_id` discriminator.
Chosen over schema-per-tenant or database-per-tenant because the analytics are
cross-sectional within a tenant but never across tenants, and because 5,000
small manufacturers would mean 5,000 schemas to migrate.

The safeguards:

1. `get_current_tenant` resolves the `X-Tenant-ID` header once; every
   tenant-scoped route depends on it.
2. Helpers like `get_tenant_machine` take the resolved tenant and filter on it,
   so a route cannot fetch a row by id alone.
3. Foreign rows return **404, not 403**. A 403 would confirm the row exists,
   leaking the shape of another customer's estate.
4. `ON DELETE CASCADE` from `tenants` means offboarding is one statement.

The riskiest failure mode here is a future query that forgets the predicate.
`test_analytics_are_scoped_to_the_calling_tenant` guards the analytics path
specifically: it seeds a second tenant with deliberately extreme data and
asserts the first tenant's KPIs do not move.

## Maturity assessment

Four dimensions, 25 points each. The **score** is continuous and motivating;
the **level** is discrete and derived from data domains being present:

```
level 0 → no machines, or CMMS dimension below 12.5/25
level 1 → CMMS established
level 2 → + production ≥ 15/25
level 3 → + sensors   ≥ 15/25
level 4 → + more than one site
```

Levels are gated on the *previous* domain, not just the current one. Without
that, a tenant could wire up IoT first and land at Level 3 with no maintenance
history — and every Level 1 and 2 feature would then render empty. The rule is
tested directly.

Assessment is explicitly **not** run on every request. It is a multi-table
aggregate; running it on dashboard traffic would make the hot path scale with
history. `POST /tenants/{id}/assess` persists the level, and gating reads the
cached column.

## Feature gating

`feature_catalog.py` holds one `Feature` record per capability. It drives:

- `FeatureGate.is_enabled` / `.require` (the runtime gate)
- `feature_toggles` rows (audit trail of when each capability unlocked)
- the upgrade path in the maturity response
- the frontend's navigation and locked-state panels

**Manual overrides** are stored with `source="manual"` and beat the level in
both directions. `sync_toggles` only rewrites `source="auto"` rows, so an
override survives re-assessment. This is what makes trials possible.

**Ingest is never gated.** `POST /production` and `POST /sensors/readings`
work at any level, while the corresponding reads require L2/L3. Gating ingest
would create a deadlock: you need the data to earn the level, and the level to
send the data.

## The models

### Level 1 — Weibull reliability

Fitted with `scipy.stats.weibull_min.fit(data, floc=0)`; location is pinned at
zero because a time between failures cannot be negative.

The shape parameter β is the operationally useful output:

- β < 0.9 — infant mortality; suspect workmanship or parts quality
- β ≈ 1 — random failures; time-based replacement will not help, condition
  monitoring will
- β > 1.15 — wear-out; scheduled replacement before the characteristic life pays

The CDF is evaluated through `scipy` rather than expanding `1 - exp(-(t/η)^β)`
directly. With near-identical intervals — a metronomic PM schedule — the fitted
β runs into the hundreds and the closed form overflows. A β above 25 is also
reported at low confidence: the fit is numerically valid but is describing a
schedule, not a failure process.

### Level 2 — failure risk

Training rows are built by sliding a monthly snapshot over each machine's
history. Features describe the state strictly *before* the snapshot; the label
is whether a reactive work order followed within the horizon. Building both
training and inference rows through the same `_machine_features` function is
what keeps future information out of the features.

Below 24 rows, or with fewer than 3 positive labels, the service falls back to
a weighted heuristic index whose terms are bounded so the total stays in [0,1]
and every point is attributable. It reports `model_used` and `confidence` so
the caller always knows which produced the number.

### Level 2 — cascade impact

Deterministic, not learned. A serial line propagates a stoppage both ways:
downstream stations starve for input, upstream stations block because
work-in-progress has nowhere to go. Each idled station loses output at the
line rate — capped by the bottleneck, since a line never runs faster than its
slowest station.

This is the calculation that reframes the conversation: the cost of a stoppage
is rarely the repair bill, it is what the rest of the line did not make.

### Level 3 — remaining useful life

A least-squares trend per degradation channel (vibration, temperature,
acoustic, current), extrapolated to an alarm threshold set three sigma above
the machine's own healthy baseline. The channel with the shortest projected
life wins.

Two guards matter:

- **Noise floor.** A flat signal still fits a tiny positive slope from
  floating-point error, which extrapolates to a confident, meaningless answer.
  The rise across the window must exceed half the baseline standard deviation
  (and a relative epsilon) before a number is reported. Otherwise: `null`.
- **Horizon cap.** Linear extrapolation beyond a year is not meaningful, so
  results are capped at 8,760 hours.

This is a trend extrapolation, not the LSTM the original brief sketched. At the
data volumes a mid-market plant actually has — days of telemetry, not years —
a sequence model would be fitting noise, and it would add a deep-learning
runtime to every container. The interface (`method`, `confidence`,
`degradation_rate_per_hour`) is stable, so swapping in a sequence model for
customers with long histories is a service-internal change.

### Level 3 — anomaly detection

Readings are z-normalised within each `(machine, sensor_type)` group — the
normal range of a vibration probe on a press says nothing about one on an oven
— and the normalised values are then **pooled by channel** into one Isolation
Forest.

Pooling is a correctness decision before it is a performance one.
`contamination` makes a forest flag a fixed *proportion* of whatever it is
fitted to, so one model per machine-channel forces a false positive out of
every clean machine. Measured against the pilot data's known injected faults:

| | flagged | true positives | precision | recall | time |
|---|---|---|---|---|---|
| per machine-channel (75 models) | 75 | 28 | 37% | 82% | 6.5s |
| pooled per channel (5 models) | 54 | 33 | **61%** | **97%** | **0.6s** |

Severity is reported from the reading's deviation from its own machine's
baseline (|z| ≥ 6 critical, ≥ 4.5 high), which is what an operator can act on;
the raw forest score is returned alongside for ranking.

## Performance

The dashboard aggregates across every unlocked tier, which made it the natural
place for performance bugs to collect. Two were found and fixed by measurement:

| | before | after |
|---|---|---|
| `/analytics/dashboard` (L3 tenant) | 8.8s | 2.1s |
| `/analytics/dashboard` (L2 tenant) | 5.3s | 1.2s |
| `/analytics/anomalies` | 7.3s | 0.9s |

1. **Anomaly pooling** (above) — 75 model fits per request became 5.
2. **N+1 in the line view** — `production_line_view` queried batches once per
   machine. It now fetches the line's batches in one query and groups in
   memory.

The remaining ~2s on a Level 3 dashboard is risk-model training plus per-machine
RUL. The natural next step is to cache the trained risk model per tenant and
invalidate it on new maintenance data, rather than refitting per request.

## Frontend

React 18 + Vite, React Router, Recharts.

- `TenantProvider` holds the selected tenant and its feature set, so navigation
  can render locked states without every page refetching.
- `useApi` turns a 403 from the gate into a typed `FeatureLockedError`, which
  becomes an upgrade prompt rather than an error banner.
- Locked pages stay **visible but disabled** in the navigation with the level
  they need. The upgrade path is the product; hiding it would defeat it.
- Charts follow one convention set: a single y-axis (never dual), a fixed
  categorical colour order, status colours reserved for state and never reused
  as a series, a legend whenever two series share a plot, and a hover tooltip
  on every plot. The two-series palette was validated for colour-vision
  deficiency separation and surface contrast in both light and dark themes.

## Deliberate limitations

- **Authentication is not implemented.** Tenant scope comes from a header,
  which is correct for isolation but assumes a trusted caller. Production needs
  JWT or mTLS in front, with the tenant claim resolved from the token instead
  of the header. The dependency (`get_current_tenant`) is the single place that
  would change.
- **Real-time is HTTP polling**, not WebSockets. At a 10-second cadence over
  tens of machines this is cheaper to operate and debug; the polling interval
  is one constant.
- **No background job runner.** Assessment and model training happen in-request.
  The next scaling step is moving both to a worker with cached results.
