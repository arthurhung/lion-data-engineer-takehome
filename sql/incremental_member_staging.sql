CREATE OR REPLACE TABLE staging.member_snapshot AS
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
