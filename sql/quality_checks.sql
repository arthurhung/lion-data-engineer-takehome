-- Authoritative Phase 1 detector logic.
-- Each detector must return: business_key, sample_sort_key, sample_json.
-- Views raw_orders, raw_members, raw_products and raw_fx_rates are registered by quality.py.

-- detector: SRC-001
WITH candidates AS (
    SELECT 'orders' AS dataset, source_file, source_row_number, order_id AS business_key
    FROM raw_orders
    WHERE order_id IS NULL OR trim(order_id) = '' OR member_id IS NULL OR trim(member_id) = ''
       OR product_id IS NULL OR trim(product_id) = '' OR channel IS NULL OR trim(channel) = ''
       OR order_status IS NULL OR trim(order_status) = '' OR quantity IS NULL OR trim(quantity) = ''
       OR currency IS NULL OR trim(currency) = '' OR amount IS NULL OR trim(amount) = ''
       OR coupon_discount IS NULL OR trim(coupon_discount) = ''
       OR order_created_at IS NULL OR trim(order_created_at) = ''
       OR departure_date IS NULL OR trim(departure_date) = ''
       OR updated_at IS NULL OR trim(updated_at) = ''
    UNION ALL
    SELECT 'members', source_file, source_row_number, member_id
    FROM raw_members
    WHERE member_id IS NULL OR trim(member_id) = '' OR member_name IS NULL OR trim(member_name) = ''
       OR member_level IS NULL OR trim(member_level) = '' OR city IS NULL OR trim(city) = ''
       OR register_date IS NULL OR trim(register_date) = '' OR extract_date IS NULL OR trim(extract_date) = ''
    UNION ALL
    SELECT 'products', source_file, source_row_number, product_id
    FROM raw_products
    WHERE product_id IS NULL OR trim(product_id) = '' OR product_name IS NULL OR trim(product_name) = ''
       OR product_type IS NULL OR trim(product_type) = ''
       OR destination_country IS NULL OR trim(destination_country) = ''
       OR destination_city IS NULL OR trim(destination_city) = ''
       OR trip_days IS NULL OR trim(trip_days) = '' OR base_price_twd IS NULL OR trim(base_price_twd) = ''
       OR is_active IS NULL OR trim(is_active) = ''
    UNION ALL
    SELECT 'fx_rates', source_file, source_row_number, concat_ws('|', rate_date, currency)
    FROM raw_fx_rates
    WHERE rate_date IS NULL OR trim(rate_date) = '' OR currency IS NULL OR trim(currency) = ''
       OR rate_to_twd IS NULL OR trim(rate_to_twd) = ''
)
SELECT business_key,
       dataset || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('dataset', dataset, 'source_file', source_file,
                   'source_row_number', source_row_number, 'business_key', business_key) AS sample_json
FROM candidates;

-- detector: SRC-002
WITH candidates AS (
    SELECT 'orders' AS dataset, source_file, source_row_number, order_id AS business_key
    FROM raw_orders
    WHERE order_id != trim(order_id) OR member_id != trim(member_id)
       OR product_id != trim(product_id) OR channel != trim(channel)
       OR order_status != trim(order_status) OR quantity != trim(quantity)
       OR currency != trim(currency) OR amount != trim(amount)
       OR coupon_discount != trim(coupon_discount)
       OR order_created_at != trim(order_created_at) OR departure_date != trim(departure_date)
       OR updated_at != trim(updated_at)
    UNION ALL
    SELECT 'members', source_file, source_row_number, member_id
    FROM raw_members
    WHERE member_id != trim(member_id) OR member_name != trim(member_name)
       OR member_level != trim(member_level) OR city != trim(city)
    UNION ALL
    SELECT 'products', source_file, source_row_number, product_id
    FROM raw_products
    WHERE product_id != trim(product_id) OR product_name != trim(product_name)
       OR product_type != trim(product_type) OR destination_country != trim(destination_country)
       OR destination_city != trim(destination_city) OR is_active != trim(is_active)
    UNION ALL
    SELECT 'fx_rates', source_file, source_row_number, concat_ws('|', rate_date, currency)
    FROM raw_fx_rates
    WHERE rate_date != trim(rate_date) OR currency != trim(currency) OR rate_to_twd != trim(rate_to_twd)
)
SELECT business_key,
       dataset || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('dataset', dataset, 'source_file', source_file,
                   'source_row_number', source_row_number, 'business_key', business_key) AS sample_json
FROM candidates;

-- detector: ORD-001
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY order_id, member_id, product_id, channel, order_status,
        quantity, currency, amount, coupon_discount, order_created_at, departure_date, updated_at) AS copies
    FROM raw_orders
)
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'source_file', source_file,
                   'source_row_number', source_row_number, 'updated_at', updated_at) AS sample_json
FROM marked WHERE copies > 1;

-- detector: ORD-002
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY order_id) AS event_count FROM raw_orders
)
SELECT order_id AS business_key,
       order_id || '|' || updated_at || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'event_count', event_count,
                   'source_file', source_file, 'updated_at', updated_at, 'order_status', order_status) AS sample_json
FROM marked WHERE event_count > 1;

-- detector: ORD-003
WITH marked AS (
    SELECT *, count(DISTINCT md5(concat_ws(chr(31), member_id, product_id, channel, order_status,
        quantity, currency, amount, coupon_discount, order_created_at, departure_date)))
        OVER (PARTITION BY order_id, updated_at) AS payload_count
    FROM raw_orders
)
SELECT order_id AS business_key,
       order_id || '|' || updated_at || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'updated_at', updated_at, 'order_status', order_status,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM marked WHERE payload_count > 1;

-- detector: ORD-004
WITH bad_keys AS (
    SELECT order_id
    FROM raw_orders
    GROUP BY order_id
    HAVING count(DISTINCT member_id) > 1 OR count(DISTINCT product_id) > 1
        OR count(DISTINCT channel) > 1 OR count(DISTINCT quantity) > 1
        OR count(DISTINCT currency) > 1 OR count(DISTINCT amount) > 1
        OR count(DISTINCT coupon_discount) > 1 OR count(DISTINCT order_created_at) > 1
        OR count(DISTINCT departure_date) > 1
)
SELECT o.order_id AS business_key,
       o.order_id || '|' || o.updated_at || '|' || o.source_file || '|' || lpad(o.source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', o.order_id, 'member_id', o.member_id, 'product_id', o.product_id,
                   'currency', o.currency, 'order_created_at', o.order_created_at,
                   'source_file', o.source_file, 'source_row_number', o.source_row_number) AS sample_json
FROM raw_orders o JOIN bad_keys b USING (order_id);

-- detector: ORD-005
WITH max_times AS (
    SELECT order_id, max(try_cast(updated_at AS TIMESTAMPTZ)) AS max_updated_at
    FROM raw_orders GROUP BY order_id
), marked AS (
    SELECT o.*, count(*) OVER (PARTITION BY o.order_id) AS latest_candidates
    FROM raw_orders o JOIN max_times m ON o.order_id = m.order_id
      AND try_cast(o.updated_at AS TIMESTAMPTZ) = m.max_updated_at
)
SELECT order_id AS business_key,
       order_id || '|' || updated_at || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'updated_at', updated_at, 'latest_candidates', latest_candidates,
                   'order_status', order_status, 'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM marked WHERE latest_candidates > 1;

-- detector: ORD-006
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'order_status', order_status,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders WHERE order_status NOT IN ('created', 'paid', 'completed', 'cancelled');

-- detector: ORD-007
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'channel', channel,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders WHERE channel NOT IN ('app', 'web', '門市', '電銷');

-- detector: ORD-008
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'quantity', quantity,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders WHERE try_cast(quantity AS INTEGER) IS NULL OR try_cast(quantity AS INTEGER) <= 0;

-- detector: ORD-009
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'currency', currency,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders WHERE currency NOT IN ('JPY', 'TWD', 'USD');

-- detector: ORD-010
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'amount', amount, 'currency', currency,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE try_cast(amount AS DECIMAL(24,4)) IS NULL OR try_cast(amount AS DECIMAL(24,4)) <= 0;

-- detector: ORD-011
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'coupon_discount', coupon_discount,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE try_cast(coupon_discount AS DECIMAL(24,4)) IS NULL
   OR try_cast(coupon_discount AS DECIMAL(24,4)) < 0;

-- detector: ORD-012
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'order_created_at', order_created_at,
                   'departure_date', departure_date, 'updated_at', updated_at,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE NOT regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
   OR NOT regexp_full_match(updated_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$');

-- detector: ORD-013
SELECT order_id AS business_key,
       order_id || '|' || updated_at || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'order_created_at', order_created_at, 'updated_at', updated_at,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
  AND regexp_full_match(updated_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
  AND try_cast(updated_at AS TIMESTAMPTZ) < try_cast(order_created_at AS TIMESTAMPTZ);

-- detector: ORD-014
SELECT order_id AS business_key,
       order_id || '|' || departure_date || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'order_created_at', order_created_at, 'departure_date', departure_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
  AND try_cast(departure_date AS DATE)
      < cast(try_cast(order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE);

-- detector: ORD-015
SELECT o.order_id AS business_key,
       o.order_id || '|' || o.source_file || '|' || lpad(o.source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', o.order_id, 'member_id', o.member_id,
                   'source_file', o.source_file, 'source_row_number', o.source_row_number) AS sample_json
FROM raw_orders o
LEFT JOIN (SELECT DISTINCT member_id FROM raw_members) m USING (member_id)
WHERE m.member_id IS NULL;

-- detector: ORD-016
SELECT o.order_id AS business_key,
       o.order_id || '|' || o.source_file || '|' || lpad(o.source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', o.order_id, 'product_id', o.product_id,
                   'source_file', o.source_file, 'source_row_number', o.source_row_number) AS sample_json
FROM raw_orders o
LEFT JOIN (SELECT DISTINCT product_id FROM raw_products) p USING (product_id)
WHERE p.product_id IS NULL;

-- detector: ORD-017
SELECT o.order_id AS business_key,
       o.order_id || '|' || o.currency || '|' || o.order_created_at || '|' || o.source_file || '|' || lpad(o.source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', o.order_id, 'currency', o.currency,
                   'candidate_fx_date', cast(try_cast(o.order_created_at AS TIMESTAMPTZ) AS DATE),
                   'source_file', o.source_file, 'source_row_number', o.source_row_number) AS sample_json
FROM raw_orders o
LEFT JOIN raw_fx_rates f ON o.currency = f.currency
 AND cast(try_cast(o.order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE)
     = try_cast(f.rate_date AS DATE)
WHERE o.currency IN ('JPY', 'USD') AND f.currency IS NULL
  AND regexp_full_match(o.order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$');

-- detector: ORD-018
WITH sequenced AS (
    SELECT *,
        lag(order_status) OVER (PARTITION BY order_id
          ORDER BY try_cast(updated_at AS TIMESTAMPTZ), batch_order, source_row_number) AS prior_status
    FROM raw_orders
)
SELECT order_id AS business_key,
       order_id || '|' || updated_at || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'prior_status', prior_status, 'order_status', order_status,
                   'updated_at', updated_at, 'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM sequenced
WHERE prior_status IN ('completed', 'cancelled') AND order_status IS DISTINCT FROM prior_status;

-- detector: ORD-019
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'member_id', member_id, 'product_id', product_id,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE NOT regexp_full_match(order_id, '^ORD[0-9]{8}$')
   OR NOT regexp_full_match(member_id, '^M[0-9]{6}$')
   OR NOT regexp_full_match(product_id, '^P[0-9]{5}$');

-- detector: ORD-020
WITH rated AS (
    SELECT o.*,
        CASE WHEN o.currency = 'TWD' THEN 1::DECIMAL(24,8)
             ELSE try_cast(f.rate_to_twd AS DECIMAL(24,8)) END AS candidate_rate
    FROM raw_orders o
    LEFT JOIN raw_fx_rates f ON o.currency = f.currency
     AND cast(try_cast(o.order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE)
         = try_cast(f.rate_date AS DATE)
)
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'currency', currency, 'amount', amount,
                   'candidate_rate_to_twd', candidate_rate::VARCHAR,
                   'coupon_discount_twd', coupon_discount,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM rated
WHERE candidate_rate IS NOT NULL
  AND regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
  AND try_cast(amount AS DECIMAL(24,4)) IS NOT NULL
  AND try_cast(amount AS DECIMAL(24,4)) > 0
  AND try_cast(coupon_discount AS DECIMAL(24,4)) IS NOT NULL
  AND try_cast(coupon_discount AS DECIMAL(24,4)) >= 0
  AND try_cast(coupon_discount AS DECIMAL(24,4))
      > try_cast(amount AS DECIMAL(24,4)) * candidate_rate;

-- detector: ORD-021
SELECT order_id AS business_key,
       source_file || '|' || order_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'order_created_at', order_created_at,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE (source_file = 'orders_base.csv'
       AND regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
       AND cast(try_cast(order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE)
           NOT BETWEEN DATE '2026-05-01' AND DATE '2026-06-30');

-- detector: ORD-022
SELECT order_id AS business_key,
       source_file || '|' || order_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'order_created_at', order_created_at,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE (source_file = 'orders_incremental_day1.csv'
       AND regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
       AND cast(try_cast(order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE) != DATE '2026-07-01')
   OR (source_file = 'orders_incremental_day2.csv'
       AND regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
       AND cast(try_cast(order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE) != DATE '2026-07-02')
   OR (source_file = 'orders_incremental_day3.csv'
       AND regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
       AND cast(try_cast(order_created_at AS TIMESTAMPTZ) AT TIME ZONE 'Asia/Taipei' AS DATE) != DATE '2026-07-03');

-- detector: ORD-023
WITH normalized AS (
    SELECT o.*,
        CASE
          WHEN regexp_full_match(o.order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
            THEN try_cast(o.order_created_at AS TIMESTAMPTZ)
          WHEN regexp_full_match(o.order_created_at, '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
            THEN try_cast(strptime(o.order_created_at, '%Y/%m/%d %H:%M:%S') AT TIME ZONE 'Asia/Taipei' AS TIMESTAMPTZ)
        END AS normalized_order_created_at,
        CASE WHEN o.currency = 'NTD' THEN 'TWD' ELSE o.currency END AS normalized_currency
    FROM raw_orders o
), valued AS (
    SELECT n.*,
        try_cast(n.amount AS DECIMAL(24,4))
          * CASE WHEN n.normalized_currency = 'TWD' THEN 1::DECIMAL(24,8)
                 ELSE try_cast(f.rate_to_twd AS DECIMAL(24,8)) END AS candidate_gross_twd,
        try_cast(p.base_price_twd AS DECIMAL(24,4))
          * try_cast(n.quantity AS INTEGER) AS candidate_base_total_twd
    FROM normalized n
    JOIN raw_products p USING (product_id)
    LEFT JOIN raw_fx_rates f ON n.normalized_currency = f.currency
     AND cast(n.normalized_order_created_at AT TIME ZONE 'Asia/Taipei' AS DATE)
         = try_cast(f.rate_date AS DATE)
    WHERE n.normalized_order_created_at IS NOT NULL
      AND n.normalized_currency IN ('TWD', 'JPY', 'USD')
      AND try_cast(n.amount AS DECIMAL(24,4)) > 0
      AND try_cast(n.quantity AS INTEGER) > 0
      AND try_cast(p.base_price_twd AS DECIMAL(24,4)) > 0
)
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'currency', currency,
                   'candidate_gross_twd', candidate_gross_twd::VARCHAR,
                   'candidate_base_total_twd', candidate_base_total_twd::VARCHAR,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM valued
WHERE candidate_gross_twd IS NOT NULL
  AND (candidate_gross_twd * 2 < candidate_base_total_twd
       OR candidate_gross_twd > candidate_base_total_twd * 2);

-- detector: ORD-024
SELECT order_id AS business_key,
       order_id || '|' || source_file || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('order_id', order_id, 'departure_date', departure_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_orders
WHERE try_cast(departure_date AS DATE) IS NULL
   OR NOT regexp_full_match(departure_date, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$');

-- detector: MEM-001
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY member_id, member_name, member_level, city,
        birth_date, register_date, extract_date) AS copies FROM raw_members
)
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'extract_date', extract_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM marked WHERE copies > 1;

-- detector: MEM-002
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY member_id, extract_date) AS snapshot_count FROM raw_members
)
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'extract_date', extract_date,
                   'snapshot_count', snapshot_count, 'source_file', source_file,
                   'source_row_number', source_row_number) AS sample_json
FROM marked WHERE snapshot_count > 1;

-- detector: MEM-003
WITH marked AS (
    SELECT *, count(DISTINCT md5(concat_ws(chr(31), member_name, member_level, city,
        birth_date, register_date))) OVER (PARTITION BY member_id, extract_date) AS payload_count
    FROM raw_members
)
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'extract_date', extract_date, 'member_level', member_level,
                   'city', city, 'birth_date_present', birth_date IS NOT NULL AND trim(birth_date) != '',
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM marked WHERE payload_count > 1;

-- detector: MEM-004
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'extract_date', extract_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_members WHERE NOT regexp_full_match(member_id, '^M[0-9]{6}$');

-- detector: MEM-005
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'member_level', member_level, 'extract_date', extract_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_members WHERE member_level NOT IN ('一般', '銀卡', '金卡', '白金');

-- detector: MEM-006
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'birth_date_present', birth_date IS NOT NULL AND trim(birth_date) != '',
                   'register_date', register_date, 'extract_date', extract_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_members
WHERE (birth_date IS NOT NULL AND trim(birth_date) != '' AND try_cast(birth_date AS DATE) IS NULL)
   OR try_cast(register_date AS DATE) IS NULL OR try_cast(extract_date AS DATE) IS NULL;

-- detector: MEM-007
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'register_date', register_date, 'extract_date', extract_date,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_members
WHERE try_cast(register_date AS DATE) > try_cast(extract_date AS DATE)
   OR (try_cast(birth_date AS DATE) IS NOT NULL
       AND try_cast(birth_date AS DATE) > try_cast(register_date AS DATE));

-- detector: MEM-008
WITH sequenced AS (
    SELECT *, row_number() OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS seq,
        lag(member_name IS NULL OR trim(member_name) = '') OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS prior_name_null,
        lag(member_level IS NULL OR trim(member_level) = '') OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS prior_level_null,
        lag(city IS NULL OR trim(city) = '') OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS prior_city_null,
        lag(birth_date IS NULL OR trim(birth_date) = '') OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS prior_birth_null
    FROM raw_members
)
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'extract_date', extract_date,
                   'name_null_transition', (member_name IS NULL OR trim(member_name) = '') != prior_name_null,
                   'level_null_transition', (member_level IS NULL OR trim(member_level) = '') != prior_level_null,
                   'city_null_transition', (city IS NULL OR trim(city) = '') != prior_city_null,
                   'birth_date_null_transition', (birth_date IS NULL OR trim(birth_date) = '') != prior_birth_null,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM sequenced
WHERE seq > 1 AND ((member_name IS NULL OR trim(member_name) = '') != prior_name_null
   OR (member_level IS NULL OR trim(member_level) = '') != prior_level_null
   OR (city IS NULL OR trim(city) = '') != prior_city_null
   OR (birth_date IS NULL OR trim(birth_date) = '') != prior_birth_null);

-- detector: MEM-009
WITH bad_keys AS (
    SELECT member_id
    FROM raw_members
    GROUP BY member_id
    HAVING count(DISTINCT CASE WHEN birth_date != '1900-01-01' THEN birth_date END) >= 2
), member_stats AS (
    SELECT member_id,
           count(DISTINCT CASE WHEN birth_date != '1900-01-01' THEN birth_date END)
             AS non_sentinel_birth_date_count
    FROM raw_members
    GROUP BY member_id
)
SELECT m.member_id AS business_key,
       m.member_id || '|' || m.extract_date || '|' || lpad(m.source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', m.member_id, 'extract_date', m.extract_date,
                   'birth_date_sentinel', m.birth_date = '1900-01-01',
                   'non_sentinel_birth_date_count', s.non_sentinel_birth_date_count,
                   'source_file', m.source_file, 'source_row_number', m.source_row_number) AS sample_json
FROM raw_members m
JOIN bad_keys b USING (member_id)
JOIN member_stats s USING (member_id);

-- detector: MEM-010
WITH sequenced AS (
    SELECT *,
        lag(member_level) OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS prior_level,
        lag(city) OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS prior_city,
        row_number() OVER (PARTITION BY member_id ORDER BY try_cast(extract_date AS DATE), source_row_number) AS seq
    FROM raw_members
)
SELECT member_id AS business_key,
       member_id || '|' || extract_date || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', member_id, 'extract_date', extract_date,
                   'prior_level', prior_level, 'member_level', member_level,
                   'prior_city', prior_city, 'city', city,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM sequenced
WHERE seq > 1
  AND (member_level IS DISTINCT FROM prior_level OR city IS DISTINCT FROM prior_city);

-- detector: MEM-011
WITH member_stats AS (
    SELECT member_id,
           count(DISTINCT CASE WHEN birth_date != '1900-01-01' THEN birth_date END)
             AS non_sentinel_birth_date_count
    FROM raw_members
    GROUP BY member_id
)
SELECT m.member_id AS business_key,
       m.member_id || '|' || m.extract_date || '|' || lpad(m.source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('member_id', m.member_id, 'extract_date', m.extract_date,
                   'birth_date_sentinel', true,
                   'non_sentinel_birth_date_count', s.non_sentinel_birth_date_count,
                   'source_file', m.source_file, 'source_row_number', m.source_row_number) AS sample_json
FROM raw_members m
JOIN member_stats s USING (member_id)
WHERE m.birth_date = '1900-01-01';

-- detector: PROD-001
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY product_id, product_name, product_type, destination_country,
        destination_city, trip_days, base_price_twd, is_active) AS copies FROM raw_products
)
SELECT product_id AS business_key,
       product_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('product_id', product_id, 'source_file', source_file,
                   'source_row_number', source_row_number) AS sample_json
FROM marked WHERE copies > 1;

-- detector: PROD-002
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY product_id) AS key_count FROM raw_products
)
SELECT product_id AS business_key,
       product_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('product_id', product_id, 'key_count', key_count,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM marked WHERE key_count > 1;

-- detector: PROD-003
SELECT product_id AS business_key,
       product_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('product_id', product_id, 'source_file', source_file,
                   'source_row_number', source_row_number) AS sample_json
FROM raw_products WHERE NOT regexp_full_match(product_id, '^P[0-9]{5}$');

-- detector: PROD-004
SELECT product_id AS business_key,
       product_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('product_id', product_id,
                   'product_name_blank', product_name IS NULL OR trim(product_name) = '',
                   'product_type_blank', product_type IS NULL OR trim(product_type) = '',
                   'country_blank', destination_country IS NULL OR trim(destination_country) = '',
                   'city_blank', destination_city IS NULL OR trim(destination_city) = '',
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_products
WHERE product_name IS NULL OR trim(product_name) = '' OR product_type IS NULL OR trim(product_type) = ''
   OR destination_country IS NULL OR trim(destination_country) = ''
   OR destination_city IS NULL OR trim(destination_city) = '';

-- detector: PROD-005
SELECT product_id AS business_key,
       product_id || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('product_id', product_id, 'trip_days', trip_days,
                   'base_price_twd', base_price_twd, 'is_active', is_active,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_products
WHERE try_cast(trip_days AS INTEGER) IS NULL OR try_cast(trip_days AS INTEGER) <= 0
   OR try_cast(base_price_twd AS DECIMAL(24,4)) IS NULL OR try_cast(base_price_twd AS DECIMAL(24,4)) <= 0
   OR is_active NOT IN ('N', 'Y');

-- detector: PROD-006
WITH marked AS (
    SELECT *, count(DISTINCT product_id) OVER (PARTITION BY product_name, product_type,
        destination_country, destination_city, trip_days, base_price_twd, is_active) AS key_count
    FROM raw_products
)
SELECT product_id AS business_key,
       product_name || '|' || product_id AS sample_sort_key,
       json_object('product_id', product_id, 'product_type', product_type,
                   'destination_country', destination_country, 'destination_city', destination_city,
                   'trip_days', trip_days, 'base_price_twd', base_price_twd,
                   'is_active', is_active, 'source_file', source_file,
                   'source_row_number', source_row_number) AS sample_json
FROM marked WHERE key_count > 1;

-- detector: FX-001
WITH marked AS (
    SELECT *, count(*) OVER (PARTITION BY rate_date, currency) AS key_count FROM raw_fx_rates
)
SELECT concat_ws('|', rate_date, currency) AS business_key,
       rate_date || '|' || currency || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('rate_date', rate_date, 'currency', currency, 'rate_to_twd', rate_to_twd,
                   'key_count', key_count, 'source_file', source_file,
                   'source_row_number', source_row_number) AS sample_json
FROM marked WHERE key_count > 1;

-- detector: FX-002
WITH marked AS (
    SELECT *, count(DISTINCT rate_to_twd) OVER (PARTITION BY rate_date, currency) AS rate_count
    FROM raw_fx_rates
)
SELECT concat_ws('|', rate_date, currency) AS business_key,
       rate_date || '|' || currency || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('rate_date', rate_date, 'currency', currency, 'rate_to_twd', rate_to_twd,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM marked WHERE rate_count > 1;

-- detector: FX-003
SELECT concat_ws('|', rate_date, currency) AS business_key,
       rate_date || '|' || currency || '|' || lpad(source_row_number::VARCHAR, 12, '0') AS sample_sort_key,
       json_object('rate_date', rate_date, 'currency', currency, 'rate_to_twd', rate_to_twd,
                   'source_file', source_file, 'source_row_number', source_row_number) AS sample_json
FROM raw_fx_rates
WHERE try_cast(rate_date AS DATE) IS NULL OR currency NOT IN ('JPY', 'USD')
   OR try_cast(rate_to_twd AS DECIMAL(24,8)) IS NULL OR try_cast(rate_to_twd AS DECIMAL(24,8)) <= 0;

-- detector: FX-004
WITH boundaries AS (
    SELECT currency, min(try_cast(rate_date AS DATE)) AS min_date, max(try_cast(rate_date AS DATE)) AS max_date
    FROM raw_fx_rates WHERE try_cast(rate_date AS DATE) IS NOT NULL GROUP BY currency
), expected AS (
    SELECT currency, unnest(generate_series(min_date, max_date, INTERVAL 1 DAY))::DATE AS rate_date
    FROM boundaries
), missing AS (
    SELECT e.currency, e.rate_date
    FROM expected e LEFT JOIN raw_fx_rates f
      ON e.currency = f.currency AND e.rate_date = try_cast(f.rate_date AS DATE)
    WHERE f.currency IS NULL
)
SELECT currency || '|' || rate_date::VARCHAR AS business_key,
       currency || '|' || rate_date::VARCHAR AS sample_sort_key,
       json_object('currency', currency, 'missing_rate_date', rate_date) AS sample_json
FROM missing;

-- analysis: ORD-004-FIELD-BREAKDOWN
WITH conflict_keys AS (
    SELECT 'member_id' AS field_name, order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT member_id) > 1
    UNION ALL SELECT 'product_id', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT product_id) > 1
    UNION ALL SELECT 'channel', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT channel) > 1
    UNION ALL SELECT 'quantity', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT quantity) > 1
    UNION ALL SELECT 'currency', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT currency) > 1
    UNION ALL SELECT 'amount', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT amount) > 1
    UNION ALL SELECT 'coupon_discount', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT coupon_discount) > 1
    UNION ALL SELECT 'order_created_at', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT order_created_at) > 1
    UNION ALL SELECT 'departure_date', order_id FROM raw_orders GROUP BY order_id HAVING count(DISTINCT departure_date) > 1
)
SELECT c.field_name, o.order_id AS business_key, o.source_file, o.source_row_number,
       CASE c.field_name
         WHEN 'member_id' THEN o.member_id WHEN 'product_id' THEN o.product_id
         WHEN 'channel' THEN o.channel WHEN 'quantity' THEN o.quantity
         WHEN 'currency' THEN o.currency WHEN 'amount' THEN o.amount
         WHEN 'coupon_discount' THEN o.coupon_discount
         WHEN 'order_created_at' THEN o.order_created_at
         WHEN 'departure_date' THEN o.departure_date
       END AS field_value
FROM raw_orders o JOIN conflict_keys c USING (order_id);

-- analysis: MEM-009-IDENTITY-BREAKDOWN
WITH conflict_keys AS (
    SELECT 'member_name' AS field_name, member_id
    FROM raw_members GROUP BY member_id HAVING count(DISTINCT member_name) > 1
    UNION ALL
    SELECT 'birth_date', member_id
    FROM raw_members GROUP BY member_id HAVING count(DISTINCT birth_date) > 1
    UNION ALL
    SELECT 'register_date', member_id
    FROM raw_members GROUP BY member_id HAVING count(DISTINCT register_date) > 1
)
SELECT c.field_name, m.member_id AS business_key, m.source_file, m.source_row_number,
       m.extract_date, CASE c.field_name
         WHEN 'member_name' THEN m.member_name IS NOT NULL AND trim(m.member_name) != ''
         WHEN 'birth_date' THEN m.birth_date IS NOT NULL AND trim(m.birth_date) != ''
         WHEN 'register_date' THEN m.register_date IS NOT NULL AND trim(m.register_date) != ''
       END AS value_present
FROM raw_members m JOIN conflict_keys c USING (member_id);

-- analysis: MEM-BIRTH-DATE-SEMANTICS
WITH member_stats AS (
    SELECT member_id,
           count(DISTINCT birth_date) AS raw_birth_date_count,
           count(*) FILTER (WHERE birth_date = '1900-01-01') > 0 AS has_sentinel,
           count(DISTINCT CASE WHEN birth_date != '1900-01-01' THEN birth_date END)
             AS non_sentinel_birth_date_count
    FROM raw_members
    GROUP BY member_id
)
SELECT m.member_id, m.source_file, m.source_row_number, m.extract_date,
       m.birth_date = '1900-01-01' AS birth_date_sentinel,
       s.raw_birth_date_count, s.has_sentinel, s.non_sentinel_birth_date_count,
       CASE WHEN m.birth_date != '1900-01-01' THEN try_cast(m.birth_date AS DATE) END
         AS non_sentinel_birth_date
FROM raw_members m
JOIN member_stats s USING (member_id);

-- analysis: ORD-001-EXACT-DUPLICATE-POLICY
SELECT order_id, updated_at,
       count(*)::BIGINT AS raw_duplicate_count,
       1::BIGINT AS canonical_event_count,
       count(*)::BIGINT - 1 AS duplicate_loser_count
FROM raw_orders
GROUP BY order_id, member_id, product_id, channel, order_status, quantity, currency,
         amount, coupon_discount, order_created_at, departure_date, updated_at
HAVING count(*) > 1;

-- analysis: ORD-012-TIMESTAMP-BREAKDOWN
SELECT 'order_created_at' AS field_name, order_id AS business_key, source_file,
       source_row_number, order_created_at AS raw_value,
       CASE
         WHEN regexp_full_match(order_created_at, '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
           THEN 'YYYY/MM/DD HH:MM:SS'
         ELSE 'OTHER'
       END AS observed_raw_format
FROM raw_orders
WHERE NOT regexp_full_match(order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
UNION ALL
SELECT 'updated_at', order_id, source_file, source_row_number, updated_at,
       CASE
         WHEN regexp_full_match(updated_at, '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
           THEN 'YYYY/MM/DD HH:MM:SS'
         ELSE 'OTHER'
       END
FROM raw_orders
WHERE NOT regexp_full_match(updated_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$');

-- analysis: ORD-018-TRANSITION-PAIRS
WITH sequenced AS (
    SELECT *,
        lag(order_status) OVER (PARTITION BY order_id
          ORDER BY try_cast(updated_at AS TIMESTAMPTZ), batch_order, source_row_number) AS from_status,
        row_number() OVER (PARTITION BY order_id
          ORDER BY try_cast(updated_at AS TIMESTAMPTZ), batch_order, source_row_number) AS event_sequence
    FROM raw_orders
)
SELECT from_status, order_status AS to_status, order_id AS business_key, updated_at,
       source_file, source_row_number
FROM sequenced WHERE event_sequence > 1;

-- analysis: ORD-AMOUNT-SEMANTICS
WITH normalized AS (
    SELECT o.*,
        CASE
          WHEN regexp_full_match(o.order_created_at, '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})$')
            THEN try_cast(o.order_created_at AS TIMESTAMPTZ)
          WHEN regexp_full_match(o.order_created_at, '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
            THEN try_cast(strptime(o.order_created_at, '%Y/%m/%d %H:%M:%S') AT TIME ZONE 'Asia/Taipei' AS TIMESTAMPTZ)
        END AS normalized_order_created_at,
        CASE WHEN o.currency = 'NTD' THEN 'TWD' ELSE o.currency END AS normalized_currency
    FROM raw_orders o
), valued AS (
    SELECT n.*,
        try_cast(n.amount AS DECIMAL(24,4))
          * CASE WHEN n.normalized_currency = 'TWD' THEN 1::DECIMAL(24,8)
                 ELSE try_cast(f.rate_to_twd AS DECIMAL(24,8)) END AS amount_twd,
        try_cast(p.base_price_twd AS DECIMAL(24,4)) AS base_price_twd_decimal
    FROM normalized n
    JOIN raw_products p USING (product_id)
    LEFT JOIN raw_fx_rates f ON n.normalized_currency = f.currency
     AND cast(n.normalized_order_created_at AT TIME ZONE 'Asia/Taipei' AS DATE)
         = try_cast(f.rate_date AS DATE)
    WHERE n.normalized_order_created_at IS NOT NULL
      AND n.normalized_currency IN ('TWD', 'JPY', 'USD')
      AND try_cast(n.amount AS DECIMAL(24,4)) > 0
      AND try_cast(n.quantity AS INTEGER) > 0
      AND try_cast(p.base_price_twd AS DECIMAL(24,4)) > 0
), ratios AS (
    SELECT *,
        cast(amount_twd / base_price_twd_decimal AS DECIMAL(38,8)) AS ratio_to_unit_price,
        cast(amount_twd / (base_price_twd_decimal * try_cast(quantity AS INTEGER)) AS DECIMAL(38,8))
          AS ratio_to_quantity_total
    FROM valued WHERE amount_twd IS NOT NULL
), expanded AS (
    SELECT 'amount_twd/base_price_twd' AS comparison_basis, order_id, ratio_to_unit_price AS ratio FROM ratios
    UNION ALL
    SELECT 'amount_twd/(base_price_twd*quantity)', order_id, ratio_to_quantity_total FROM ratios
)
SELECT comparison_basis, count(*)::BIGINT AS eligible_row_count,
       count(DISTINCT order_id)::BIGINT AS eligible_order_count,
       min(ratio) AS minimum_ratio, quantile_cont(ratio, 0.01) AS p01_ratio,
       median(ratio) AS median_ratio, quantile_cont(ratio, 0.50) AS p50_ratio,
       quantile_cont(ratio, 0.99) AS p99_ratio, max(ratio) AS maximum_ratio,
       count(*) FILTER (WHERE ratio < 0.5 OR ratio > 2)::BIGINT AS extreme_row_count,
       count(DISTINCT order_id) FILTER (WHERE ratio < 0.5 OR ratio > 2)::BIGINT
         AS extreme_order_count
FROM expanded GROUP BY comparison_basis;
