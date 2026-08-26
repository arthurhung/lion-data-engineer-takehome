INSERT INTO curated.dim_product VALUES
    (0, NULL, 'Unknown Product', 'Unknown', NULL, NULL, NULL, NULL, NULL, true,
     NULL, NULL, NULL, NULL);

INSERT INTO curated.dim_product
SELECT cast('0x' || substr(sha256('dim_product|v1|' || p.product_id),1,15) AS BIGINT),
       p.product_id,p.product_name,p.product_type,p.destination_country,p.destination_city,
       p.trip_days,p.base_price_twd,p.is_active='Y',false,
       p.source_file,p.source_row_number,p.source_row_uid,p.row_hash
FROM staging.product p
JOIN quality.entity_disposition d
  ON d.entity_type='product' AND d.business_key=p.product_id AND d.is_curated_eligible;

INSERT INTO curated.dim_member VALUES
    (0, '__UNKNOWN__', 'Unknown Member', 'Unknown', 'Unknown', NULL, NULL,
     false, true, false, DATE '0001-01-01', DATE '9999-12-31', true,
     sha256('member-state-v1|unknown'), true, NULL, NULL, NULL, NULL, NULL);

INSERT INTO curated.dim_member
WITH reliable AS (
    SELECT s.*
    FROM staging.member_snapshot s
    JOIN quality.entity_disposition md
      ON md.entity_type='member' AND md.business_key=s.member_id AND md.is_curated_eligible
    JOIN quality.entity_disposition sd
      ON sd.entity_type='member_snapshot'
     AND sd.business_key=s.member_id || '|' || s.extract_date::VARCHAR
     AND sd.is_curated_eligible
    WHERE s.is_canonical_snapshot AND s.same_day_payload_count=1
      AND s.member_id IS NOT NULL AND s.member_name IS NOT NULL
      AND s.member_level IN ('一般','銀卡','金卡','白金')
      AND s.city IS NOT NULL AND s.register_date IS NOT NULL AND s.extract_date IS NOT NULL
), conflicts AS (
    SELECT member_id,extract_date
    FROM staging.member_snapshot
    WHERE same_day_payload_count>1 AND extract_date IS NOT NULL
    GROUP BY member_id,extract_date
), timeline AS (
    SELECT member_id,extract_date,false is_conflict,member_name,member_level,city,
           canonical_birth_date,register_date,has_birth_date_sentinel,birth_date_unknown,
           birth_date_restatement,version_hash,source_file,source_row_number,source_row_uid,row_hash
    FROM reliable
    UNION ALL
    SELECT member_id,extract_date,true,NULL,NULL,NULL,NULL,NULL,false,false,false,NULL,
           NULL,NULL,NULL,NULL
    FROM conflicts
), compared AS (
    SELECT *,lag(is_conflict) OVER (PARTITION BY member_id ORDER BY extract_date) prior_conflict,
           lag(version_hash) OVER (PARTITION BY member_id ORDER BY extract_date) prior_version_hash,
           row_number() OVER (PARTITION BY member_id ORDER BY extract_date) timeline_sequence
    FROM timeline
), marked AS (
    SELECT *, NOT is_conflict AND (
        timeline_sequence=1 OR prior_conflict OR version_hash IS DISTINCT FROM prior_version_hash
    ) AS is_new_version
    FROM compared
), boundaries AS (
    SELECT *,lead(extract_date) OVER (PARTITION BY member_id ORDER BY extract_date) next_boundary
    FROM marked WHERE is_conflict OR is_new_version
)
SELECT cast('0x' || substr(sha256('dim_member|v1|' || member_id || '|' ||
                                 extract_date::VARCHAR),1,15) AS BIGINT),
       member_id,member_name,member_level,city,canonical_birth_date,register_date,
       has_birth_date_sentinel,birth_date_unknown,birth_date_restatement,
       extract_date,coalesce(next_boundary,DATE '9999-12-31'),
       next_boundary IS NULL,version_hash,false,extract_date,
       source_file,source_row_number,source_row_uid,row_hash
FROM boundaries WHERE is_new_version;

INSERT INTO curated.dim_member_lineage
SELECT d.member_sk,s.source_row_uid,s.source_file,s.source_row_number,s.extract_date,s.row_hash
FROM staging.member_snapshot s
JOIN quality.entity_disposition md
  ON md.entity_type='member' AND md.business_key=s.member_id AND md.is_curated_eligible
JOIN quality.entity_disposition sd
  ON sd.entity_type='member_snapshot'
 AND sd.business_key=s.member_id || '|' || s.extract_date::VARCHAR
 AND sd.is_curated_eligible
JOIN curated.dim_member d
  ON d.member_id=s.member_id AND d.member_sk<>0
 AND d.valid_from<=s.extract_date AND s.extract_date<d.valid_to
WHERE s.same_day_payload_count=1;

INSERT INTO curated.dim_date
WITH accepted_dates AS (
    SELECT o.order_business_date calendar_date
    FROM staging.order_event o JOIN quality.entity_disposition d
      ON d.entity_type='order' AND d.business_key=o.order_id AND d.is_curated_eligible
    WHERE o.is_canonical_event AND o.order_business_date IS NOT NULL
    UNION SELECT o.updated_business_date
    FROM staging.order_event o JOIN quality.entity_disposition d
      ON d.entity_type='order' AND d.business_key=o.order_id AND d.is_curated_eligible
    WHERE o.is_canonical_event AND o.updated_business_date IS NOT NULL
    UNION SELECT o.departure_date
    FROM staging.order_event o JOIN quality.entity_disposition d
      ON d.entity_type='order' AND d.business_key=o.order_id AND d.is_curated_eligible
    WHERE o.is_canonical_event AND o.departure_date IS NOT NULL
    UNION SELECT f.rate_date FROM staging.fx_rate f JOIN quality.entity_disposition d
      ON d.entity_type='fx_rate'
     AND d.business_key=f.rate_date::VARCHAR || '|' || f.currency AND d.is_curated_eligible
    WHERE f.rate_date IS NOT NULL
    UNION SELECT s.extract_date FROM staging.member_snapshot s
      JOIN quality.entity_disposition d ON d.entity_type='member'
       AND d.business_key=s.member_id AND d.is_curated_eligible
    WHERE s.extract_date IS NOT NULL
    UNION SELECT s.register_date FROM staging.member_snapshot s
      JOIN quality.entity_disposition d ON d.entity_type='member'
       AND d.business_key=s.member_id AND d.is_curated_eligible
    WHERE s.register_date IS NOT NULL
    UNION SELECT s.canonical_birth_date FROM staging.member_snapshot s
      JOIN quality.entity_disposition d ON d.entity_type='member'
       AND d.business_key=s.member_id AND d.is_curated_eligible
    WHERE s.canonical_birth_date IS NOT NULL
), bounds AS (
    SELECT min(calendar_date) min_date,max(calendar_date) max_date FROM accepted_dates
), dates AS (
    SELECT generate_series::DATE calendar_date
    FROM bounds,generate_series(min_date,max_date,INTERVAL 1 DAY)
)
SELECT strftime(calendar_date,'%Y%m%d')::INTEGER,calendar_date,
       year(calendar_date)::SMALLINT,quarter(calendar_date)::SMALLINT,
       month(calendar_date)::SMALLINT,day(calendar_date)::SMALLINT,
       isoyear(calendar_date)::SMALLINT,week(calendar_date)::SMALLINT,
       isodow(calendar_date)::SMALLINT,strftime(calendar_date,'%Y-%m'),
       strftime(calendar_date,'%B'),strftime(calendar_date,'%A'),
       isodow(calendar_date) IN (6,7),
       calendar_date=date_trunc('month',calendar_date)::DATE,
       calendar_date=last_day(calendar_date),
       calendar_date=date_trunc('quarter',calendar_date)::DATE,
       calendar_date=(date_trunc('quarter',calendar_date)+INTERVAL 3 MONTH-INTERVAL 1 DAY)::DATE,
       calendar_date=date_trunc('year',calendar_date)::DATE,
       calendar_date=(date_trunc('year',calendar_date)+INTERVAL 1 YEAR-INTERVAL 1 DAY)::DATE
FROM dates;
