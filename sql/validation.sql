DROP TABLE IF EXISTS quality.validation_result;
CREATE TABLE quality.validation_result (
    check_id VARCHAR PRIMARY KEY,
    violation_count BIGINT NOT NULL,
    detail VARCHAR NOT NULL
);

INSERT INTO quality.validation_result
SELECT * FROM (
    SELECT 'RAW_STAGING_ORDER_COUNT',abs(
        (SELECT count(*) FROM raw.order_event)-(SELECT count(*) FROM staging.order_event)),
        'raw.order_event and staging.order_event counts must reconcile'
    UNION ALL SELECT 'RAW_STAGING_MEMBER_COUNT',abs(
        (SELECT count(*) FROM raw.member_snapshot)-(SELECT count(*) FROM staging.member_snapshot)),
        'raw.member_snapshot and staging.member_snapshot counts must reconcile'
    UNION ALL SELECT 'RAW_STAGING_PRODUCT_COUNT',abs(
        (SELECT count(*) FROM raw.product)-(SELECT count(*) FROM staging.product)),
        'raw.product and staging.product counts must reconcile'
    UNION ALL SELECT 'RAW_STAGING_FX_COUNT',abs(
        (SELECT count(*) FROM raw.fx_rate)-(SELECT count(*) FROM staging.fx_rate)),
        'raw.fx_rate and staging.fx_rate counts must reconcile'
    UNION ALL SELECT 'SOURCE_FILE_ALLOWLIST',count(*),
        'warehouse may contain orders_base.csv, members.csv, products.csv and fx_rates.csv only'
        FROM (SELECT source_file FROM raw.order_event UNION ALL SELECT source_file FROM raw.member_snapshot
              UNION ALL SELECT source_file FROM raw.product UNION ALL SELECT source_file FROM raw.fx_rate)
        WHERE source_file NOT IN ('orders_base.csv','members.csv','products.csv','fx_rates.csv')
    UNION ALL SELECT 'FACT_ORDER_UNIQUENESS',count(*)-count(DISTINCT order_id),
        'fact grain is one row per accepted order_id' FROM curated.fact_order
    UNION ALL SELECT 'MEMBER_SK_COLLISION',count(*),
        'a known member_sk may map to only one member/version identity'
        FROM (SELECT member_sk FROM curated.dim_member WHERE member_sk<>0
              GROUP BY member_sk HAVING count(DISTINCT member_id || '|' || valid_from::VARCHAR)>1)
    UNION ALL SELECT 'PRODUCT_SK_COLLISION',count(*),
        'a known product_sk may map to only one product_id'
        FROM (SELECT product_sk FROM curated.dim_product WHERE product_sk<>0
              GROUP BY product_sk HAVING count(DISTINCT product_id)>1)
    UNION ALL SELECT 'KNOWN_SK_NONZERO',count(*),
        'known dimension members must not use reserved key zero'
        FROM (SELECT member_sk FROM curated.dim_member WHERE NOT is_unknown AND member_sk=0
              UNION ALL SELECT product_sk FROM curated.dim_product WHERE NOT is_unknown AND product_sk=0)
    UNION ALL SELECT 'UNKNOWN_MEMBER_CARDINALITY',abs(count(*)-1),
        'exactly one Unknown Member row is required'
        FROM curated.dim_member WHERE member_sk=0 AND is_unknown
    UNION ALL SELECT 'UNKNOWN_PRODUCT_CARDINALITY',abs(count(*)-1),
        'exactly one Unknown Product row is required'
        FROM curated.dim_product WHERE product_sk=0 AND is_unknown
    UNION ALL SELECT 'MEMBER_PERIOD_OVERLAP',count(*),
        'accepted member versions must not overlap'
        FROM curated.dim_member a JOIN curated.dim_member b
          ON a.member_id=b.member_id AND a.member_sk<b.member_sk
         AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to
        WHERE NOT a.is_unknown AND NOT b.is_unknown
    UNION ALL SELECT 'MEMBER_SINGLE_CURRENT',count(*),
        'each known member has at most one current version'
        FROM (SELECT member_id FROM curated.dim_member WHERE is_current AND NOT is_unknown
              GROUP BY member_id HAVING count(*)>1)
    UNION ALL SELECT 'MEMBER_VALIDITY_FLAGS',count(*),
        'validity must be nonempty, exclusive and current flag must match sentinel'
        FROM curated.dim_member WHERE NOT is_unknown AND
          (valid_from>=valid_to OR is_current<>(valid_to=DATE '9999-12-31'))
    UNION ALL SELECT 'FACT_MEMBER_ORPHAN',count(*),
        'every fact member_sk must resolve, including Unknown Member'
        FROM curated.fact_order f LEFT JOIN curated.dim_member d USING (member_sk)
        WHERE d.member_sk IS NULL
    UNION ALL SELECT 'FACT_PRODUCT_ORPHAN',count(*),
        'every fact product_sk must resolve, including Unknown Product'
        FROM curated.fact_order f LEFT JOIN curated.dim_product d USING (product_sk)
        WHERE d.product_sk IS NULL
    UNION ALL SELECT 'FACT_DATE_ORPHAN',count(*),
        'all fact role-playing date keys must resolve'
        FROM curated.fact_order f
        LEFT JOIN curated.dim_date od ON od.date_sk=f.order_date_sk
        LEFT JOIN curated.dim_date dd ON dd.date_sk=f.departure_date_sk
        LEFT JOIN curated.dim_date ud ON ud.date_sk=f.updated_date_sk
        LEFT JOIN curated.dim_date fd ON fd.date_sk=f.fx_date_sk
        WHERE od.date_sk IS NULL OR dd.date_sk IS NULL OR ud.date_sk IS NULL OR fd.date_sk IS NULL
    UNION ALL SELECT 'DATE_KEY_FORMAT',count(*),
        'date_sk must equal YYYYMMDD'
        FROM curated.dim_date WHERE date_sk<>strftime(calendar_date,'%Y%m%d')::INTEGER
    UNION ALL SELECT 'DATE_CONTINUITY',CASE WHEN count(*)=0 THEN 1
             ELSE abs(count(*)-(date_diff('day',min(calendar_date),max(calendar_date))+1)) END,
        'dim_date must be a nonempty continuous range'
        FROM curated.dim_date
    UNION ALL SELECT 'DATE_SENTINEL_EXCLUSION',count(*),
        'birth-date and SCD technical sentinels must not enter dim_date'
        FROM curated.dim_date WHERE calendar_date IN (DATE '1900-01-01',DATE '9999-12-31')
    UNION ALL SELECT 'MISSING_FX_LEAKAGE',count(*),
        'curated non-TWD facts require a dated FX rate'
        FROM curated.fact_order WHERE normalized_currency<>'TWD' AND rate_to_twd IS NULL
    UNION ALL SELECT 'UNSUPPORTED_CURRENCY_LEAKAGE',count(*),
        'curated facts support TWD, USD and JPY only'
        FROM curated.fact_order WHERE normalized_currency NOT IN ('TWD','USD','JPY')
    UNION ALL SELECT 'MONEY_EXACT_RECOMPUTE',count(*),
        'exact gross/net values must recompute with Decimal arithmetic'
        FROM curated.fact_order WHERE
          gross_amount_twd_exact<>cast(original_amount*rate_to_twd AS DECIMAL(38,12))
          OR net_amount_twd_exact<>cast(original_amount*rate_to_twd-coupon_discount_twd_source
                                        AS DECIMAL(38,12))
    UNION ALL SELECT 'MONEY_ROUND_RECOMPUTE',count(*),
        'reported gross/net must round exact intermediates to two decimals'
        FROM curated.fact_order WHERE
          gross_amount_twd<>cast(round(gross_amount_twd_exact,2) AS DECIMAL(28,2))
          OR net_amount_twd<>cast(round(net_amount_twd_exact,2) AS DECIMAL(28,2))
    UNION ALL SELECT 'UNKNOWN_PRODUCT_FLAG',count(*),
        'Unknown Product key and flags must agree'
        FROM curated.fact_order WHERE
          (product_sk=0)<>missing_product OR missing_product<>price_check_not_evaluable
    UNION ALL SELECT 'UNKNOWN_MEMBER_FLAG',count(*),
        'Unknown Member key and missing-as-of flag must agree'
        FROM curated.fact_order WHERE (member_sk=0)<>missing_member_asof
    UNION ALL SELECT 'QUARANTINE_ROW_DUPLICATE',count(*)-count(DISTINCT source_row_uid),
        'a quarantined source row appears once regardless of matched rule count'
        FROM quality.quarantine_row
    UNION ALL SELECT 'ORDER_CANONICAL_CONFLICT_RULE_RECONCILIATION',abs(
        (SELECT count(*) FROM (
          SELECT order_id FROM staging.order_event WHERE is_canonical_event GROUP BY order_id
          HAVING count(DISTINCT invariant_hash)>1
        ))-(SELECT count(*) FROM quality.entity_rule
              WHERE entity_type='order' AND rule_id='ORD-004')),
        'canonical invariant conflict entities must equal ORD-004 entity rules'
    UNION ALL SELECT 'ENTITY_DISPOSITION_SOURCE_GRAIN_RECONCILIATION',
        abs((SELECT count(*) FROM quality.entity_disposition)-(
          (SELECT count(DISTINCT order_id) FROM staging.order_event)+
          (SELECT count(*) FROM (
             SELECT member_id,extract_date FROM staging.member_snapshot GROUP BY member_id,extract_date
          ))+(SELECT count(DISTINCT member_id) FROM staging.member_snapshot)+
          (SELECT count(DISTINCT product_id) FROM staging.product)+
          (SELECT count(*) FROM (
             SELECT rate_date,currency FROM staging.fx_rate GROUP BY rate_date,currency
          )))),
        'entity dispositions must reconcile to each source entity grain exactly once'
    UNION ALL SELECT 'MEMBER_ACCEPTED_LINEAGE_RECONCILIATION',abs(
        (SELECT count(*) FROM curated.dim_member_lineage)-(
          SELECT count(*) FROM staging.member_snapshot s
          JOIN quality.entity_disposition m
            ON m.entity_type='member' AND m.business_key=s.member_id AND m.is_curated_eligible
          JOIN quality.entity_disposition d
            ON d.entity_type='member_snapshot'
           AND d.business_key=s.member_id || '|' || s.extract_date::VARCHAR
           AND d.is_curated_eligible
          WHERE s.same_day_payload_count=1
        )),
        'accepted reliable snapshot source rows must all appear in member lineage'
    UNION ALL SELECT 'TIMEZONE_ASSUMPTION_DISPOSITION_PARTITION',abs(
        (SELECT count(*) FROM staging.order_event WHERE timezone_assumed)-(
          SELECT count(*) FROM staging.order_event s JOIN quality.entity_disposition d
            ON d.entity_type='order' AND d.business_key=s.order_id
          WHERE s.timezone_assumed
        )),
        'every timezone-assumed source row must resolve to one order disposition'
    UNION ALL SELECT 'TIMEZONE_FACT_SELECTED_SOURCE_FLAG',count(*),
        'fact timezone flag must equal the selected source event flag'
        FROM curated.fact_order f JOIN staging.order_event s USING(source_row_uid)
        WHERE f.timezone_assumed IS DISTINCT FROM s.timezone_assumed
) checks;
