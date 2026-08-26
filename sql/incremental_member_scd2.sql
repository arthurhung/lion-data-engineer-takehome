DELETE FROM curated.dim_member_lineage;
DELETE FROM curated.dim_member WHERE NOT is_unknown;

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
