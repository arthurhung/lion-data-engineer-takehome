CREATE OR REPLACE TABLE staging.order_event AS
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
           min(source_row_uid) OVER (PARTITION BY canonical_event_hash)
               AS representative_source_row_uid
    FROM identified
)
SELECT *, source_row_uid=representative_source_row_uid AS is_canonical_event
FROM ranked;

DELETE FROM staging.order_event_lineage;
INSERT INTO staging.order_event_lineage
SELECT source_row_uid,canonical_event_hash,representative_source_row_uid,
       source_row_uid=representative_source_row_uid,duplicate_source_row_count,
       source_file,batch_order,source_row_number,row_hash
FROM staging.order_event;
