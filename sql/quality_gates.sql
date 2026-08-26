-- Phase 2 treatment application. Rule IDs intentionally match Phase 1 profiling IDs.
INSERT INTO quality.issue_hit
WITH canonical_orders AS (
    SELECT * FROM staging.order_event WHERE is_canonical_event
), same_time_conflict AS (
    SELECT order_id, updated_at
    FROM canonical_orders
    GROUP BY order_id, updated_at
    HAVING count(DISTINCT canonical_event_hash) > 1
), invariant_conflict AS (
    SELECT order_id FROM canonical_orders GROUP BY order_id
    HAVING count(DISTINCT invariant_hash) > 1
), latest_time AS (
    SELECT order_id, max(updated_at) AS updated_at FROM canonical_orders GROUP BY order_id
), latest_tie AS (
    SELECT o.order_id FROM canonical_orders o JOIN latest_time l USING (order_id, updated_at)
    GROUP BY o.order_id HAVING count(*) > 1
), sequenced AS (
    SELECT *, lag(order_status) OVER (
        PARTITION BY order_id ORDER BY updated_at,canonical_event_hash
    ) AS prior_status
    FROM canonical_orders
), late_arrival AS (
    SELECT o.source_row_uid
    FROM canonical_orders o
    WHERE o.batch_order > 0
      AND o.updated_at < (
          SELECT max(p.updated_at)
          FROM canonical_orders p
          WHERE p.order_id=o.order_id AND p.batch_order<o.batch_order
      )
), order_hits AS (
    SELECT 'orders' dataset, 'order' entity_type, order_id business_key, source_row_uid,
           'ORD-001' rule_id, 'NORMALIZE' disposition
    FROM staging.order_event WHERE duplicate_source_row_count > 1
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'ORD-003','QUARANTINE'
    FROM staging.order_event o JOIN same_time_conflict c USING (order_id, updated_at)
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'ORD-004','QUARANTINE'
    FROM staging.order_event o JOIN invariant_conflict c USING (order_id)
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'ORD-005','QUARANTINE'
    FROM staging.order_event o JOIN latest_tie c USING (order_id)
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-006','QUARANTINE'
    FROM staging.order_event WHERE order_status IS NULL
       OR order_status NOT IN ('created','paid','completed','cancelled')
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-007','QUARANTINE'
    FROM staging.order_event WHERE channel IS NULL OR channel NOT IN ('app','web','門市','電銷')
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-008','QUARANTINE'
    FROM staging.order_event WHERE quantity IS NULL OR quantity <= 0
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-009','NORMALIZE'
    FROM staging.order_event WHERE currency_normalized
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-010','QUARANTINE'
    FROM staging.order_event WHERE original_amount IS NULL OR original_amount <= 0
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-011','QUARANTINE'
    FROM staging.order_event
    WHERE coupon_discount_twd_source IS NULL OR coupon_discount_twd_source < 0
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-012','NORMALIZE'
    FROM staging.order_event WHERE timezone_assumed
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-013','QUARANTINE'
    FROM staging.order_event
    WHERE order_created_at IS NULL OR updated_at IS NULL OR updated_at < order_created_at
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-014','QUARANTINE'
    FROM staging.order_event
    WHERE departure_date IS NOT NULL AND order_business_date IS NOT NULL
      AND departure_date < order_business_date
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'ORD-015','ACCEPT'
    FROM staging.order_event o
    LEFT JOIN (SELECT DISTINCT member_id FROM staging.member_snapshot) m USING (member_id)
    WHERE m.member_id IS NULL
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'ORD-016','ACCEPT'
    FROM staging.order_event o LEFT JOIN staging.product p USING (product_id)
    WHERE p.product_id IS NULL
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-017','QUARANTINE'
    FROM staging.order_event
    WHERE normalized_currency NOT IN ('TWD','USD','JPY')
       OR (normalized_currency IN ('USD','JPY') AND rate_to_twd IS NULL)
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-018','ACCEPT'
    FROM sequenced
    WHERE prior_status IN ('completed','cancelled') AND order_status <> prior_status
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-019','QUARANTINE'
    FROM staging.order_event
    WHERE order_id IS NULL OR NOT regexp_full_match(order_id, '^ORD[0-9]{8}$')
       OR member_id IS NULL OR NOT regexp_full_match(member_id, '^M[0-9]{6}$')
       OR product_id IS NULL OR NOT regexp_full_match(product_id, '^P[0-9]{5}$')
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-020','QUARANTINE'
    FROM staging.order_event
    WHERE original_amount > 0 AND coupon_discount_twd_source >= 0
      AND net_amount_twd_exact < 0
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-021','QUARANTINE'
    FROM staging.order_event o
    JOIN (VALUES
        (0,'orders_base.csv',DATE '2026-05-01',DATE '2026-06-30'),
        (1,'orders_incremental_day1.csv',DATE '2026-05-01',DATE '2026-07-01'),
        (2,'orders_incremental_day2.csv',DATE '2026-05-01',DATE '2026-07-02'),
        (3,'orders_incremental_day3.csv',DATE '2026-05-01',DATE '2026-07-03')
    ) AS c(batch_order,source_file,min_business_date,max_business_date)
      ON c.batch_order=o.batch_order AND c.source_file=o.source_file
    WHERE o.order_business_date IS NULL
       OR o.order_business_date NOT BETWEEN c.min_business_date AND c.max_business_date
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'ORD-023','QUARANTINE'
    FROM staging.order_event o JOIN staging.product p USING (product_id)
    WHERE o.original_amount > 0 AND o.gross_amount_twd_exact IS NOT NULL
      AND o.quantity > 0 AND p.base_price_twd > 0
      AND (o.gross_amount_twd_exact / (p.base_price_twd * o.quantity) < 0.5
        OR o.gross_amount_twd_exact / (p.base_price_twd * o.quantity) > 2.0)
    UNION ALL
    SELECT 'orders','order',order_id,source_row_uid,'ORD-024','QUARANTINE'
    FROM staging.order_event WHERE departure_date IS NULL
    UNION ALL
    SELECT 'orders','order',o.order_id,o.source_row_uid,'INC-001','WARN'
    FROM staging.order_event o JOIN late_arrival l USING(source_row_uid)
), member_hits AS (
    SELECT 'members' dataset, 'member_snapshot' entity_type,
           member_id || '|' || coalesce(extract_date::VARCHAR, '<NULL>') business_key,
           source_row_uid, 'MEM-001' rule_id, 'NORMALIZE' disposition
    FROM staging.member_snapshot WHERE identical_snapshot_count > 1
    UNION ALL
    SELECT 'members','member_snapshot',
           member_id || '|' || coalesce(extract_date::VARCHAR, '<NULL>'),
           source_row_uid,'MEM-003','QUARANTINE'
    FROM staging.member_snapshot WHERE same_day_payload_count > 1
    UNION ALL
    SELECT 'members','member',member_id,source_row_uid,'MEM-009','QUARANTINE'
    FROM staging.member_snapshot WHERE birth_date_identity_ambiguous
    UNION ALL
    SELECT 'members','member',member_id,source_row_uid,'MEM-011','NORMALIZE'
    FROM staging.member_snapshot WHERE birth_date_sentinel
    UNION ALL
    SELECT 'members','member_snapshot',member_id || '|' || coalesce(extract_date::VARCHAR,'<NULL>'),
           source_row_uid,'MEM-004','QUARANTINE'
    FROM staging.member_snapshot
    WHERE member_id IS NULL OR NOT regexp_full_match(member_id,'^M[0-9]{6}$')
    UNION ALL
    SELECT 'members','member_snapshot',member_id || '|' || coalesce(extract_date::VARCHAR,'<NULL>'),
           source_row_uid,'MEM-005','QUARANTINE'
    FROM staging.member_snapshot WHERE member_level IS NULL
       OR member_level NOT IN ('一般','銀卡','金卡','白金')
    UNION ALL
    SELECT 'members','member_snapshot',member_id || '|' || coalesce(extract_date::VARCHAR,'<NULL>'),
           source_row_uid,'MEM-006','QUARANTINE'
    FROM staging.member_snapshot
    WHERE extract_date IS NULL OR register_date IS NULL
       OR (raw_birth_date IS NOT NULL AND trim(raw_birth_date) <> ''
           AND try_cast(raw_birth_date AS DATE) IS NULL)
    UNION ALL
    SELECT 'members','member_snapshot',member_id || '|' || extract_date::VARCHAR,
           source_row_uid,'MEM-007','QUARANTINE'
    FROM staging.member_snapshot
    WHERE register_date > extract_date
       OR (canonical_birth_date IS NOT NULL AND canonical_birth_date >= register_date)
), product_hits AS (
    SELECT 'products' dataset,'product' entity_type,coalesce(product_id,'<NULL>') business_key,
           source_row_uid,'PROD-002' rule_id,'QUARANTINE' disposition
    FROM staging.product QUALIFY count(*) OVER (PARTITION BY product_id) > 1
    UNION ALL
    SELECT 'products','product',coalesce(product_id,'<NULL>'),source_row_uid,
           'PROD-003','QUARANTINE' FROM staging.product
    WHERE product_id IS NULL OR NOT regexp_full_match(product_id,'^P[0-9]{5}$')
    UNION ALL
    SELECT 'products','product',coalesce(product_id,'<NULL>'),source_row_uid,
           'PROD-004','QUARANTINE' FROM staging.product
    WHERE product_name IS NULL OR product_type IS NULL OR destination_country IS NULL
       OR destination_city IS NULL
    UNION ALL
    SELECT 'products','product',coalesce(product_id,'<NULL>'),source_row_uid,
           'PROD-005','QUARANTINE' FROM staging.product
    WHERE trip_days IS NULL OR trip_days <= 0 OR base_price_twd IS NULL OR base_price_twd <= 0
       OR is_active NOT IN ('Y','N')
), fx_hits AS (
    SELECT 'fx_rates' dataset,'fx_rate' entity_type,
           coalesce(rate_date::VARCHAR,'<NULL>') || '|' || coalesce(currency,'<NULL>'),
           source_row_uid,'FX-001' rule_id,'QUARANTINE' disposition
    FROM staging.fx_rate QUALIFY count(*) OVER (PARTITION BY rate_date,currency) > 1
    UNION ALL
    SELECT 'fx_rates','fx_rate',
           coalesce(rate_date::VARCHAR,'<NULL>') || '|' || coalesce(currency,'<NULL>'),
           source_row_uid,'FX-003','QUARANTINE' FROM staging.fx_rate
    WHERE rate_date IS NULL OR currency NOT IN ('USD','JPY')
       OR rate_to_twd IS NULL OR rate_to_twd <= 0
)
SELECT DISTINCT * FROM (
    SELECT * FROM order_hits UNION ALL SELECT * FROM member_hits
    UNION ALL SELECT * FROM product_hits UNION ALL SELECT * FROM fx_hits
);

INSERT INTO quality.entity_rule
SELECT entity_type, business_key, rule_id, max(disposition), count(DISTINCT source_row_uid)
FROM quality.issue_hit
GROUP BY entity_type, business_key, rule_id;

INSERT INTO quality.entity_disposition
WITH all_entities AS (
    SELECT 'order' entity_type, order_id business_key FROM staging.order_event GROUP BY order_id
    UNION ALL SELECT 'member', member_id FROM staging.member_snapshot GROUP BY member_id
    UNION ALL SELECT 'member_snapshot', member_id || '|' || coalesce(extract_date::VARCHAR,'<NULL>')
        FROM staging.member_snapshot GROUP BY member_id,extract_date
    UNION ALL SELECT 'product', coalesce(product_id,'<NULL>') FROM staging.product GROUP BY product_id
    UNION ALL SELECT 'fx_rate', coalesce(rate_date::VARCHAR,'<NULL>') || '|' || coalesce(currency,'<NULL>')
        FROM staging.fx_rate GROUP BY rate_date,currency
), summarized AS (
    SELECT a.entity_type,a.business_key,count(r.rule_id) matched_rule_count,
           count(r.rule_id) FILTER (WHERE r.disposition='QUARANTINE') quarantine_rule_count
    FROM all_entities a LEFT JOIN quality.entity_rule r USING (entity_type,business_key)
    GROUP BY a.entity_type,a.business_key
)
SELECT entity_type,business_key,
       CASE WHEN quarantine_rule_count>0 THEN 'QUARANTINE'
            WHEN matched_rule_count>0 THEN 'ACCEPT_WITH_FLAGS' ELSE 'ACCEPT' END,
       quarantine_rule_count=0,matched_rule_count,quarantine_rule_count
FROM summarized;

INSERT INTO quality.quarantine_row
WITH candidates AS (
    SELECT 'orders' dataset,d.entity_type,d.business_key,r.source_row_uid,r.source_file,
           r.source_row_number FROM quality.entity_disposition d
    JOIN raw.order_event r ON d.entity_type='order' AND d.business_key=r.order_id
    WHERE NOT d.is_curated_eligible
    UNION ALL
    SELECT 'members',d.entity_type,d.business_key,r.source_row_uid,r.source_file,r.source_row_number
    FROM quality.entity_disposition d JOIN raw.member_snapshot r
      ON (d.entity_type='member' AND d.business_key=r.member_id)
      OR (d.entity_type='member_snapshot'
          AND d.business_key=r.member_id || '|' || coalesce(r.extract_date,'<NULL>'))
    WHERE NOT d.is_curated_eligible
    UNION ALL
    SELECT 'products',d.entity_type,d.business_key,r.source_row_uid,r.source_file,r.source_row_number
    FROM quality.entity_disposition d JOIN raw.product r
      ON d.entity_type='product' AND d.business_key=coalesce(r.product_id,'<NULL>')
    WHERE NOT d.is_curated_eligible
    UNION ALL
    SELECT 'fx_rates',d.entity_type,d.business_key,r.source_row_uid,r.source_file,r.source_row_number
    FROM quality.entity_disposition d JOIN raw.fx_rate r
      ON d.entity_type='fx_rate'
     AND d.business_key=coalesce(r.rate_date,'<NULL>') || '|' || coalesce(r.currency,'<NULL>')
    WHERE NOT d.is_curated_eligible
), deduped AS (
    SELECT dataset,min(entity_type) entity_type,string_agg(DISTINCT business_key,',' ORDER BY business_key)
               business_key,source_row_uid,source_file,source_row_number
    FROM candidates GROUP BY dataset,source_row_uid,source_file,source_row_number
)
SELECT d.*,
       coalesce((SELECT string_agg(DISTINCT h.rule_id,',' ORDER BY h.rule_id)
                 FROM quality.issue_hit h
                 WHERE h.source_row_uid=d.source_row_uid AND h.disposition='QUARANTINE'),
                (SELECT string_agg(DISTINCT r.rule_id,',' ORDER BY r.rule_id)
                 FROM quality.entity_rule r
                 WHERE d.dataset='orders' AND r.entity_type='order'
                   AND r.business_key=d.business_key AND r.disposition='QUARANTINE'),
                '<UNSPECIFIED>') rule_ids
FROM deduped d;
