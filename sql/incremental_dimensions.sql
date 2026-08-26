DELETE FROM curated.dim_date;

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
