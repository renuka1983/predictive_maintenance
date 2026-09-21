-- ---------------------------------------------------------------------------
-- Manufacturing AI SaaS - PostgreSQL schema
--
-- The backend can create this schema itself via SQLAlchemy on startup; this
-- file is the authoritative DDL for environments where migrations are applied
-- out-of-band, and it adds the production indexes and constraints that the
-- ORM metadata alone does not express.
--
-- Multi-tenancy: every table carries tenant_id and cascades from tenants, so
-- deleting a customer removes all of their data in one statement.
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- --------------------------------------------------------------------------
-- Tenants
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id                  VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name                VARCHAR(200) NOT NULL,
    slug                VARCHAR(100) NOT NULL UNIQUE,
    industry            VARCHAR(100),
    contact_email       VARCHAR(200),
    subscription_tier   VARCHAR(50)  NOT NULL DEFAULT 'free',
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    maturity_level      INTEGER      NOT NULL DEFAULT 0,
    maturity_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_assessed_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_tenant_level CHECK (maturity_level BETWEEN 0 AND 4),
    CONSTRAINT ck_tenant_score CHECK (maturity_score BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS ix_tenants_slug ON tenants (slug);

-- --------------------------------------------------------------------------
-- Machines
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS machines (
    id                   VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id            VARCHAR(36)  NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    machine_code         VARCHAR(60)  NOT NULL,
    name                 VARCHAR(200) NOT NULL,
    machine_type         VARCHAR(100),
    manufacturer         VARCHAR(120),
    model_number         VARCHAR(120),
    site                 VARCHAR(120),
    production_line      VARCHAR(120),
    line_position        INTEGER,
    criticality          INTEGER      NOT NULL DEFAULT 3,
    status               VARCHAR(30)  NOT NULL DEFAULT 'operational',
    installation_date    DATE,
    hourly_output_units  DOUBLE PRECISION NOT NULL DEFAULT 0,
    hourly_downtime_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
    has_sensors          BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_machine_tenant_code UNIQUE (tenant_id, machine_code),
    CONSTRAINT ck_machine_criticality CHECK (criticality BETWEEN 1 AND 5),
    CONSTRAINT ck_machine_status CHECK (
        status IN ('operational', 'degraded', 'maintenance', 'down', 'retired')
    )
);

CREATE INDEX IF NOT EXISTS ix_machines_tenant       ON machines (tenant_id);
CREATE INDEX IF NOT EXISTS ix_machines_tenant_line  ON machines (tenant_id, production_line);
CREATE INDEX IF NOT EXISTS ix_machines_site         ON machines (site);

-- --------------------------------------------------------------------------
-- Maintenance history (CMMS) - the Level 1 foundation
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS maintenance_records (
    id                VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id         VARCHAR(36)  NOT NULL REFERENCES tenants(id)  ON DELETE CASCADE,
    machine_id        VARCHAR(36)  NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    work_order_number VARCHAR(80),
    maintenance_type  VARCHAR(30)  NOT NULL DEFAULT 'reactive',
    failure_mode      VARCHAR(120),
    description       TEXT,
    start_time        TIMESTAMPTZ  NOT NULL,
    end_time          TIMESTAMPTZ,
    downtime_hours    DOUBLE PRECISION NOT NULL DEFAULT 0,
    labor_hours       DOUBLE PRECISION NOT NULL DEFAULT 0,
    labor_cost        DOUBLE PRECISION NOT NULL DEFAULT 0,
    parts_cost        DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_cost        DOUBLE PRECISION NOT NULL DEFAULT 0,
    technician        VARCHAR(120),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_maint_type CHECK (
        maintenance_type IN ('planned', 'preventive', 'reactive', 'predictive')
    ),
    CONSTRAINT ck_maint_window CHECK (end_time IS NULL OR end_time >= start_time)
);

CREATE INDEX IF NOT EXISTS ix_maint_tenant         ON maintenance_records (tenant_id);
CREATE INDEX IF NOT EXISTS ix_maint_tenant_machine ON maintenance_records (tenant_id, machine_id);
CREATE INDEX IF NOT EXISTS ix_maint_tenant_start   ON maintenance_records (tenant_id, start_time);
CREATE INDEX IF NOT EXISTS ix_maint_failure_mode   ON maintenance_records (failure_mode);

-- --------------------------------------------------------------------------
-- Production batches (MES/ERP) - unlocks Level 2
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS production_batches (
    id                      VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id               VARCHAR(36) NOT NULL REFERENCES tenants(id)  ON DELETE CASCADE,
    machine_id              VARCHAR(36) NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    batch_number            VARCHAR(80),
    product_code            VARCHAR(80),
    start_time              TIMESTAMPTZ NOT NULL,
    end_time                TIMESTAMPTZ,
    planned_units           INTEGER     NOT NULL DEFAULT 0,
    produced_units          INTEGER     NOT NULL DEFAULT 0,
    defective_units         INTEGER     NOT NULL DEFAULT 0,
    scrap_units             INTEGER     NOT NULL DEFAULT 0,
    planned_runtime_minutes DOUBLE PRECISION NOT NULL DEFAULT 0,
    actual_runtime_minutes  DOUBLE PRECISION NOT NULL DEFAULT 0,
    downtime_minutes        DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_batch_units CHECK (defective_units + scrap_units <= produced_units)
);

CREATE INDEX IF NOT EXISTS ix_batch_tenant         ON production_batches (tenant_id);
CREATE INDEX IF NOT EXISTS ix_batch_tenant_machine ON production_batches (tenant_id, machine_id);
CREATE INDEX IF NOT EXISTS ix_batch_tenant_start   ON production_batches (tenant_id, start_time);

-- --------------------------------------------------------------------------
-- Sensor readings (IoT) - unlocks Level 3
--
-- Highest-volume table: a bigserial key and composite indexes tuned for the
-- "recent readings for a machine/channel" access pattern the API actually
-- issues. For large deployments, partition this table by month on recorded_at.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_readings (
    id          BIGSERIAL   PRIMARY KEY,
    tenant_id   VARCHAR(36) NOT NULL REFERENCES tenants(id)  ON DELETE CASCADE,
    machine_id  VARCHAR(36) NOT NULL REFERENCES machines(id) ON DELETE CASCADE,
    sensor_type VARCHAR(50) NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    unit        VARCHAR(30),
    quality     VARCHAR(20) NOT NULL DEFAULT 'good',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_sensor_quality CHECK (quality IN ('good', 'suspect', 'bad'))
);

CREATE INDEX IF NOT EXISTS ix_sensor_tenant              ON sensor_readings (tenant_id);
CREATE INDEX IF NOT EXISTS ix_sensor_tenant_machine_time ON sensor_readings (tenant_id, machine_id, recorded_at);
CREATE INDEX IF NOT EXISTS ix_sensor_tenant_type_time    ON sensor_readings (tenant_id, sensor_type, recorded_at);

-- --------------------------------------------------------------------------
-- Feature toggles
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feature_toggles (
    id             VARCHAR(36)  PRIMARY KEY DEFAULT gen_random_uuid()::text,
    tenant_id      VARCHAR(36)  NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    feature_key    VARCHAR(100) NOT NULL,
    is_enabled     BOOLEAN      NOT NULL DEFAULT FALSE,
    required_level INTEGER      NOT NULL DEFAULT 0,
    enabled_at     TIMESTAMPTZ,
    source         VARCHAR(20)  NOT NULL DEFAULT 'auto',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_feature_tenant_key UNIQUE (tenant_id, feature_key),
    CONSTRAINT ck_feature_source CHECK (source IN ('auto', 'manual'))
);

CREATE INDEX IF NOT EXISTS ix_feature_tenant ON feature_toggles (tenant_id);
