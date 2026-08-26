CREATE SCHEMA raw;
CREATE SCHEMA staging;
CREATE SCHEMA quality;
CREATE SCHEMA curated;

CREATE TABLE raw.order_event (
    order_id VARCHAR,
    member_id VARCHAR,
    product_id VARCHAR,
    channel VARCHAR,
    order_status VARCHAR,
    quantity VARCHAR,
    currency VARCHAR,
    amount VARCHAR,
    coupon_discount VARCHAR,
    order_created_at VARCHAR,
    departure_date VARCHAR,
    updated_at VARCHAR,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    batch_order INTEGER NOT NULL,
    row_hash VARCHAR NOT NULL,
    source_row_uid VARCHAR PRIMARY KEY,
    ingested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE raw.member_snapshot (
    member_id VARCHAR,
    member_name VARCHAR,
    member_level VARCHAR,
    city VARCHAR,
    birth_date VARCHAR,
    register_date VARCHAR,
    extract_date VARCHAR,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    batch_order INTEGER NOT NULL,
    row_hash VARCHAR NOT NULL,
    source_row_uid VARCHAR PRIMARY KEY,
    ingested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE raw.product (
    product_id VARCHAR,
    product_name VARCHAR,
    product_type VARCHAR,
    destination_country VARCHAR,
    destination_city VARCHAR,
    trip_days VARCHAR,
    base_price_twd VARCHAR,
    is_active VARCHAR,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    batch_order INTEGER NOT NULL,
    row_hash VARCHAR NOT NULL,
    source_row_uid VARCHAR PRIMARY KEY,
    ingested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE raw.fx_rate (
    rate_date VARCHAR,
    currency VARCHAR,
    rate_to_twd VARCHAR,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    batch_order INTEGER NOT NULL,
    row_hash VARCHAR NOT NULL,
    source_row_uid VARCHAR PRIMARY KEY,
    ingested_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE quality.issue_hit (
    dataset VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    business_key VARCHAR NOT NULL,
    source_row_uid VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    disposition VARCHAR NOT NULL,
    PRIMARY KEY (source_row_uid, rule_id)
);

CREATE TABLE quality.entity_rule (
    entity_type VARCHAR NOT NULL,
    business_key VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    disposition VARCHAR NOT NULL,
    affected_source_row_count BIGINT NOT NULL,
    PRIMARY KEY (entity_type, business_key, rule_id)
);

CREATE TABLE quality.entity_disposition (
    entity_type VARCHAR NOT NULL,
    business_key VARCHAR NOT NULL,
    final_disposition VARCHAR NOT NULL,
    is_curated_eligible BOOLEAN NOT NULL,
    matched_rule_count BIGINT NOT NULL,
    quarantine_rule_count BIGINT NOT NULL,
    PRIMARY KEY (entity_type, business_key)
);

CREATE TABLE quality.quarantine_row (
    dataset VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    business_key VARCHAR NOT NULL,
    source_row_uid VARCHAR PRIMARY KEY,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    rule_ids VARCHAR NOT NULL
);

CREATE TABLE curated.dim_date (
    date_sk INTEGER PRIMARY KEY,
    calendar_date DATE UNIQUE NOT NULL,
    calendar_year SMALLINT NOT NULL,
    calendar_quarter SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL,
    day_of_month SMALLINT NOT NULL,
    iso_year SMALLINT NOT NULL,
    iso_week SMALLINT NOT NULL,
    iso_weekday SMALLINT NOT NULL,
    year_month VARCHAR NOT NULL,
    month_name VARCHAR NOT NULL,
    weekday_name VARCHAR NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_month_start BOOLEAN NOT NULL,
    is_month_end BOOLEAN NOT NULL,
    is_quarter_start BOOLEAN NOT NULL,
    is_quarter_end BOOLEAN NOT NULL,
    is_year_start BOOLEAN NOT NULL,
    is_year_end BOOLEAN NOT NULL
);

CREATE TABLE curated.dim_product (
    product_sk BIGINT PRIMARY KEY,
    product_id VARCHAR UNIQUE,
    product_name VARCHAR NOT NULL,
    product_type VARCHAR NOT NULL,
    destination_country VARCHAR,
    destination_city VARCHAR,
    trip_days INTEGER,
    base_price_twd DECIMAL(24,4),
    is_active BOOLEAN,
    is_unknown BOOLEAN NOT NULL,
    source_file VARCHAR,
    source_row_number BIGINT,
    source_row_uid VARCHAR,
    row_hash VARCHAR
);

CREATE TABLE curated.dim_member (
    member_sk BIGINT PRIMARY KEY,
    member_id VARCHAR NOT NULL,
    member_name VARCHAR NOT NULL,
    member_level VARCHAR NOT NULL,
    city VARCHAR NOT NULL,
    birth_date DATE,
    register_date DATE,
    birth_date_sentinel BOOLEAN NOT NULL,
    birth_date_unknown BOOLEAN NOT NULL,
    birth_date_restatement BOOLEAN NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL,
    is_current BOOLEAN NOT NULL,
    version_hash VARCHAR NOT NULL,
    is_unknown BOOLEAN NOT NULL,
    source_extract_date DATE,
    source_file VARCHAR,
    source_row_number BIGINT,
    source_row_uid VARCHAR,
    row_hash VARCHAR,
    UNIQUE (member_id, valid_from)
);

CREATE TABLE curated.dim_member_lineage (
    member_sk BIGINT NOT NULL,
    source_row_uid VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    extract_date DATE NOT NULL,
    row_hash VARCHAR NOT NULL,
    PRIMARY KEY (member_sk, source_row_uid)
);

CREATE TABLE curated.fact_order (
    order_id VARCHAR PRIMARY KEY,
    member_sk BIGINT NOT NULL,
    product_sk BIGINT NOT NULL,
    member_id VARCHAR NOT NULL,
    product_id VARCHAR NOT NULL,
    order_date_sk INTEGER NOT NULL,
    departure_date_sk INTEGER NOT NULL,
    updated_date_sk INTEGER NOT NULL,
    fx_date_sk INTEGER NOT NULL,
    channel VARCHAR NOT NULL,
    order_status VARCHAR NOT NULL,
    quantity INTEGER NOT NULL,
    original_currency VARCHAR NOT NULL,
    normalized_currency VARCHAR NOT NULL,
    original_amount DECIMAL(24,4) NOT NULL,
    coupon_discount_twd_source DECIMAL(24,4) NOT NULL,
    rate_to_twd DECIMAL(24,8) NOT NULL,
    gross_amount_twd_exact DECIMAL(38,12) NOT NULL,
    net_amount_twd_exact DECIMAL(38,12) NOT NULL,
    gross_amount_twd DECIMAL(28,2) NOT NULL,
    net_amount_twd DECIMAL(28,2) NOT NULL,
    order_created_at TIMESTAMPTZ NOT NULL,
    departure_date DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    missing_product BOOLEAN NOT NULL,
    price_check_not_evaluable BOOLEAN NOT NULL,
    missing_member_asof BOOLEAN NOT NULL,
    currency_normalized BOOLEAN NOT NULL,
    timezone_assumed BOOLEAN NOT NULL,
    status_transition_warning BOOLEAN NOT NULL,
    duplicate_source_row_count BIGINT NOT NULL,
    source_file VARCHAR NOT NULL,
    source_row_number BIGINT NOT NULL,
    batch_order INTEGER NOT NULL,
    source_row_uid VARCHAR NOT NULL,
    row_hash VARCHAR NOT NULL
);
