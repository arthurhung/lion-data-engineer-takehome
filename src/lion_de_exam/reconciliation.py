"""Phase 2 validation and deterministic evidence generation."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VALIDATION_SQL = PROJECT_ROOT / "sql" / "validation.sql"
EVIDENCE_FILES = ("model_summary.json", "validation_summary.json")


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    result = connection.execute(sql)
    columns = [item[0] for item in result.description]
    return [
        {column: _json_value(value) for column, value in zip(columns, row, strict=True)}
        for row in result.fetchall()
    ]


def canonical_evidence(connection: duckdb.DuckDBPyConnection) -> dict[str, dict[str, object]]:
    """Return evidence that excludes timestamps, paths and execution metadata."""
    model_summary: dict[str, object] = {
        "schema_version": 2,
        "scope": "phase_2_clean_base_build_stability_not_incremental_idempotency",
        "table_counts": _rows(
            connection,
            """
            SELECT * FROM (VALUES
              ('raw.order_event',(SELECT count(*) FROM raw.order_event)),
              ('raw.member_snapshot',(SELECT count(*) FROM raw.member_snapshot)),
              ('raw.product',(SELECT count(*) FROM raw.product)),
              ('raw.fx_rate',(SELECT count(*) FROM raw.fx_rate)),
              ('staging.order_event',(SELECT count(*) FROM staging.order_event)),
              ('staging.member_snapshot',(SELECT count(*) FROM staging.member_snapshot)),
              ('staging.product',(SELECT count(*) FROM staging.product)),
              ('staging.fx_rate',(SELECT count(*) FROM staging.fx_rate)),
              ('quality.issue_hit',(SELECT count(*) FROM quality.issue_hit)),
              ('quality.entity_rule',(SELECT count(*) FROM quality.entity_rule)),
              ('quality.entity_disposition',(SELECT count(*) FROM quality.entity_disposition)),
              ('quality.quarantine_row',(SELECT count(*) FROM quality.quarantine_row)),
              ('curated.dim_date',(SELECT count(*) FROM curated.dim_date)),
              ('curated.dim_product',(SELECT count(*) FROM curated.dim_product)),
              ('curated.dim_member',(SELECT count(*) FROM curated.dim_member)),
              ('curated.dim_member_lineage',(SELECT count(*) FROM curated.dim_member_lineage)),
              ('curated.fact_order',(SELECT count(*) FROM curated.fact_order))
            ) counts(table_name,row_count) ORDER BY table_name
            """,
        ),
        "order_reconciliation": _rows(
            connection,
            """
            SELECT count(*) raw_rows,count(DISTINCT order_id) raw_orders,
              count(*) FILTER (WHERE is_canonical_event) canonical_event_rows,
              sum(duplicate_source_row_count-1) FILTER (WHERE is_canonical_event)
                duplicate_extra_rows,
              (SELECT count(*) FROM quality.entity_disposition
                 WHERE entity_type='order' AND NOT is_curated_eligible) quarantined_orders,
              (SELECT count(*) FROM quality.quarantine_row WHERE dataset='orders')
                quarantined_source_rows,
              (SELECT count(*) FROM curated.fact_order) fact_rows
            FROM staging.order_event
            """,
        )[0],
        "order_invariant_bridge": {
            "summary": _rows(
                connection,
                """
                WITH raw_conflicts AS (
                    SELECT order_id FROM raw.order_event GROUP BY order_id
                    HAVING count(DISTINCT sha256(to_json(struct_pack(
                        member_id:=member_id,product_id:=product_id,channel:=channel,
                        quantity:=quantity,currency:=currency,amount:=amount,
                        coupon_discount:=coupon_discount,order_created_at:=order_created_at,
                        departure_date:=departure_date
                    ))))>1
                ), canonical_conflicts AS (
                    SELECT order_id FROM staging.order_event WHERE is_canonical_event
                    GROUP BY order_id HAVING count(DISTINCT invariant_hash)>1
                )
                SELECT
                  (SELECT count(*) FROM (
                    SELECT order_id FROM raw.order_event GROUP BY order_id HAVING count(*)>1
                  )) multi_event_orders,
                  (SELECT count(*) FROM raw_conflicts) raw_textual_conflict_candidates,
                  (SELECT count(*) FROM canonical_conflicts) canonical_semantic_conflicts
                """,
            )[0],
            "field_counts": _rows(
                connection,
                """
                WITH fields(field_name,field_order) AS (VALUES
                    ('member_id',1),('product_id',2),('channel',3),('quantity',4),
                    ('currency',5),('amount',6),('coupon_discount',7),
                    ('order_created_at',8),('departure_date',9)
                ), multi_orders AS (
                    SELECT order_id FROM raw.order_event GROUP BY order_id HAVING count(*)>1
                ), raw_values AS (
                    SELECT r.order_id,v.field_name,v.field_value
                    FROM raw.order_event r JOIN multi_orders USING (order_id), LATERAL (VALUES
                      ('member_id',coalesce(r.member_id,'<NULL>')),
                      ('product_id',coalesce(r.product_id,'<NULL>')),
                      ('channel',coalesce(r.channel,'<NULL>')),
                      ('quantity',coalesce(r.quantity,'<NULL>')),
                      ('currency',coalesce(r.currency,'<NULL>')),
                      ('amount',coalesce(r.amount,'<NULL>')),
                      ('coupon_discount',coalesce(r.coupon_discount,'<NULL>')),
                      ('order_created_at',coalesce(r.order_created_at,'<NULL>')),
                      ('departure_date',coalesce(r.departure_date,'<NULL>'))
                    ) v(field_name,field_value)
                ), canonical_values AS (
                    SELECT s.order_id,v.field_name,v.field_value
                    FROM staging.order_event s JOIN multi_orders USING (order_id), LATERAL (VALUES
                      ('member_id',coalesce(s.member_id,'<NULL>')),
                      ('product_id',coalesce(s.product_id,'<NULL>')),
                      ('channel',coalesce(s.channel,'<NULL>')),
                      ('quantity',coalesce(s.quantity::VARCHAR,'<NULL>')),
                      ('currency',coalesce(s.normalized_currency,'<NULL>')),
                      ('amount',coalesce(s.original_amount::VARCHAR,'<NULL>')),
                      ('coupon_discount',coalesce(s.coupon_discount_twd_source::VARCHAR,'<NULL>')),
                      ('order_created_at',coalesce(s.order_created_at::VARCHAR,'<NULL>')),
                      ('departure_date',coalesce(s.departure_date::VARCHAR,'<NULL>'))
                    ) v(field_name,field_value)
                    WHERE s.is_canonical_event
                ), raw_counts AS (
                    SELECT field_name,count(*) raw_textual_conflict_orders FROM (
                      SELECT order_id,field_name FROM raw_values GROUP BY order_id,field_name
                      HAVING count(DISTINCT field_value)>1
                    ) GROUP BY field_name
                ), canonical_counts AS (
                    SELECT field_name,count(*) canonical_semantic_conflict_orders FROM (
                      SELECT order_id,field_name FROM canonical_values GROUP BY order_id,field_name
                      HAVING count(DISTINCT field_value)>1
                    ) GROUP BY field_name
                )
                SELECT f.field_name,coalesce(r.raw_textual_conflict_orders,0)
                         raw_textual_conflict_orders,
                       coalesce(c.canonical_semantic_conflict_orders,0)
                         canonical_semantic_conflict_orders
                FROM fields f LEFT JOIN raw_counts r USING(field_name)
                LEFT JOIN canonical_counts c USING(field_name) ORDER BY f.field_order
                """,
            ),
            "raw_timestamp_representation_counts": _rows(
                connection,
                """
                WITH candidates AS (
                    SELECT order_id FROM raw.order_event GROUP BY order_id
                    HAVING count(DISTINCT sha256(to_json(struct_pack(
                        member_id:=member_id,product_id:=product_id,channel:=channel,
                        quantity:=quantity,currency:=currency,amount:=amount,
                        coupon_discount:=coupon_discount,order_created_at:=order_created_at,
                        departure_date:=departure_date
                    ))))>1
                ), categorized AS (
                    SELECT order_id,CASE
                      WHEN regexp_full_match(order_created_at,'.*Z$') THEN 'UTC_Z'
                      WHEN regexp_full_match(order_created_at,'.*[+-][0-9]{2}:[0-9]{2}$')
                        THEN 'EXPLICIT_OFFSET'
                      WHEN regexp_full_match(order_created_at,
                        '^[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
                        THEN 'NAIVE_ASIA_TAIPEI'
                      ELSE 'OTHER' END representation
                    FROM raw.order_event JOIN candidates USING(order_id)
                )
                SELECT representation,count(*) source_rows,count(DISTINCT order_id) orders
                FROM categorized GROUP BY representation ORDER BY representation
                """,
            ),
        },
        "timezone_assumption_bridge": {
            "summary": _rows(
                connection,
                """
                WITH flagged AS (
                    SELECT * FROM staging.order_event WHERE timezone_assumed
                ), accepted AS (
                    SELECT f.* FROM flagged f JOIN quality.entity_disposition d
                      ON d.entity_type='order' AND d.business_key=f.order_id
                     AND d.is_curated_eligible
                ), quarantined AS (
                    SELECT f.* FROM flagged f JOIN quality.entity_disposition d
                      ON d.entity_type='order' AND d.business_key=f.order_id
                     AND NOT d.is_curated_eligible
                ), selected AS (
                    SELECT a.* FROM accepted a JOIN curated.fact_order f
                      ON f.source_row_uid=a.source_row_uid
                )
                SELECT
                  (SELECT count(*) FROM flagged) raw_assumption_rows,
                  (SELECT count(DISTINCT order_id) FROM flagged) raw_assumption_orders,
                  (SELECT count(*) FROM accepted) accepted_flagged_source_rows,
                  (SELECT count(DISTINCT order_id) FROM accepted)
                    accepted_orders_with_flagged_source,
                  (SELECT count(*) FROM selected) selected_flagged_fact_rows,
                  (SELECT count(DISTINCT order_id) FROM selected) selected_flagged_fact_orders,
                  (SELECT count(*) FROM accepted a LEFT JOIN selected s USING(source_row_uid)
                    WHERE s.source_row_uid IS NULL) accepted_but_not_latest_rows,
                  (SELECT count(DISTINCT a.order_id) FROM accepted a
                    LEFT JOIN selected s USING(source_row_uid) WHERE s.source_row_uid IS NULL)
                    accepted_but_not_latest_orders,
                  (SELECT count(*) FROM quarantined) quarantined_flagged_source_rows,
                  (SELECT count(DISTINCT order_id) FROM quarantined) quarantined_flagged_orders,
                  (SELECT count(*) FROM curated.fact_order WHERE timezone_assumed)
                    fact_timezone_assumed_rows
                """,
            )[0],
            "quarantine_rule_breakdown": _rows(
                connection,
                """
                WITH flagged AS (SELECT * FROM staging.order_event WHERE timezone_assumed)
                SELECT r.rule_id,count(DISTINCT f.source_row_uid) flagged_source_rows,
                       count(DISTINCT f.order_id) flagged_orders
                FROM flagged f JOIN quality.entity_rule r
                  ON r.entity_type='order' AND r.business_key=f.order_id
                 AND r.disposition='QUARANTINE'
                GROUP BY r.rule_id ORDER BY r.rule_id
                """,
            ),
            "quarantine_rule_overlap": _rows(
                connection,
                """
                WITH flagged AS (SELECT * FROM staging.order_event WHERE timezone_assumed),
                order_rules AS (
                    SELECT business_key order_id,string_agg(rule_id,',' ORDER BY rule_id) rule_set,
                           count(*) rule_count
                    FROM quality.entity_rule
                    WHERE entity_type='order' AND disposition='QUARANTINE'
                    GROUP BY business_key
                )
                SELECT rule_set,rule_count,count(*) flagged_source_rows,
                       count(DISTINCT order_id) flagged_orders
                FROM flagged JOIN order_rules USING(order_id)
                GROUP BY rule_set,rule_count ORDER BY rule_set
                """,
            ),
        },
        "entity_disposition_bridge": {
            "total_entities": _rows(
                connection,
                "SELECT count(*) total_entities FROM quality.entity_disposition",
            )[0]["total_entities"],
            "by_entity_type": _rows(
                connection,
                """
                WITH grains(entity_type,grain,entity_order) AS (VALUES
                  ('order','order_id',1),
                  ('member_snapshot','member_id + extract_date',2),
                  ('member','member_id',3),
                  ('product','product_id',4),
                  ('fx_rate','rate_date + currency',5)
                ), counts AS (
                  SELECT entity_type,count(*) distinct_entities,
                    count(*) FILTER(WHERE final_disposition='ACCEPT') accepted,
                    count(*) FILTER(WHERE final_disposition='ACCEPT_WITH_FLAGS')
                      accepted_with_flags,
                    count(*) FILTER(WHERE final_disposition='QUARANTINE') quarantined
                  FROM quality.entity_disposition GROUP BY entity_type
                )
                SELECT g.entity_type,g.grain,coalesce(c.distinct_entities,0) distinct_entities,
                       coalesce(c.accepted,0) accepted,
                       coalesce(c.accepted_with_flags,0) accepted_with_flags,
                       coalesce(c.quarantined,0) quarantined
                FROM grains g LEFT JOIN counts c USING(entity_type) ORDER BY g.entity_order
                """,
            ),
        },
        "quarantine_reconciliation": {
            "summary": _rows(
                connection,
                """
                SELECT
                  (SELECT count(*) FROM quality.entity_disposition
                    WHERE entity_type='order' AND NOT is_curated_eligible) quarantined_orders,
                  (SELECT count(*) FROM quality.quarantine_row) quarantine_physical_rows,
                  (SELECT count(*) FROM quality.issue_hit) issue_hit_source_rule_links,
                  (SELECT count(*) FROM quality.entity_rule) entity_rule_links,
                  (SELECT count(*) FROM quality.issue_hit)-
                    (SELECT count(*) FROM quality.entity_rule) collapsed_source_rule_links
                """,
            )[0],
            "by_entity_type": _rows(
                connection,
                """
                WITH types(entity_type,entity_order) AS (VALUES
                  ('order',1),('member_snapshot',2),('member',3),('product',4),('fx_rate',5)
                ), entity_counts AS (
                  SELECT entity_type,count(*) distinct_business_entities,
                    count(*) FILTER(WHERE quarantine_rule_count>1) rule_overlap_entities
                  FROM quality.entity_disposition d
                  WHERE NOT d.is_curated_eligible
                  GROUP BY entity_type
                ), rule_counts AS (
                  SELECT r.entity_type,count(*) entity_rule_links,
                         count(DISTINCT r.rule_id) distinct_rules
                  FROM quality.entity_rule r JOIN quality.entity_disposition d
                    USING(entity_type,business_key)
                  WHERE NOT d.is_curated_eligible AND r.disposition='QUARANTINE'
                  GROUP BY r.entity_type
                ), entities AS (
                  SELECT e.entity_type,e.distinct_business_entities,
                         r.entity_rule_links,r.distinct_rules,e.rule_overlap_entities
                  FROM entity_counts e JOIN rule_counts r USING(entity_type)
                ), physical AS (
                  SELECT entity_type,count(*) physical_source_rows
                  FROM quality.quarantine_row GROUP BY entity_type
                )
                SELECT t.entity_type,coalesce(e.distinct_business_entities,0)
                         distinct_business_entities,
                       coalesce(p.physical_source_rows,0) physical_source_rows,
                       coalesce(e.distinct_rules,0) distinct_rules,
                       coalesce(e.entity_rule_links,0) entity_rule_links,
                       coalesce(e.rule_overlap_entities,0) rule_overlap_entities
                FROM types t LEFT JOIN entities e USING(entity_type)
                LEFT JOIN physical p USING(entity_type) ORDER BY t.entity_order
                """,
            ),
            "issue_hit_to_entity_rule_by_rule": _rows(
                connection,
                """
                SELECT h.rule_id,count(*) issue_hit_source_rule_links,
                  count(DISTINCT h.entity_type || '|' || h.business_key || '|' || h.rule_id)
                    entity_rule_links,
                  count(*)-count(DISTINCT h.entity_type || '|' || h.business_key || '|' ||
                    h.rule_id)
                    collapsed_source_rule_links
                FROM quality.issue_hit h GROUP BY h.rule_id ORDER BY h.rule_id
                """,
            ),
            "quarantined_multi_event_orders": _rows(
                connection,
                """
                SELECT count(*) quarantined_multi_event_orders FROM (
                  SELECT d.business_key FROM quality.entity_disposition d
                  JOIN staging.order_event o
                    ON d.entity_type='order' AND d.business_key=o.order_id
                  WHERE NOT d.is_curated_eligible GROUP BY d.business_key HAVING count(*)>1
                )
                """,
            )[0]["quarantined_multi_event_orders"],
        },
        "member_summary": _rows(
            connection,
            """
            SELECT
              count(*) FILTER (WHERE NOT is_unknown) member_versions,
              count(*) FILTER (WHERE is_current AND NOT is_unknown) current_versions,
              count(DISTINCT member_id) FILTER (WHERE NOT is_unknown) represented_members,
              (SELECT count(DISTINCT member_id || '|' || extract_date::VARCHAR)
                 FROM staging.member_snapshot
                 WHERE same_day_payload_count>1) conflict_snapshot_keys,
              (SELECT count(*) FROM curated.fact_order WHERE member_sk=0) unknown_member_facts
            FROM curated.dim_member
            """,
        )[0],
        "member_scd2_bridge": {
            "summary": _rows(
                connection,
                """
                WITH conflict_rows AS (
                  SELECT * FROM staging.member_snapshot WHERE same_day_payload_count>1
                ), conflicts AS (
                  SELECT member_id,extract_date FROM conflict_rows GROUP BY member_id,extract_date
                ), conflict_members AS (
                  SELECT DISTINCT member_id FROM conflicts
                ), represented AS (
                  SELECT DISTINCT member_id FROM curated.dim_member WHERE NOT is_unknown
                ), restarted AS (
                  SELECT DISTINCT c.member_id FROM conflicts c JOIN curated.dim_member d
                    ON d.member_id=c.member_id AND NOT d.is_unknown
                   AND d.valid_from>c.extract_date
                ), version_start_lineage AS (
                  SELECT l.source_row_uid FROM curated.dim_member_lineage l
                  JOIN curated.dim_member d ON d.member_sk=l.member_sk
                  WHERE d.source_row_uid=l.source_row_uid
                )
                SELECT
                  (SELECT count(*) FROM raw.member_snapshot) raw_snapshot_rows,
                  (SELECT count(*) FROM conflict_rows) same_day_conflict_raw_rows,
                  (SELECT count(*) FROM conflicts) same_day_conflict_snapshot_entities,
                  (SELECT count(*) FROM curated.dim_member_lineage) accepted_lineage_rows,
                  (SELECT count(*) FROM curated.dim_member WHERE NOT is_unknown) known_versions,
                  (SELECT count(*) FROM curated.dim_member_lineage l
                    LEFT JOIN version_start_lineage v USING(source_row_uid)
                    WHERE v.source_row_uid IS NULL) unchanged_snapshot_lineage_rows,
                  (SELECT count(*) FROM represented) represented_members,
                  (SELECT count(*) FROM curated.dim_member
                    WHERE is_current AND NOT is_unknown) current_members,
                  (SELECT count(*) FROM conflict_members c LEFT JOIN represented r USING(member_id)
                    WHERE r.member_id IS NULL) conflict_members_without_reliable_version,
                  (SELECT count(*) FROM restarted) conflict_members_restarted_later,
                  (SELECT count(*) FROM curated.fact_order WHERE member_sk=0) unknown_member_facts,
                  (SELECT count(DISTINCT member_id) FROM curated.fact_order WHERE member_sk=0)
                    unknown_member_source_ids
                """,
            )[0],
            "unknown_fact_reason_breakdown": _rows(
                connection,
                """
                SELECT CASE WHEN EXISTS(
                    SELECT 1 FROM curated.dim_member d
                    WHERE d.member_id=f.member_id AND NOT d.is_unknown
                  ) THEN 'uncertainty_gap_before_restart' ELSE 'no_reliable_version' END reason,
                  count(*) fact_rows,count(DISTINCT f.member_id) source_member_ids
                FROM curated.fact_order f WHERE member_sk=0
                GROUP BY reason ORDER BY reason
                """,
            ),
        },
        "birth_date_summary": _rows(
            connection,
            """
            SELECT
              count(*) FILTER (WHERE birth_date_sentinel) sentinel_rows,
              count(DISTINCT member_id) FILTER (WHERE birth_date_sentinel) sentinel_members,
              count(DISTINCT member_id) FILTER (WHERE birth_date_unknown) sentinel_only_members,
              count(DISTINCT member_id) FILTER (WHERE birth_date_restatement) restatement_members,
              count(DISTINCT member_id) FILTER (WHERE birth_date_identity_ambiguous)
                ambiguous_members
            FROM staging.member_snapshot
            """,
        )[0],
        "dimension_summary": _rows(
            connection,
            """
            SELECT
              (SELECT count(*) FROM curated.dim_product WHERE NOT is_unknown) known_products,
              (SELECT count(*) FROM curated.dim_product WHERE is_unknown) unknown_product_rows,
              (SELECT min(calendar_date)::VARCHAR FROM curated.dim_date) date_min,
              (SELECT max(calendar_date)::VARCHAR FROM curated.dim_date) date_max,
              (SELECT count(*) FROM curated.dim_date) date_rows
            """,
        )[0],
        "fact_flags": _rows(
            connection,
            """
            SELECT count(*) fact_rows,
              count(*) FILTER (WHERE missing_product) missing_product_rows,
              count(*) FILTER (WHERE missing_member_asof) missing_member_asof_rows,
              count(*) FILTER (WHERE currency_normalized) currency_normalized_rows,
              count(*) FILTER (WHERE timezone_assumed) timezone_assumed_rows,
              count(*) FILTER (WHERE status_transition_warning) status_warning_rows,
              sum(duplicate_source_row_count) duplicate_extra_rows
            FROM curated.fact_order
            """,
        )[0],
        "money_reconciliation": _rows(
            connection,
            """
            SELECT sum(gross_amount_twd_exact) gross_exact_sum,
              sum(net_amount_twd_exact) net_exact_sum,
              sum(gross_amount_twd) gross_rounded_sum,
              sum(net_amount_twd) net_rounded_sum
            FROM curated.fact_order
            """,
        )[0],
        "quality_rule_counts": _rows(
            connection,
            """
            SELECT rule_id,disposition,count(*) issue_hit_rows,
              count(DISTINCT entity_type || '|' || business_key) affected_entities
            FROM quality.issue_hit GROUP BY rule_id,disposition ORDER BY rule_id
            """,
        ),
        "state_checksums": _rows(
            connection,
            """
            SELECT
              (SELECT sha256(coalesce(string_agg(order_id,'|' ORDER BY order_id),''))
                 FROM curated.fact_order) fact_order_key_sha256,
              (SELECT sha256(coalesce(string_agg(
                 order_id || ':' || gross_amount_twd::VARCHAR || ':' || net_amount_twd::VARCHAR,
                 '|' ORDER BY order_id),'')) FROM curated.fact_order) fact_money_sha256,
              (SELECT sha256(coalesce(string_agg(
                 member_id || ':' || valid_from::VARCHAR || ':' || valid_to::VARCHAR || ':' ||
                 member_sk::VARCHAR || ':' || version_hash,'|' ORDER BY member_id,valid_from),''))
                 FROM curated.dim_member WHERE NOT is_unknown) member_version_sha256,
              (SELECT sha256(coalesce(string_agg(
                 product_id || ':' || product_sk::VARCHAR,'|' ORDER BY product_id),''))
                 FROM curated.dim_product WHERE NOT is_unknown) product_key_sha256
            """,
        )[0],
        "source_files": _rows(
            connection,
            """
            SELECT source_file,count(*) row_count FROM (
              SELECT source_file FROM raw.order_event UNION ALL
              SELECT source_file FROM raw.member_snapshot UNION ALL
              SELECT source_file FROM raw.product UNION ALL
              SELECT source_file FROM raw.fx_rate
            ) sources GROUP BY source_file ORDER BY source_file
            """,
        ),
    }
    validation_summary: dict[str, object] = {
        "schema_version": 2,
        "checks": _rows(
            connection,
            "SELECT check_id,violation_count,detail "
            "FROM quality.validation_result ORDER BY check_id",
        ),
    }
    return {
        "model_summary.json": model_summary,
        "validation_summary.json": validation_summary,
    }


def write_evidence(
    connection: duckdb.DuckDBPyConnection, evidence_dir: Path
) -> str:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payloads = canonical_evidence(connection)
    encoded: dict[str, bytes] = {}
    for file_name in EVIDENCE_FILES:
        data = (
            json.dumps(payloads[file_name], ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        encoded[file_name] = data.encode("utf-8")
        (evidence_dir / file_name).write_bytes(encoded[file_name])
    bundle = hashlib.sha256(b"".join(encoded[name] for name in EVIDENCE_FILES)).hexdigest()
    manifest = {
        "algorithm": "SHA-256",
        "canonical_bundle_sha256": bundle,
        "canonicalization": "UTF-8, LF, JSON sorted keys, indent=2, trailing LF",
        "evidence_content": "deterministic analytical state only; audit/runtime metadata excluded",
        "files": [
            {"file": name, "sha256": hashlib.sha256(encoded[name]).hexdigest()}
            for name in EVIDENCE_FILES
        ],
        "schema_version": 2,
    }
    (evidence_dir / "evidence_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle


def validate_database(database: Path, evidence_dir: Path | None = None) -> str | None:
    if not database.is_file():
        raise FileNotFoundError(f"Warehouse database not found: {database}")
    connection = duckdb.connect(str(database))
    try:
        connection.execute(DEFAULT_VALIDATION_SQL.read_text(encoding="utf-8"))
        failures = connection.execute(
            "SELECT check_id,violation_count FROM quality.validation_result "
            "WHERE violation_count<>0 ORDER BY check_id"
        ).fetchall()
        if failures:
            raise RuntimeError(f"Warehouse validation failed: {failures}")
        return write_evidence(connection, evidence_dir) if evidence_dir else None
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the Phase 2 base warehouse")
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    checksum = validate_database(args.output_db, args.evidence_dir)
    if checksum:
        print(f"canonical_evidence_sha256={checksum}")
    print("validation=passed")


if __name__ == "__main__":
    main()
