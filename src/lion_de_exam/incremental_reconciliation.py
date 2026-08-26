"""Deterministic Phase 3 analytical reconciliation and evidence."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import duckdb

EVIDENCE_FILES = (
    "batch_summary.json",
    "final_summary.json",
    "rerun_summary.json",
    "validation_summary.json",
)


def _value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    result = connection.execute(sql)
    columns = [item[0] for item in result.description]
    return [
        {column: _value(value) for column, value in zip(columns, row, strict=True)}
        for row in result.fetchall()
    ]


def canonical_json(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def analytical_snapshot(
    connection: duckdb.DuckDBPyConnection, batch_order: int, batch_name: str
) -> dict[str, object]:
    """Return deterministic analytical state; runtime audit attempts are excluded."""
    return {
        "schema_version": 3,
        "batch_order": batch_order,
        "batch_name": batch_name,
        "source_registry": _rows(
            connection,
            """
            SELECT source_file,dataset_role,batch_order,file_sha256,schema_sha256,
                   byte_size,source_row_count
            FROM audit.source_file_registry ORDER BY batch_order,dataset_role,source_file
            """,
        ),
        "table_counts": _rows(
            connection,
            """
            SELECT * FROM (VALUES
              ('raw.order_event',(SELECT count(*) FROM raw.order_event)),
              ('staging.order_event',(SELECT count(*) FROM staging.order_event)),
              ('staging.order_event_lineage',(SELECT count(*) FROM staging.order_event_lineage)),
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
        "event_reconciliation": _rows(
            connection,
            """
            SELECT count(*) raw_rows,count(DISTINCT order_id) raw_orders,
              count(DISTINCT canonical_event_hash) logical_events,
              count(*)-count(DISTINCT canonical_event_hash) duplicate_physical_rows,
              count(*) FILTER(WHERE is_canonical_event) representative_rows
            FROM staging.order_event
            """,
        )[0],
        "order_dispositions": _rows(
            connection,
            """
            SELECT final_disposition,count(*) order_count
            FROM quality.entity_disposition WHERE entity_type='order'
            GROUP BY final_disposition ORDER BY final_disposition
            """,
        ),
        "fact_reconciliation": _rows(
            connection,
            """
            SELECT count(*) fact_rows,count(DISTINCT order_id) distinct_orders,
              sum(gross_amount_twd_exact) gross_exact_sum,
              sum(net_amount_twd_exact) net_exact_sum,
              sum(gross_amount_twd) gross_rounded_sum,
              sum(net_amount_twd) net_rounded_sum
            FROM curated.fact_order
            """,
        )[0],
        "member_reconciliation": _rows(
            connection,
            """
            SELECT count(*) FILTER(WHERE NOT is_unknown) member_versions,
              count(*) FILTER(WHERE is_current AND NOT is_unknown) current_members,
              count(*) member_rows
            FROM curated.dim_member
            """,
        )[0],
        "quarantine_reconciliation": {
            "summary": _rows(
                connection,
                """
                SELECT
                  (SELECT count(*) FROM quality.entity_disposition
                    WHERE entity_type='order' AND NOT is_curated_eligible)
                    quarantined_order_entities,
                  (SELECT count(*) FROM quality.quarantine_row) quarantine_physical_rows,
                  (SELECT count(*) FROM quality.issue_hit) issue_hit_source_rule_links,
                  (SELECT count(*) FROM quality.entity_rule) entity_rule_links
                """,
            )[0],
            "rules": _rows(
                connection,
                """
                SELECT rule_id,disposition,count(*) source_rule_links,
                  count(DISTINCT entity_type || '|' || business_key) affected_entities
                FROM quality.issue_hit GROUP BY rule_id,disposition ORDER BY rule_id
                """,
            ),
        },
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
                 source_row_uid || ':' || canonical_event_hash || ':' ||
                 representative_source_row_uid,'|' ORDER BY source_row_uid),''))
                 FROM staging.order_event_lineage) event_lineage_sha256,
              (SELECT sha256(coalesce(string_agg(
                 entity_type || ':' || business_key || ':' || rule_ids,
                 '|' ORDER BY entity_type,business_key,source_row_uid),''))
                 FROM quality.quarantine_row) quarantine_sha256
            """,
        )[0],
    }


def snapshot_sha256(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(canonical_json(snapshot)).hexdigest()


def stored_batch_snapshots(connection: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    return [
        json.loads(row[0])
        for row in connection.execute(
            "SELECT snapshot_json::VARCHAR FROM audit.batch_reconciliation ORDER BY batch_order"
        ).fetchall()
    ]


def write_phase3_evidence(
    connection: duckdb.DuckDBPyConnection,
    evidence_dir: Path,
    rerun_summary: dict[str, object],
) -> str:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    batches = stored_batch_snapshots(connection)
    payloads: dict[str, object] = {
        "batch_summary.json": {"schema_version": 3, "batches": batches},
        "final_summary.json": batches[-1],
        "rerun_summary.json": rerun_summary,
        "validation_summary.json": {
            "schema_version": 3,
            "checks": _rows(
                connection,
                "SELECT check_id,violation_count,detail FROM quality.validation_result "
                "ORDER BY check_id",
            ),
        },
    }
    encoded = {name: canonical_json(payloads[name]) for name in EVIDENCE_FILES}
    for name, data in encoded.items():
        (evidence_dir / name).write_bytes(data)
    bundle = hashlib.sha256(b"".join(encoded[name] for name in EVIDENCE_FILES)).hexdigest()
    manifest = {
        "algorithm": "SHA-256",
        "canonical_bundle_sha256": bundle,
        "canonicalization": "UTF-8, LF, JSON sorted keys, indent=2, trailing LF",
        "evidence_content": "deterministic analytical state and replay outcomes only",
        "files": [
            {"file": name, "sha256": hashlib.sha256(encoded[name]).hexdigest()}
            for name in EVIDENCE_FILES
        ],
        "schema_version": 3,
    }
    (evidence_dir / "evidence_manifest.json").write_bytes(canonical_json(manifest))
    return bundle
