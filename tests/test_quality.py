from __future__ import annotations

import json
from pathlib import Path

import duckdb

from lion_de_exam.profiling import DEFAULT_DATASET_ROOT, DEFAULT_SQL_FILE
from lion_de_exam.quality import (
    execute_detectors,
    load_analysis_sql,
    load_detector_sql,
    register_raw_tables,
)
from lion_de_exam.quality_catalog import DETECTOR_BY_ID, DETECTORS

EXPECTED_NONZERO_COUNTS = {
    "MEM-002": (60, 30),
    "MEM-003": (60, 30),
    "MEM-010": (804, 803),
    "MEM-011": (81, 80),
    "ORD-002": (3799, 1889),
    "ORD-004": (3613, 1796),
    "ORD-009": (200, 200),
    "ORD-010": (50, 50),
    "ORD-011": (300, 300),
    "ORD-012": (3001, 3001),
    "ORD-016": (120, 120),
    "ORD-018": (368, 366),
    "ORD-022": (1893, 1873),
    "ORD-023": (40, 40),
}


def execute_all_detectors() -> list[dict[str, object]]:
    connection = duckdb.connect(":memory:")
    try:
        register_raw_tables(connection, DEFAULT_DATASET_ROOT)
        return execute_detectors(connection, load_detector_sql(DEFAULT_SQL_FILE))
    finally:
        connection.close()


def create_raw_members(connection: duckdb.DuckDBPyConnection, rows: str) -> None:
    connection.execute(
        "CREATE TEMP TABLE raw_members AS SELECT * FROM (VALUES "
        + rows
        + ") AS source(member_id, member_name, member_level, city, birth_date, "
        "register_date, extract_date, source_file, batch_order, source_row_number)"
    )


def create_raw_orders(connection: duckdb.DuckDBPyConnection, rows: str) -> None:
    connection.execute(
        "CREATE TEMP TABLE raw_orders AS SELECT * FROM (VALUES "
        + rows
        + ") AS source(order_id, member_id, product_id, channel, order_status, quantity, "
        "currency, amount, coupon_discount, order_created_at, departure_date, updated_at, "
        "source_file, batch_order, source_row_number)"
    )


def test_detector_ids_are_unique_and_match_executable_sql() -> None:
    catalog_ids = [item.issue_id for item in DETECTORS]
    sql_ids = list(load_detector_sql(DEFAULT_SQL_FILE))

    assert len(catalog_ids) == len(set(catalog_ids))
    assert set(catalog_ids) == set(sql_ids)


def test_detector_result_schema_counts_and_zero_results_are_stable() -> None:
    results = execute_all_detectors()

    assert [item["issue_id"] for item in results] == sorted(item["issue_id"] for item in results)
    assert len(results) == len(DETECTORS)
    for result in results:
        issue_id = str(result["issue_id"])
        expected = EXPECTED_NONZERO_COUNTS.get(issue_id, (0, 0))
        assert (result["affected_row_count"], result["affected_business_key_count"]) == expected
        assert set(result) == {
            "issue_id",
            "dataset",
            "description",
            "detector",
            "affected_row_count",
            "affected_business_key_count",
            "finding_type",
            "deterministic_sample",
            "business_impact",
            "detection_severity",
            "proposed_disposition",
            "disposition_status",
            "rationale",
            "pending_human_decision",
            "post_treatment_validation_proposal",
        }

    finding_types = {item["issue_id"]: item["finding_type"] for item in results}
    disposition_statuses = {
        item["issue_id"]: item["disposition_status"] for item in results
    }
    assert finding_types["ORD-002"] == "EXPECTED_CONDITION"
    assert finding_types["ORD-022"] == "EXPECTED_CONDITION"
    assert finding_types["MEM-010"] == "EXPECTED_CONDITION"
    assert finding_types["ORD-004"] == "DATA_QUALITY_ISSUE"
    assert finding_types["ORD-024"] == "CONTROL_CHECK"
    assert finding_types["MEM-009"] == "CONTROL_CHECK"
    assert finding_types["MEM-011"] == "DATA_QUALITY_ISSUE"
    for issue_id in ("MEM-009", "MEM-011", "ORD-001", "ORD-003"):
        assert disposition_statuses[issue_id] == "human_approved_phase_1_correction_policy"


def test_samples_exclude_member_names_and_use_relative_source_names() -> None:
    results = execute_all_detectors()
    samples = json.dumps([result["deterministic_sample"] for result in results], ensure_ascii=False)

    assert "member_name" not in samples
    assert str(Path.cwd()) not in samples
    assert "/Users/" not in samples
    for result in results:
        assert len(result["deterministic_sample"]) <= 3
        if result["issue_id"] == "MEM-011":
            allowed = {
                "member_id",
                "extract_date",
                "birth_date_sentinel",
                "non_sentinel_birth_date_count",
                "source_file",
                "source_row_number",
            }
            assert all(set(sample) <= allowed for sample in result["deterministic_sample"])


def test_severity_and_disposition_are_separate_proposed_fields() -> None:
    severities = {"INFO", "WARNING", "ERROR", "CRITICAL"}
    dispositions = {"ACCEPT", "NORMALIZE", "REPAIR", "QUARANTINE", "REJECT"}

    for item in DETECTORS:
        assert item.detection_severity in severities
        assert item.proposed_disposition in dispositions
        assert item.detection_severity not in dispositions
        assert item.proposed_disposition not in severities


def test_field_breakdowns_and_amount_semantics_match_observed_evidence() -> None:
    issue_summary = json.loads(
        Path("docs/evidence/phase_01/issue_summary.json").read_text(encoding="utf-8")
    )
    assert issue_summary["finding_summary"] == {
        "detector_total": 47,
        "nonzero_detector_result_count": 14,
        "candidate_data_quality_issue_count": 11,
        "expected_condition_count": 3,
        "zero_result_control_check_count": 33,
    }
    analysis = json.loads(
        Path("docs/evidence/phase_01/analysis_summary.json").read_text(encoding="utf-8")
    )
    invariants = {
        item["field_name"]: (item["affected_order_count"], item["affected_event_row_count"])
        for item in analysis["order_invariant_field_breakdown"]
    }
    assert invariants == {
        "member_id": (1788, 3597),
        "product_id": (1783, 3587),
        "channel": (1350, 2716),
        "quantity": (1350, 2718),
        "currency": (883, 1778),
        "amount": (1788, 3597),
        "coupon_discount": (1691, 3403),
        "order_created_at": (1796, 3613),
        "departure_date": (1773, 3567),
    }
    identity = {
        item["field_name"]: (
            item["affected_member_count"],
            item["affected_snapshot_row_count"],
        )
        for item in analysis["member_identity_field_breakdown"]
    }
    assert identity == {
        "member_name": (0, 0),
        "birth_date": (19, 38),
        "register_date": (0, 0),
    }
    timestamps = {
        item["field_name"]: (item["affected_order_count"], item["affected_event_row_count"])
        for item in analysis["timestamp_format_field_breakdown"]
    }
    assert timestamps == {"order_created_at": (3001, 3001), "updated_at": (0, 0)}

    transitions = analysis["status_transition_pair_breakdown"]
    transition_keys = [(item["from_status"], item["to_status"]) for item in transitions]
    assert transition_keys == sorted(transition_keys)
    transition_counts = {
        (item["from_status"], item["to_status"]): (
            item["event_count"],
            item["affected_order_count"],
        )
        for item in transitions
    }
    assert transition_counts == {
        ("cancelled", "cancelled"): (121, 120),
        ("cancelled", "completed"): (122, 122),
        ("cancelled", "paid"): (4, 4),
        ("completed", "cancelled"): (238, 238),
        ("completed", "completed"): (265, 262),
        ("completed", "created"): (1, 1),
        ("completed", "paid"): (3, 3),
        ("created", "cancelled"): (146, 146),
        ("created", "completed"): (147, 147),
        ("created", "created"): (22, 22),
        ("paid", "cancelled"): (407, 407),
        ("paid", "completed"): (402, 402),
        ("paid", "paid"): (32, 32),
    }

    amount = analysis["amount_semantic_analysis"]
    distributions = {item["comparison_basis"]: item for item in amount["distributions"]}
    assert distributions["amount_twd/(base_price_twd*quantity)"]["median_ratio"] == ("1.04953901")
    assert distributions["amount_twd/base_price_twd"]["median_ratio"] == "2.49846026"
    assert distributions["amount_twd/(base_price_twd*quantity)"]["extreme_row_count"] == 40
    assert amount["outlier_threshold"] == {
        "inclusive_minimum": "0.50000000",
        "inclusive_maximum": "2.00000000",
    }
    assert amount["amount_twd_formula"] == "DECIMAL(amount) * DECIMAL(rate_to_twd)"
    assert amount["outlier_basis"] == "amount_twd/(base_price_twd*quantity)"

    birth = analysis["birth_date_semantic_analysis"]
    assert birth["sentinel_affected_row_count"] == 81
    assert birth["sentinel_affected_member_count"] == 80
    assert birth["only_sentinel_member_count"] == 61
    assert birth["sentinel_plus_single_non_sentinel_member_count"] == 19
    assert birth["multiple_distinct_non_sentinel_member_count"] == 0
    assert birth["non_sentinel_observed_min"] == "1960-01-03"
    assert birth["non_sentinel_observed_max"] == "2003-10-17"


def test_sentinel_only_and_sentinel_plus_one_date_are_not_identity_ambiguity() -> None:
    detectors = load_detector_sql(DEFAULT_SQL_FILE)
    connection = duckdb.connect(":memory:")
    try:
        create_raw_members(
            connection,
            "('M000001','測試甲','一般','台北市','1900-01-01','2020-01-01',"
            "'2026-04-30','members.csv',0,1),"
            "('M000002','測試乙','一般','台北市','1900-01-01','2020-01-01',"
            "'2026-04-30','members.csv',0,2),"
            "('M000002','測試乙','一般','台北市','1980-01-01','2020-01-01',"
            "'2026-05-31','members.csv',0,3)",
        )
        assert connection.execute(detectors["MEM-009"]).fetchall() == []
        sentinel_rows = connection.execute(detectors["MEM-011"]).fetchall()
        assert len(sentinel_rows) == 2
        assert {row[0] for row in sentinel_rows} == {"M000001", "M000002"}
    finally:
        connection.close()


def test_two_distinct_non_sentinel_birth_dates_quarantine_member() -> None:
    detector_sql = load_detector_sql(DEFAULT_SQL_FILE)["MEM-009"]
    connection = duckdb.connect(":memory:")
    try:
        create_raw_members(
            connection,
            "('M000003','測試丙','一般','台北市','1980-01-01','2020-01-01',"
            "'2026-04-30','members.csv',0,1),"
            "('M000003','測試丙','一般','台北市','1981-01-01','2020-01-01',"
            "'2026-05-31','members.csv',0,2)",
        )
        rows = connection.execute(detector_sql).fetchall()
        assert len(rows) == 2
        assert {row[0] for row in rows} == {"M000003"}
        assert DETECTOR_BY_ID["MEM-009"].proposed_disposition == "QUARANTINE"
    finally:
        connection.close()


def test_exact_duplicate_canonical_dedup_does_not_quarantine_order() -> None:
    detectors = load_detector_sql(DEFAULT_SQL_FILE)
    analyses = load_analysis_sql(DEFAULT_SQL_FILE)
    connection = duckdb.connect(":memory:")
    try:
        row = (
            "('ORD00000001','M000001','P00001','web','paid','1','TWD','1000','0',"
            "'2026-05-01T10:00:00+08:00','2026-06-01','2026-05-01T10:01:00+08:00',"
            "'orders_base.csv',0,1)"
        )
        duplicate = row[:-2] + "2)"
        create_raw_orders(connection, row + "," + duplicate)

        assert len(connection.execute(detectors["ORD-001"]).fetchall()) == 2
        assert connection.execute(detectors["ORD-003"]).fetchall() == []
        assert connection.execute(
            analyses["ORD-001-EXACT-DUPLICATE-POLICY"]
        ).fetchall() == [("ORD00000001", "2026-05-01T10:01:00+08:00", 2, 1, 1)]
        assert DETECTOR_BY_ID["ORD-001"].proposed_disposition == "NORMALIZE"
    finally:
        connection.close()


def test_same_timestamp_conflicting_payload_quarantines_order() -> None:
    detector_sql = load_detector_sql(DEFAULT_SQL_FILE)["ORD-003"]
    connection = duckdb.connect(":memory:")
    try:
        create_raw_orders(
            connection,
            "('ORD00000001','M000001','P00001','web','paid','1','TWD','1000','0',"
            "'2026-05-01T10:00:00+08:00','2026-06-01','2026-05-01T10:01:00+08:00',"
            "'orders_base.csv',0,1),"
            "('ORD00000001','M000001','P00001','web','completed','1','TWD','1000','0',"
            "'2026-05-01T10:00:00+08:00','2026-06-01','2026-05-01T10:01:00+08:00',"
            "'orders_base.csv',0,2)",
        )
        rows = connection.execute(detector_sql).fetchall()
        assert len(rows) == 2
        assert {row[0] for row in rows} == {"ORD00000001"}
        assert DETECTOR_BY_ID["ORD-003"].proposed_disposition == "QUARANTINE"
    finally:
        connection.close()
