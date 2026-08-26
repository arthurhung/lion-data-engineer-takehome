DELETE FROM quality.validation_result WHERE check_id='SOURCE_FILE_ALLOWLIST';

INSERT INTO quality.validation_result
SELECT 'SOURCE_FILE_ALLOWLIST',count(*),
       'warehouse source files must match the approved Phase 3 batch contract'
FROM (
    SELECT source_file,batch_order FROM raw.order_event
    UNION ALL SELECT source_file,batch_order FROM raw.member_snapshot
    UNION ALL SELECT source_file,batch_order FROM raw.product
    UNION ALL SELECT source_file,batch_order FROM raw.fx_rate
) s
WHERE (source_file,batch_order) NOT IN (
    ('orders_base.csv',0),('members.csv',0),('products.csv',0),('fx_rates.csv',0),
    ('orders_incremental_day1.csv',1),('orders_incremental_day2.csv',2),
    ('orders_incremental_day3.csv',3)
);

INSERT INTO quality.validation_result
SELECT * FROM (
    SELECT 'REGISTRY_LOGICAL_FILE_UNIQUENESS',count(*)-count(DISTINCT source_file),
      'each logical source filename has one successful registry row'
      FROM audit.source_file_registry
    UNION ALL SELECT 'BATCH_RECONCILIATION_UNIQUENESS',count(*)-count(DISTINCT batch_order),
      'each successful logical batch has one canonical reconciliation snapshot'
      FROM audit.batch_reconciliation
    UNION ALL SELECT 'RAW_SOURCE_REGISTRY_RECONCILIATION',count(*),
      'every raw source file must resolve to a registry record with the same batch order'
      FROM (
        SELECT source_file,batch_order FROM raw.order_event GROUP BY source_file,batch_order
        UNION SELECT source_file,batch_order FROM raw.member_snapshot GROUP BY source_file,batch_order
        UNION SELECT source_file,batch_order FROM raw.product GROUP BY source_file,batch_order
        UNION SELECT source_file,batch_order FROM raw.fx_rate GROUP BY source_file,batch_order
      ) s LEFT JOIN audit.source_file_registry r USING(source_file,batch_order)
      WHERE r.source_file IS NULL
    UNION ALL SELECT 'REGISTRY_SOURCE_ROW_COUNT',count(*),
      'registry metadata row count must equal the physical raw source row count'
      FROM audit.source_file_registry r LEFT JOIN (
        SELECT source_file,batch_order,count(*) source_row_count
          FROM raw.order_event GROUP BY source_file,batch_order
        UNION ALL SELECT source_file,batch_order,count(*)
          FROM raw.member_snapshot GROUP BY source_file,batch_order
        UNION ALL SELECT source_file,batch_order,count(*)
          FROM raw.product GROUP BY source_file,batch_order
        UNION ALL SELECT source_file,batch_order,count(*)
          FROM raw.fx_rate GROUP BY source_file,batch_order
      ) s USING(source_file,batch_order)
      WHERE s.source_file IS NULL OR s.source_row_count<>r.source_row_count
    UNION ALL SELECT 'ORDER_LINEAGE_RAW_RECONCILIATION',abs(
      (SELECT count(*) FROM raw.order_event)-
      (SELECT count(*) FROM staging.order_event_lineage)),
      'each physical raw order row maps to one logical event identity'
    UNION ALL SELECT 'ORDER_LINEAGE_LOGICAL_REPRESENTATIVE',count(*),
      'each logical event has exactly one deterministic lineage representative'
      FROM (
        SELECT canonical_event_hash,
          count(*) FILTER(WHERE is_lineage_representative) representatives
        FROM staging.order_event_lineage GROUP BY canonical_event_hash
        HAVING representatives<>1
      ) x
    UNION ALL SELECT 'FACT_LATEST_STATE',count(*),
      'fact source event must be the unique latest eligible canonical event'
      FROM curated.fact_order f JOIN staging.order_event s USING(source_row_uid)
      WHERE EXISTS (
        SELECT 1 FROM staging.order_event newer
        JOIN quality.entity_disposition d
          ON d.entity_type='order' AND d.business_key=newer.order_id AND d.is_curated_eligible
        WHERE newer.order_id=f.order_id AND newer.is_canonical_event
          AND newer.updated_at>s.updated_at
      )
    UNION ALL SELECT 'LATE_EVENT_FLAG_RECONCILIATION',abs(
      (SELECT count(*) FROM quality.issue_hit WHERE rule_id='INC-001')-
      (SELECT count(*) FROM staging.order_event o
       WHERE o.is_canonical_event AND o.batch_order>0 AND o.updated_at<(
         SELECT max(p.updated_at) FROM staging.order_event p
         WHERE p.is_canonical_event AND p.order_id=o.order_id
           AND p.batch_order<o.batch_order
       ))),
      'late canonical source rows must reconcile to INC-001 warning links'
    UNION ALL SELECT 'QUARANTINED_ORDER_FACT_LEAKAGE',count(*),
      'cumulative order-level quarantine must remove the order from curated fact'
      FROM curated.fact_order f JOIN quality.entity_disposition d
        ON d.entity_type='order' AND d.business_key=f.order_id
      WHERE NOT d.is_curated_eligible
) checks;
