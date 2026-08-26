CREATE OR REPLACE TEMP TABLE desired_fact_order AS
WITH eligible AS (
    SELECT o.*
    FROM staging.order_event o JOIN quality.entity_disposition d
      ON d.entity_type='order' AND d.business_key=o.order_id AND d.is_curated_eligible
    WHERE o.is_canonical_event
), latest AS (
    SELECT *,row_number() OVER (
        PARTITION BY order_id ORDER BY updated_at DESC,canonical_event_hash
    ) AS latest_rank
    FROM eligible
), warning_flags AS (
    SELECT business_key AS order_id,
           bool_or(rule_id='ORD-018') status_transition_warning
    FROM quality.entity_rule WHERE entity_type='order' GROUP BY business_key
), duplicate_counts AS (
    SELECT order_id,count(*)-count(DISTINCT canonical_event_hash) duplicate_count
    FROM staging.order_event GROUP BY order_id
)
SELECT l.order_id,coalesce(m.member_sk,0) member_sk,coalesce(p.product_sk,0) product_sk,
       l.member_id,l.product_id,
       strftime(l.order_business_date,'%Y%m%d')::INTEGER order_date_sk,
       strftime(l.departure_date,'%Y%m%d')::INTEGER departure_date_sk,
       strftime(l.updated_business_date,'%Y%m%d')::INTEGER updated_date_sk,
       strftime(l.order_business_date,'%Y%m%d')::INTEGER fx_date_sk,
       l.channel,l.order_status,l.quantity,l.raw_currency original_currency,
       l.normalized_currency,l.original_amount,l.coupon_discount_twd_source,l.rate_to_twd,
       l.gross_amount_twd_exact,l.net_amount_twd_exact,
       cast(round(l.gross_amount_twd_exact,2) AS DECIMAL(28,2)) gross_amount_twd,
       cast(round(l.net_amount_twd_exact,2) AS DECIMAL(28,2)) net_amount_twd,
       l.order_created_at,l.departure_date,l.updated_at,
       p.product_sk IS NULL missing_product,p.product_sk IS NULL price_check_not_evaluable,
       m.member_sk IS NULL missing_member_asof,l.currency_normalized,l.timezone_assumed,
       coalesce(w.status_transition_warning,false) status_transition_warning,
       coalesce(dc.duplicate_count,0) duplicate_source_row_count,
       l.source_file,l.source_row_number,l.batch_order,l.source_row_uid,l.row_hash
FROM latest l
LEFT JOIN curated.dim_product p ON p.product_id=l.product_id AND NOT p.is_unknown
LEFT JOIN curated.dim_member m ON m.member_id=l.member_id AND NOT m.is_unknown
  AND m.valid_from<=l.order_business_date AND l.order_business_date<m.valid_to
LEFT JOIN warning_flags w USING (order_id)
LEFT JOIN duplicate_counts dc USING (order_id)
WHERE l.latest_rank=1;

DELETE FROM curated.fact_order f
WHERE NOT EXISTS (SELECT 1 FROM desired_fact_order d WHERE d.order_id=f.order_id);

INSERT OR REPLACE INTO curated.fact_order BY NAME
SELECT * FROM desired_fact_order;
