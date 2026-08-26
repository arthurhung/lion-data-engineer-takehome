"""DuckDB orchestration for the authoritative Phase 1 SQL detectors."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import duckdb

from lion_de_exam.quality_catalog import DETECTOR_BY_ID, DETECTORS
from lion_de_exam.source_contract import CONTRACTS, SourceContract

SECTION_MARKER = re.compile(
    r"^-- (detector|analysis): ([A-Z0-9]+(?:-[A-Z0-9]+)+)\s*$", re.MULTILINE
)
RESULT_COLUMNS = ("business_key", "sample_sort_key", "sample_json")
EXPECTED_CONDITION_IDS = {"MEM-010", "ORD-002", "ORD-022"}
INVARIANT_FIELDS = (
    "member_id",
    "product_id",
    "channel",
    "quantity",
    "currency",
    "amount",
    "coupon_discount",
    "order_created_at",
    "departure_date",
)
IDENTITY_FIELDS = ("member_name", "birth_date", "register_date")
TIMESTAMP_FIELDS = ("order_created_at", "updated_at")


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _read_csv_sql(path: Path, contract: SourceContract) -> str:
    columns = ", ".join(f"{_sql_literal(item.name)}: 'VARCHAR'" for item in contract.columns)
    return (
        f"read_csv({_sql_literal(str(path.resolve()))}, header = true, auto_detect = false, "
        f"columns = {{{columns}}}, delim = ',', quote = '\"', escape = '\"', "
        "encoding = 'utf-8', nullstr = '__LION_NULL_SENTINEL__', strict_mode = true)"
    )


def register_raw_tables(
    connection: duckdb.DuckDBPyConnection, dataset_root: Path
) -> dict[str, str]:
    """Load immutable CSV text into temporary DuckDB tables and return file-to-table mapping."""
    connection.execute("SET TimeZone = 'UTC'")
    file_tables: dict[str, str] = {}
    dataset_tables: dict[str, list[str]] = {}
    for contract in CONTRACTS:
        tables: list[str] = []
        for batch_order, file_name in enumerate(contract.files):
            path = dataset_root / file_name
            if not path.is_file():
                raise FileNotFoundError(f"Missing required source: {path}")
            table_name = f"raw_{contract.dataset}_{batch_order}"
            connection.execute(
                f"CREATE TEMP TABLE {table_name} AS "
                f"SELECT *, {_sql_literal(file_name)} AS source_file, "
                f"{batch_order}::INTEGER AS batch_order, "
                f"row_number() OVER ()::BIGINT AS source_row_number "
                f"FROM {_read_csv_sql(path, contract)}"
            )
            table_info = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
            actual_columns = [row[1] for row in table_info]
            expected_columns = [item.name for item in contract.columns]
            if actual_columns[: len(expected_columns)] != expected_columns:
                raise ValueError(
                    f"Header mismatch for {file_name}: {actual_columns[: len(expected_columns)]}"
                )
            file_tables[file_name] = table_name
            tables.append(table_name)
        dataset_tables[contract.dataset] = tables

    for dataset, tables in dataset_tables.items():
        selects = " UNION ALL ".join(f"SELECT * FROM {table}" for table in tables)
        connection.execute(f"CREATE TEMP VIEW raw_{dataset} AS {selects}")
    return file_tables


def _load_sql_sections(path: Path, section_type: str) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    matches = list(SECTION_MARKER.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        if match.group(1) != section_type:
            continue
        section_id = match.group(2)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        statement = text[start:end].strip()
        if statement.endswith(";"):
            statement = statement[:-1].rstrip()
        if not statement:
            raise ValueError(f"{section_type} {section_id} has no SQL")
        if section_id in sections:
            raise ValueError(f"Duplicate SQL {section_type} ID: {section_id}")
        sections[section_id] = statement
    return sections


def load_detector_sql(path: Path) -> dict[str, str]:
    """Parse executable detector statements from quality_checks.sql."""
    return _load_sql_sections(path, "detector")


def load_analysis_sql(path: Path) -> dict[str, str]:
    """Parse executable supporting analysis statements from quality_checks.sql."""
    return _load_sql_sections(path, "analysis")


def validate_detector_catalog(detector_sql: dict[str, str]) -> None:
    sql_ids = set(detector_sql)
    catalog_ids = set(DETECTOR_BY_ID)
    if sql_ids != catalog_ids:
        raise ValueError(
            f"Detector catalog mismatch; SQL-only={sorted(sql_ids - catalog_ids)}, "
            f"catalog-only={sorted(catalog_ids - sql_ids)}"
        )


def execute_detectors(
    connection: duckdb.DuckDBPyConnection, detector_sql: dict[str, str]
) -> list[dict[str, object]]:
    """Execute every SQL detector, including zero-count checks, in canonical ID order."""
    validate_detector_catalog(detector_sql)
    results: list[dict[str, object]] = []
    for metadata in sorted(DETECTORS, key=lambda item: item.issue_id):
        statement = detector_sql[metadata.issue_id]
        description = connection.execute(
            f"DESCRIBE SELECT * FROM ({statement}) AS detector"
        ).fetchall()
        actual_columns = tuple(row[0] for row in description)
        if actual_columns != RESULT_COLUMNS:
            raise ValueError(
                f"Detector {metadata.issue_id} schema is {actual_columns}, "
                f"expected {RESULT_COLUMNS}"
            )
        affected_row_count, affected_key_count = connection.execute(
            "SELECT count(*)::BIGINT, "
            "count(DISTINCT business_key) FILTER (WHERE business_key IS NOT NULL)::BIGINT "
            f"FROM ({statement}) AS detector"
        ).fetchone()
        sample_rows = connection.execute(
            "SELECT sample_json::VARCHAR FROM ("
            f"{statement}) AS detector ORDER BY sample_sort_key, sample_json::VARCHAR LIMIT 3"
        ).fetchall()
        samples = [json.loads(row[0]) for row in sample_rows]
        if affected_row_count == 0:
            finding_type = "CONTROL_CHECK"
        elif metadata.issue_id in EXPECTED_CONDITION_IDS:
            finding_type = "EXPECTED_CONDITION"
        else:
            finding_type = "DATA_QUALITY_ISSUE"
        results.append(
            {
                "issue_id": metadata.issue_id,
                "dataset": metadata.dataset,
                "description": metadata.description,
                "detector": f"sql/quality_checks.sql#{metadata.issue_id}",
                "affected_row_count": affected_row_count,
                "affected_business_key_count": affected_key_count,
                "finding_type": finding_type,
                "deterministic_sample": samples,
                "business_impact": metadata.business_impact,
                "detection_severity": metadata.detection_severity,
                "proposed_disposition": metadata.proposed_disposition,
                "disposition_status": "proposed_pending_human_acceptance",
                "rationale": metadata.rationale,
                "pending_human_decision": metadata.pending_human_decision,
                "post_treatment_validation_proposal": metadata.post_treatment_validation_proposal,
            }
        )
    return results


def finding_summary(issues: list[dict[str, object]]) -> dict[str, int]:
    return {
        "detector_total": len(issues),
        "nonzero_detector_result_count": sum(
            int(issue["affected_row_count"] > 0) for issue in issues
        ),
        "candidate_data_quality_issue_count": sum(
            int(issue["finding_type"] == "DATA_QUALITY_ISSUE") for issue in issues
        ),
        "expected_condition_count": sum(
            int(issue["finding_type"] == "EXPECTED_CONDITION") for issue in issues
        ),
        "zero_result_control_check_count": sum(
            int(issue["finding_type"] == "CONTROL_CHECK") for issue in issues
        ),
    }


def _source_distribution(
    rows: list[tuple[object, ...]], file_index: int
) -> list[dict[str, object]]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row[file_index])] += 1
    return [
        {"source_file": source_file, "affected_event_row_count": counts[source_file]}
        for source_file in sorted(counts)
    ]


def _format_ratio(value: Decimal | None) -> str | None:
    return None if value is None else format(value, ".8f")


def execute_supporting_analyses(
    connection: duckdb.DuckDBPyConnection, analysis_sql: dict[str, str]
) -> dict[str, object]:
    expected_ids = {
        "MEM-009-IDENTITY-BREAKDOWN",
        "ORD-004-FIELD-BREAKDOWN",
        "ORD-012-TIMESTAMP-BREAKDOWN",
        "ORD-018-TRANSITION-PAIRS",
        "ORD-AMOUNT-SEMANTICS",
    }
    if set(analysis_sql) != expected_ids:
        raise ValueError(
            f"Supporting analysis mismatch; missing={sorted(expected_ids - set(analysis_sql))}, "
            f"unexpected={sorted(set(analysis_sql) - expected_ids)}"
        )

    invariant_rows = connection.execute(analysis_sql["ORD-004-FIELD-BREAKDOWN"]).fetchall()
    invariant_breakdown: list[dict[str, object]] = []
    for field_name in INVARIANT_FIELDS:
        rows = sorted(
            (row for row in invariant_rows if row[0] == field_name),
            key=lambda row: (row[1], row[2], row[3], row[4]),
        )
        invariant_breakdown.append(
            {
                "field_name": field_name,
                "affected_order_count": len({row[1] for row in rows}),
                "affected_event_row_count": len(rows),
                "source_file_distribution": _source_distribution(rows, 2),
                "deterministic_sample": [
                    {
                        "order_id": row[1],
                        "source_file": row[2],
                        "source_row_number": row[3],
                        "field_value": row[4],
                    }
                    for row in rows[:3]
                ],
            }
        )

    identity_rows = connection.execute(analysis_sql["MEM-009-IDENTITY-BREAKDOWN"]).fetchall()
    identity_breakdown: list[dict[str, object]] = []
    for field_name in IDENTITY_FIELDS:
        rows = sorted(
            (row for row in identity_rows if row[0] == field_name),
            key=lambda row: (row[1], row[4], row[2], row[3]),
        )
        identity_breakdown.append(
            {
                "field_name": field_name,
                "affected_member_count": len({row[1] for row in rows}),
                "affected_snapshot_row_count": len(rows),
                "source_file_distribution": _source_distribution(rows, 2),
                "deterministic_sample": [
                    {
                        "member_id": row[1],
                        "source_file": row[2],
                        "source_row_number": row[3],
                        "extract_date": row[4],
                        "value_present": row[5],
                    }
                    for row in rows[:3]
                ],
            }
        )

    timestamp_rows = connection.execute(analysis_sql["ORD-012-TIMESTAMP-BREAKDOWN"]).fetchall()
    timestamp_breakdown: list[dict[str, object]] = []
    for field_name in TIMESTAMP_FIELDS:
        rows = sorted(
            (row for row in timestamp_rows if row[0] == field_name),
            key=lambda row: (row[1], row[2], row[3], row[4]),
        )
        timestamp_breakdown.append(
            {
                "field_name": field_name,
                "affected_order_count": len({row[1] for row in rows}),
                "affected_event_row_count": len(rows),
                "source_file_distribution": _source_distribution(rows, 2),
                "observed_raw_formats": sorted({row[5] for row in rows}),
                "deterministic_sample": [
                    {
                        "order_id": row[1],
                        "source_file": row[2],
                        "source_row_number": row[3],
                        "raw_value": row[4],
                        "observed_raw_format": row[5],
                    }
                    for row in rows[:3]
                ],
            }
        )

    transition_rows = connection.execute(analysis_sql["ORD-018-TRANSITION-PAIRS"]).fetchall()
    pairs = sorted({(row[0], row[1]) for row in transition_rows})
    transition_breakdown: list[dict[str, object]] = []
    for from_status, to_status in pairs:
        rows = sorted(
            (row for row in transition_rows if row[0] == from_status and row[1] == to_status),
            key=lambda row: (row[2], row[3], row[4], row[5]),
        )
        transition_breakdown.append(
            {
                "from_status": from_status,
                "to_status": to_status,
                "event_count": len(rows),
                "affected_order_count": len({row[2] for row in rows}),
                "deterministic_sample": [
                    {
                        "order_id": row[2],
                        "updated_at": row[3],
                        "source_file": row[4],
                        "source_row_number": row[5],
                    }
                    for row in rows[:3]
                ],
            }
        )

    amount_rows = connection.execute(analysis_sql["ORD-AMOUNT-SEMANTICS"]).fetchall()
    amount_distributions = [
        {
            "comparison_basis": row[0],
            "eligible_row_count": row[1],
            "eligible_order_count": row[2],
            "minimum_ratio": _format_ratio(row[3]),
            "p01_ratio": _format_ratio(row[4]),
            "median_ratio": _format_ratio(row[5]),
            "p50_ratio": _format_ratio(row[6]),
            "p99_ratio": _format_ratio(row[7]),
            "maximum_ratio": _format_ratio(row[8]),
            "extreme_row_count": row[9],
            "extreme_order_count": row[10],
        }
        for row in sorted(amount_rows, key=lambda row: row[0])
    ]
    return {
        "order_invariant_field_breakdown": invariant_breakdown,
        "member_identity_field_breakdown": identity_breakdown,
        "timestamp_format_field_breakdown": timestamp_breakdown,
        "status_transition_pair_breakdown": transition_breakdown,
        "amount_semantic_analysis": {
            "candidate_amount_semantics": (
                "amount is the original-currency order-line total; FX conversion must not "
                "multiply quantity again"
            ),
            "amount_twd_formula": "DECIMAL(amount) * DECIMAL(rate_to_twd)",
            "fx_business_date": (
                "Asia/Taipei date of normalized order_created_at; source-specific naive format "
                "is assigned Asia/Taipei with timezone_assumed=true"
            ),
            "currency_handling": (
                "TWD and source-specific NTD alias use exact rate 1; USD/JPY require dated FX; "
                "no COALESCE(missing_rate, 1)"
            ),
            "outlier_basis": "amount_twd/(base_price_twd*quantity)",
            "outlier_threshold": {
                "inclusive_minimum": "0.50000000",
                "inclusive_maximum": "2.00000000",
            },
            "threshold_rationale": (
                "A deliberately wide review band around reference price; base_price_twd is a "
                "reference, not a required transaction price. Validate against p01/p50/p99."
            ),
            "distributions": amount_distributions,
        },
    }
