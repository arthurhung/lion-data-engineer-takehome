-- SQL is the authoritative Phase 2 ingestion and normalization implementation.
-- Python substitutes only the four allowlisted source paths.
WITH scanned AS (
    SELECT *, row_number() OVER ()::BIGINT AS source_row_number
    FROM read_csv('{{orders_base_path}}', header=true, auto_detect=false,
        columns={
            'order_id':'VARCHAR','member_id':'VARCHAR','product_id':'VARCHAR',
            'channel':'VARCHAR','order_status':'VARCHAR','quantity':'VARCHAR',
            'currency':'VARCHAR','amount':'VARCHAR','coupon_discount':'VARCHAR',
            'order_created_at':'VARCHAR','departure_date':'VARCHAR','updated_at':'VARCHAR'
        }, nullstr='__LION_NULL_SENTINEL__', strict_mode=true)
), hashed AS (
    SELECT *, sha256(to_json(struct_pack(
        order_id:=order_id, member_id:=member_id, product_id:=product_id, channel:=channel,
        order_status:=order_status, quantity:=quantity, currency:=currency, amount:=amount,
        coupon_discount:=coupon_discount, order_created_at:=order_created_at,
        departure_date:=departure_date, updated_at:=updated_at))) AS row_hash
    FROM scanned
)
INSERT INTO raw.order_event
SELECT order_id, member_id, product_id, channel, order_status, quantity, currency, amount,
       coupon_discount, order_created_at, departure_date, updated_at,
       'orders_base.csv', source_row_number, 0, row_hash,
       sha256('orders_base.csv|' || source_row_number::VARCHAR || '|' || row_hash),
       current_timestamp
FROM hashed;

WITH scanned AS (
    SELECT *, row_number() OVER ()::BIGINT AS source_row_number
    FROM read_csv('{{members_path}}', header=true, auto_detect=false,
        columns={
            'member_id':'VARCHAR','member_name':'VARCHAR','member_level':'VARCHAR','city':'VARCHAR',
            'birth_date':'VARCHAR','register_date':'VARCHAR','extract_date':'VARCHAR'
        }, nullstr='__LION_NULL_SENTINEL__', strict_mode=true)
), hashed AS (
    SELECT *, sha256(to_json(struct_pack(
        member_id:=member_id, member_name:=member_name, member_level:=member_level, city:=city,
        birth_date:=birth_date, register_date:=register_date, extract_date:=extract_date
    ))) AS row_hash FROM scanned
)
INSERT INTO raw.member_snapshot
SELECT member_id, member_name, member_level, city, birth_date, register_date, extract_date,
       'members.csv', source_row_number, 0, row_hash,
       sha256('members.csv|' || source_row_number::VARCHAR || '|' || row_hash), current_timestamp
FROM hashed;

WITH scanned AS (
    SELECT *, row_number() OVER ()::BIGINT AS source_row_number
    FROM read_csv('{{products_path}}', header=true, auto_detect=false,
        columns={
            'product_id':'VARCHAR','product_name':'VARCHAR','product_type':'VARCHAR',
            'destination_country':'VARCHAR','destination_city':'VARCHAR','trip_days':'VARCHAR',
            'base_price_twd':'VARCHAR','is_active':'VARCHAR'
        }, nullstr='__LION_NULL_SENTINEL__', strict_mode=true)
), hashed AS (
    SELECT *, sha256(to_json(struct_pack(
        product_id:=product_id, product_name:=product_name, product_type:=product_type,
        destination_country:=destination_country, destination_city:=destination_city,
        trip_days:=trip_days, base_price_twd:=base_price_twd, is_active:=is_active
    ))) AS row_hash FROM scanned
)
INSERT INTO raw.product
SELECT product_id, product_name, product_type, destination_country, destination_city,
       trip_days, base_price_twd, is_active, 'products.csv', source_row_number, 0, row_hash,
       sha256('products.csv|' || source_row_number::VARCHAR || '|' || row_hash), current_timestamp
FROM hashed;

WITH scanned AS (
    SELECT *, row_number() OVER ()::BIGINT AS source_row_number
    FROM read_csv('{{fx_rates_path}}', header=true, auto_detect=false,
        columns={'rate_date':'VARCHAR','currency':'VARCHAR','rate_to_twd':'VARCHAR'},
        nullstr='__LION_NULL_SENTINEL__', strict_mode=true)
), hashed AS (
    SELECT *, sha256(to_json(struct_pack(
        rate_date:=rate_date, currency:=currency, rate_to_twd:=rate_to_twd
    ))) AS row_hash FROM scanned
)
INSERT INTO raw.fx_rate
SELECT rate_date, currency, rate_to_twd, 'fx_rates.csv', source_row_number, 0, row_hash,
       sha256('fx_rates.csv|' || source_row_number::VARCHAR || '|' || row_hash), current_timestamp
FROM hashed;

CREATE TABLE staging.fx_rate AS
SELECT try_cast(rate_date AS DATE) AS rate_date,
       trim(currency) AS currency,
       try_cast(rate_to_twd AS DECIMAL(24,8)) AS rate_to_twd,
       source_file, source_row_number, batch_order, row_hash, source_row_uid, ingested_at
FROM raw.fx_rate;

CREATE TABLE staging.product AS
SELECT trim(product_id) AS product_id,
       trim(product_name) AS product_name,
       trim(product_type) AS product_type,
       trim(destination_country) AS destination_country,
       trim(destination_city) AS destination_city,
       try_cast(trip_days AS INTEGER) AS trip_days,
       try_cast(base_price_twd AS DECIMAL(24,4)) AS base_price_twd,
       trim(is_active) AS is_active,
       source_file, source_row_number, batch_order, row_hash, source_row_uid, ingested_at
FROM raw.product;

CREATE TABLE staging.member_snapshot AS
WITH typed AS (
    SELECT trim(member_id) AS member_id, member_name, trim(member_level) AS member_level,
           trim(city) AS city, birth_date AS raw_birth_date,
           CASE WHEN birth_date = '1900-01-01' THEN NULL ELSE try_cast(birth_date AS DATE) END
               AS row_birth_date,
           birth_date = '1900-01-01' AS birth_date_sentinel,
           try_cast(register_date AS DATE) AS register_date,
           try_cast(extract_date AS DATE) AS extract_date,
           source_file, source_row_number, batch_order, row_hash, source_row_uid, ingested_at
    FROM raw.member_snapshot
), birth_semantics AS (
    SELECT member_id,
           count(DISTINCT row_birth_date) FILTER (WHERE row_birth_date IS NOT NULL)
               AS distinct_real_birth_dates,
           min(row_birth_date) FILTER (WHERE row_birth_date IS NOT NULL) AS unique_real_birth_date,
           bool_or(birth_date_sentinel) AS has_birth_date_sentinel
    FROM typed GROUP BY member_id
), enriched AS (
    SELECT t.*,
           CASE WHEN b.distinct_real_birth_dates = 1 THEN b.unique_real_birth_date END
               AS canonical_birth_date,
           b.has_birth_date_sentinel,
           b.distinct_real_birth_dates = 0 AS birth_date_unknown,
           b.has_birth_date_sentinel AND b.distinct_real_birth_dates = 1
               AS birth_date_restatement,
           b.distinct_real_birth_dates >= 2 AS birth_date_identity_ambiguous,
           sha256(to_json(struct_pack(
               schema_version:='member-payload-v1', member_name:=t.member_name,
               member_level:=t.member_level, city:=t.city,
               birth_date:=CASE WHEN b.distinct_real_birth_dates = 1
                               THEN b.unique_real_birth_date::VARCHAR ELSE '<NULL>' END,
               register_date:=coalesce(t.register_date::VARCHAR, '<NULL>')
           ))) AS snapshot_payload_hash,
           sha256(to_json(struct_pack(
               schema_version:='member-state-v1', member_level:=coalesce(t.member_level,'<NULL>'),
               city:=coalesce(t.city,'<NULL>')
           ))) AS version_hash
    FROM typed t JOIN birth_semantics b USING (member_id)
), ranked AS (
    SELECT *, count(*) OVER (PARTITION BY member_id, extract_date, snapshot_payload_hash)
               AS identical_snapshot_count,
           count(DISTINCT snapshot_payload_hash) OVER (PARTITION BY member_id, extract_date)
               AS same_day_payload_count,
           row_number() OVER (
               PARTITION BY member_id, extract_date, snapshot_payload_hash
               ORDER BY source_row_uid
           ) AS identical_snapshot_rank
    FROM enriched
)
SELECT *, identical_snapshot_rank = 1 AS is_canonical_snapshot
FROM ranked;

CREATE TABLE staging.order_event AS
WITH typed AS (
    SELECT trim(order_id) AS order_id, trim(member_id) AS member_id,
           trim(product_id) AS product_id, trim(channel) AS channel,
           trim(order_status) AS order_status, try_cast(quantity AS INTEGER) AS quantity,
           currency AS raw_currency,
           CASE WHEN trim(currency) = 'NTD' THEN 'TWD' ELSE trim(currency) END
               AS normalized_currency,
           try_cast(amount AS DECIMAL(24,4)) AS original_amount,
           try_cast(coupon_discount AS DECIMAL(24,4)) AS coupon_discount_twd_source,
           order_created_at AS raw_order_created_at,
           CASE
               WHEN regexp_full_match(order_created_at, '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
               THEN timezone('Asia/Taipei', try_strptime(order_created_at, '%Y/%m/%d %H:%M:%S'))
               ELSE try_cast(order_created_at AS TIMESTAMPTZ)
           END AS order_created_at,
           regexp_full_match(order_created_at, '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
               AS timezone_assumed,
           try_cast(departure_date AS DATE) AS departure_date,
           try_cast(updated_at AS TIMESTAMPTZ) AS updated_at,
           source_file, source_row_number, batch_order, row_hash, source_row_uid, ingested_at
    FROM raw.order_event
), dated AS (
    SELECT *, timezone('Asia/Taipei', order_created_at)::DATE AS order_business_date,
           timezone('Asia/Taipei', updated_at)::DATE AS updated_business_date,
           normalized_currency <> trim(raw_currency) AS currency_normalized
    FROM typed
), fx_joined AS (
    SELECT d.*, CASE WHEN d.normalized_currency = 'TWD' THEN 1.00000000::DECIMAL(24,8)
                     ELSE f.rate_to_twd END AS rate_to_twd,
           f.source_row_uid AS fx_source_row_uid
    FROM dated d LEFT JOIN staging.fx_rate f
      ON f.rate_date = d.order_business_date AND f.currency = d.normalized_currency
), calculated AS (
    SELECT *, cast(original_amount * rate_to_twd AS DECIMAL(38,12)) AS gross_amount_twd_exact,
           cast(original_amount * rate_to_twd - coupon_discount_twd_source AS DECIMAL(38,12))
               AS net_amount_twd_exact
    FROM fx_joined
), identified AS (
    SELECT *, sha256(to_json(struct_pack(
        schema_version:='order-event-v1', order_id:=order_id, member_id:=member_id,
        product_id:=product_id, channel:=channel, order_status:=order_status,
        quantity:=quantity, currency:=normalized_currency, amount:=original_amount,
        coupon_discount:=coupon_discount_twd_source,
        order_created_at:=order_created_at::VARCHAR, departure_date:=departure_date,
        updated_at:=updated_at::VARCHAR
    ))) AS canonical_event_hash,
    sha256(to_json(struct_pack(
        schema_version:='order-invariant-v1', member_id:=member_id, product_id:=product_id,
        channel:=channel, quantity:=quantity, currency:=normalized_currency,
        amount:=original_amount, coupon_discount:=coupon_discount_twd_source,
        order_created_at:=order_created_at::VARCHAR, departure_date:=departure_date
    ))) AS invariant_hash
    FROM calculated
), ranked AS (
    SELECT *, count(*) OVER (PARTITION BY canonical_event_hash) AS duplicate_source_row_count,
           row_number() OVER (PARTITION BY canonical_event_hash ORDER BY source_row_uid)
               AS canonical_event_rank
    FROM identified
)
SELECT *, canonical_event_rank = 1 AS is_canonical_event
FROM ranked;
