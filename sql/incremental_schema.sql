CREATE SCHEMA IF NOT EXISTS audit;

CREATE SEQUENCE IF NOT EXISTS audit.batch_attempt_sequence START 1;

CREATE TABLE IF NOT EXISTS audit.batch_attempt (
    attempt_id BIGINT PRIMARY KEY DEFAULT nextval('audit.batch_attempt_sequence'),
    batch_order INTEGER NOT NULL,
    source_file VARCHAR NOT NULL,
    file_sha256 VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp,
    finished_at TIMESTAMPTZ,
    failure_message VARCHAR
);

CREATE TABLE IF NOT EXISTS audit.source_file_registry (
    source_file VARCHAR PRIMARY KEY,
    dataset_role VARCHAR NOT NULL,
    batch_order INTEGER NOT NULL,
    file_sha256 VARCHAR NOT NULL,
    schema_sha256 VARCHAR NOT NULL,
    byte_size BIGINT NOT NULL,
    source_row_count BIGINT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
);

CREATE TABLE IF NOT EXISTS audit.batch_reconciliation (
    batch_order INTEGER PRIMARY KEY,
    batch_name VARCHAR UNIQUE NOT NULL,
    analytical_sha256 VARCHAR NOT NULL,
    snapshot_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS staging.order_event_lineage (
    source_row_uid VARCHAR PRIMARY KEY,
    canonical_event_hash VARCHAR NOT NULL,
    representative_source_row_uid VARCHAR NOT NULL,
    is_lineage_representative BOOLEAN NOT NULL,
    physical_row_count BIGINT NOT NULL,
    source_file VARCHAR NOT NULL,
    batch_order INTEGER NOT NULL,
    source_row_number BIGINT NOT NULL,
    row_hash VARCHAR NOT NULL
);
