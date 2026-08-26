from __future__ import annotations

import json
from pathlib import Path

import duckdb

from lion_de_exam.profiling import DEFAULT_DATASET_ROOT, DEFAULT_SQL_FILE
from lion_de_exam.quality import execute_detectors, load_detector_sql, register_raw_tables
from lion_de_exam.quality_catalog import DETECTORS

EXPECTED_NONZERO_COUNTS = {
    "MEM-002": (60, 30),
    "MEM-003": (60, 30),
    "MEM-009": (38, 19),
    "MEM-010": (804, 803),
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
    assert finding_types["ORD-002"] == "EXPECTED_CONDITION"
    assert finding_types["ORD-022"] == "EXPECTED_CONDITION"
    assert finding_types["MEM-010"] == "EXPECTED_CONDITION"
    assert finding_types["ORD-004"] == "DATA_QUALITY_ISSUE"
    assert finding_types["ORD-024"] == "CONTROL_CHECK"


def test_samples_exclude_member_names_and_use_relative_source_names() -> None:
    results = execute_all_detectors()
    samples = json.dumps([result["deterministic_sample"] for result in results], ensure_ascii=False)

    assert "member_name" not in samples
    assert str(Path.cwd()) not in samples
    assert "/Users/" not in samples
    for result in results:
        assert len(result["deterministic_sample"]) <= 3


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
        "detector_total": 46,
        "nonzero_detector_result_count": 14,
        "candidate_data_quality_issue_count": 11,
        "expected_condition_count": 3,
        "zero_result_control_check_count": 32,
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
