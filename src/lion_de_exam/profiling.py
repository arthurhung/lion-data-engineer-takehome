"""Reproducible Phase 1 profiling CLI and canonical evidence writer."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from lion_de_exam.quality import (
    execute_detectors,
    execute_supporting_analyses,
    finding_summary,
    load_analysis_sql,
    load_detector_sql,
    register_raw_tables,
)
from lion_de_exam.source_contract import CONTRACTS, ColumnContract, canonical_contract

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "LionDEExam/candidate_package/dataset"
DEFAULT_SQL_FILE = PROJECT_ROOT / "sql/quality_checks.sql"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output/quality"
DEFAULT_EVIDENCE_DIR = PROJECT_ROOT / "docs/evidence/phase_01"
CANONICAL_FILENAMES = (
    "source_contract.json",
    "source_profile.json",
    "issue_summary.json",
    "analysis_summary.json",
    "representative_samples.json",
    "treatment_matrix.json",
)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_typed(value: Any, column: ColumnContract) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        scale = column.decimal_scale or 0
        return format(value, f".{scale}f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _profile_column(
    connection: duckdb.DuckDBPyConnection, table: str, column: ColumnContract
) -> dict[str, object]:
    name = '"' + column.name.replace('"', '""') + '"'
    nonblank = f"{name} IS NOT NULL AND trim({name}) != ''"
    if column.duckdb_type == "VARCHAR":
        parse_failure = "0"
        typed_min = typed_max = None
    else:
        parse_failure = (
            f"count(*) FILTER (WHERE {nonblank} "
            f"AND try_cast({name} AS {column.duckdb_type}) IS NULL)"
        )
        typed_min, typed_max = connection.execute(
            f"SELECT min(try_cast({name} AS {column.duckdb_type})), "
            f"max(try_cast({name} AS {column.duckdb_type})) FROM {table} WHERE {nonblank}"
        ).fetchone()
    domain_sql = "0"
    if column.domain:
        values = ", ".join("'" + value.replace("'", "''") + "'" for value in column.domain)
        domain_sql = f"count(*) FILTER (WHERE {nonblank} AND {name} NOT IN ({values}))"
    pattern_sql = "0"
    if column.pattern:
        pattern = column.pattern.replace("'", "''")
        pattern_sql = (
            f"count(*) FILTER (WHERE {nonblank} AND NOT regexp_full_match({name}, '{pattern}'))"
        )
    row = connection.execute(
        "SELECT count(*) FILTER (WHERE " + name + " IS NULL), "
        "count(*) FILTER (WHERE " + name + " IS NOT NULL AND trim(" + name + ") = ''), "
        "count(DISTINCT "
        + name
        + "), min(length("
        + name
        + ")), max(length("
        + name
        + ")), "
        + parse_failure
        + ", "
        + domain_sql
        + ", "
        + pattern_sql
        + f" FROM {table}"
    ).fetchone()
    result: dict[str, object] = {
        "column": column.name,
        "logical_type": column.logical_type,
        "duckdb_type": column.duckdb_type,
        "nullable": column.nullable,
        "raw_null_count": row[0],
        "raw_blank_string_count": row[1],
        "raw_distinct_non_null_count": row[2],
        "raw_min_length": row[3],
        "raw_max_length": row[4],
        "typed_parse_failure_count": row[5],
        "domain_violation_count": row[6],
        "pattern_violation_count": row[7],
        "sensitive": column.sensitive,
    }
    if column.duckdb_type != "VARCHAR":
        result["typed_min"] = _format_typed(typed_min, column)
        result["typed_max"] = _format_typed(typed_max, column)
    if column.logical_type in {"integer", "decimal"}:
        quantiles = connection.execute(
            f"SELECT quantile_cont(try_cast({name} AS {column.duckdb_type}), 0.01), "
            f"quantile_cont(try_cast({name} AS {column.duckdb_type}), 0.50), "
            f"quantile_cont(try_cast({name} AS {column.duckdb_type}), 0.99) "
            f"FROM {table} WHERE {nonblank}"
        ).fetchone()
        result["typed_quantiles"] = {
            "p01": _format_typed(quantiles[0], column),
            "p50": _format_typed(quantiles[1], column),
            "p99": _format_typed(quantiles[2], column),
        }
    if column.logical_type in {"categorical", "currency_code"}:
        top_values = connection.execute(
            f"SELECT {name}, count(*) AS value_count FROM {table} "
            f"WHERE {nonblank} GROUP BY {name} ORDER BY value_count DESC, {name} LIMIT 20"
        ).fetchall()
        result["top_values"] = [
            {"raw_value": value, "row_count": value_count} for value, value_count in top_values
        ]
    return result


def build_source_profile(
    connection: duckdb.DuckDBPyConnection,
    dataset_root: Path,
    file_tables: dict[str, str],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for contract in CONTRACTS:
        for file_name in contract.files:
            table = file_tables[file_name]
            data_row_count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            column_names = ", ".join(f'"{item.name}"' for item in contract.columns)
            duplicate_rows = connection.execute(
                "SELECT count(*) FROM (SELECT count(*) AS copies FROM "
                f"{table} GROUP BY {column_names}) groups WHERE copies > 1"
            ).fetchone()[0]
            files.append(
                {
                    "dataset": contract.dataset,
                    "source_file": file_name,
                    "source_sha256": _sha256_file(dataset_root / file_name),
                    "data_row_count_excluding_header": data_row_count,
                    "duplicate_value_group_count": duplicate_rows,
                    "columns": [
                        _profile_column(connection, table, column) for column in contract.columns
                    ],
                }
            )
    return {
        "schema_version": 1,
        "row_count_definition": "CSV data rows excluding the header row",
        "distinct_count_definition": "COUNT(DISTINCT raw_value), excluding SQL NULL",
        "numeric_authority": "DuckDB DECIMAL; canonical evidence stores fixed-scale strings",
        "files": files,
    }


def _evidence_documents(
    source_profile: dict[str, object],
    issues: list[dict[str, object]],
    analyses: dict[str, object],
) -> dict[str, object]:
    analysis_by_issue = {
        "MEM-009": analyses["member_identity_field_breakdown"],
        "ORD-004": analyses["order_invariant_field_breakdown"],
        "ORD-012": analyses["timestamp_format_field_breakdown"],
        "ORD-018": analyses["status_transition_pair_breakdown"],
        "ORD-023": analyses["amount_semantic_analysis"],
    }
    for issue in issues:
        if issue["issue_id"] in analysis_by_issue:
            issue["supporting_analysis"] = analysis_by_issue[str(issue["issue_id"])]
    issue_document = {
        "schema_version": 1,
        "authoritative_detector_implementation": "sql/quality_checks.sql",
        "sample_limit_per_issue": 3,
        "finding_summary": finding_summary(issues),
        "issues": issues,
    }
    samples = {
        "schema_version": 1,
        "privacy_policy": (
            "member_name is excluded; only necessary synthetic business keys and fields "
            "are retained"
        ),
        "samples": [
            {"issue_id": issue["issue_id"], "deterministic_sample": issue["deterministic_sample"]}
            for issue in issues
        ],
    }
    treatment = {
        "schema_version": 1,
        "status": "all_dispositions_are_proposed_pending_human_acceptance",
        "allowed_detection_severities": ["INFO", "WARNING", "ERROR", "CRITICAL"],
        "allowed_proposed_dispositions": [
            "ACCEPT",
            "NORMALIZE",
            "REPAIR",
            "QUARANTINE",
            "REJECT",
        ],
        "treatments": [
            {
                "issue_id": issue["issue_id"],
                "finding_type": issue["finding_type"],
                "detection_severity": issue["detection_severity"],
                "proposed_disposition": issue["proposed_disposition"],
                "rationale": issue["rationale"],
                "pending_human_decision": issue["pending_human_decision"],
                "post_treatment_validation_proposal": issue["post_treatment_validation_proposal"],
            }
            for issue in issues
        ],
        "phase_2_candidate_decisions": {
            "currency": (
                "Preserve raw currency; normalize source-specific NTD to canonical TWD. Only "
                "TWD/NTD use exact rate 1; never COALESCE a missing rate to 1."
            ),
            "member_tracked_attributes": ["member_level", "city"],
            "same_day_member_conflict": (
                "Quarantine the entire member_id + extract_date conflict set; retain all raw "
                "snapshots and do not select by row hash or file order."
            ),
            "birth_date_change": (
                "Quarantine as identity/correction ambiguity; observed member_name and "
                "register_date change counts are zero."
            ),
            "missing_product_reference": (
                "Retain raw order; candidate Unknown Product surrogate key plus quality flag. "
                "Do not build Unknown Product in Phase 1."
            ),
            "negative_amount": (
                "Quarantine; no refund status or negative-amount semantics supplied."
            ),
            "negative_coupon_discount": "Quarantine; do not repair -1 to zero or NULL.",
            "naive_order_created_at": (
                "Normalize source-specific YYYY/MM/DD HH:MM:SS as Asia/Taipei, retain raw, "
                "and set timezone_assumed=true."
            ),
            "fx_business_date": (
                "Use Asia/Taipei date of normalized order_created_at; original amount times "
                "rate_to_twd yields TWD; coupon_discount is already TWD."
            ),
            "amount_semantics": (
                "Candidate: amount is original-currency order-line total; do not multiply "
                "quantity again during FX conversion."
            ),
        },
    }
    return {
        "source_contract.json": {"schema_version": 1, **canonical_contract()},
        "source_profile.json": source_profile,
        "issue_summary.json": issue_document,
        "analysis_summary.json": {"schema_version": 1, **analyses},
        "representative_samples.json": samples,
        "treatment_matrix.json": treatment,
    }


def _write_documents(directory: Path, documents: dict[str, object]) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    file_entries: list[dict[str, str]] = []
    bundle = hashlib.sha256()
    for file_name in CANONICAL_FILENAMES:
        content = _canonical_json(documents[file_name])
        (directory / file_name).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        file_entries.append({"file": file_name, "sha256": digest})
        bundle.update(file_name.encode("utf-8") + b"\n" + content)
    bundle_checksum = bundle.hexdigest()
    manifest = {
        "schema_version": 1,
        "algorithm": "SHA-256",
        "canonicalization": (
            "UTF-8, LF, JSON sorted keys, indent=2, trailing LF; fixed record order"
        ),
        "excluded_from_checksum": [
            "execution_time",
            "absolute_paths",
            "environment_metadata",
            "random_identifiers",
        ],
        "files": file_entries,
        "canonical_bundle_sha256": bundle_checksum,
    }
    (directory / "evidence_manifest.json").write_bytes(_canonical_json(manifest))
    return bundle_checksum


def run_profile(
    dataset_root: Path,
    sql_file: Path,
    output_dir: Path,
    evidence_dir: Path,
) -> str:
    connection = duckdb.connect(":memory:")
    try:
        file_tables = register_raw_tables(connection, dataset_root)
        profile = build_source_profile(connection, dataset_root, file_tables)
        detector_sql = load_detector_sql(sql_file)
        issues = execute_detectors(connection, detector_sql)
        analyses = execute_supporting_analyses(connection, load_analysis_sql(sql_file))
    finally:
        connection.close()
    documents = _evidence_documents(profile, issues, analyses)
    checksum = _write_documents(output_dir, documents)
    if evidence_dir.resolve() != output_dir.resolve():
        evidence_checksum = _write_documents(evidence_dir, documents)
        if evidence_checksum != checksum:
            raise RuntimeError("Output and reviewer evidence checksums differ")
    return checksum


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile immutable Part A CSV sources")
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--sql-file", type=Path, default=DEFAULT_SQL_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checksum = run_profile(args.dataset_root, args.sql_file, args.output_dir, args.evidence_dir)
    print(f"canonical_bundle_sha256={checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
