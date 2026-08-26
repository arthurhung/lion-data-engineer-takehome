from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from lion_de_exam.warehouse import build_base_warehouse


def test_actual_base_quality_gate_counts_and_reconciliation(
    phase2_warehouse: tuple[Path, Path],
) -> None:
    database, evidence = phase2_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    try:
        rule_counts = dict(
            connection.execute(
                "SELECT rule_id,count(*) FROM quality.issue_hit GROUP BY rule_id ORDER BY rule_id"
            ).fetchall()
        )
        assert rule_counts == {
            "MEM-003": 60,
            "MEM-011": 81,
            "ORD-009": 200,
            "ORD-010": 50,
            "ORD-011": 300,
            "ORD-012": 3001,
            "ORD-016": 120,
            "ORD-023": 40,
        }
        assert connection.execute(
            "SELECT count(*),count(DISTINCT order_id) FROM raw.order_event"
        ).fetchone() == (100040, 100000)
        assert connection.execute(
            "SELECT count(*) FROM quality.entity_disposition "
            "WHERE entity_type='order' AND NOT is_curated_eligible"
        ).fetchone()[0] == 388
        assert connection.execute("SELECT count(*) FROM curated.fact_order").fetchone()[0] == 99612
        assert connection.execute(
            "SELECT count(*) FROM quality.quarantine_row WHERE dataset='orders'"
        ).fetchone()[0] == 388
        manifest = json.loads((evidence / "evidence_manifest.json").read_text(encoding="utf-8"))
        assert len(manifest["canonical_bundle_sha256"]) == 64
    finally:
        connection.close()


def test_actual_dimensions_fact_flags_dates_and_referential_integrity(
    phase2_warehouse: tuple[Path, Path],
) -> None:
    database, _ = phase2_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute(
            "SELECT count(*),min(calendar_date),max(calendar_date) FROM curated.dim_date"
        ).fetchone() == (
            24405,
            connection.execute("SELECT DATE '1960-01-03'").fetchone()[0],
            connection.execute("SELECT DATE '2026-10-27'").fetchone()[0],
        )
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_product WHERE NOT is_unknown"
        ).fetchone()[0] == 300
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_product WHERE product_sk=0 AND is_unknown"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FILTER(WHERE missing_product),"
            "count(*) FILTER(WHERE missing_member_asof),"
            "count(*) FILTER(WHERE currency_normalized),"
            "count(*) FILTER(WHERE timezone_assumed) FROM curated.fact_order"
        ).fetchone() == (120, 337, 200, 2988)
        assert connection.execute(
            "SELECT count(*) FROM quality.validation_result WHERE violation_count<>0"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_actual_reviewer_facing_order_and_quality_bridges(
    phase2_warehouse: tuple[Path, Path],
) -> None:
    _, evidence = phase2_warehouse
    summary = json.loads((evidence / "model_summary.json").read_text(encoding="utf-8"))
    invariant = summary["order_invariant_bridge"]
    assert invariant["summary"] == {
        "canonical_semantic_conflicts": 0,
        "multi_event_orders": 40,
        "raw_textual_conflict_candidates": 8,
    }
    assert {
        row["field_name"]: (
            row["raw_textual_conflict_orders"],
            row["canonical_semantic_conflict_orders"],
        )
        for row in invariant["field_counts"]
    } == {
        "member_id": (0, 0),
        "product_id": (0, 0),
        "channel": (0, 0),
        "quantity": (0, 0),
        "currency": (0, 0),
        "amount": (0, 0),
        "coupon_discount": (0, 0),
        "order_created_at": (8, 0),
        "departure_date": (0, 0),
    }
    timezone_bridge = summary["timezone_assumption_bridge"]["summary"]
    assert timezone_bridge == {
        "accepted_but_not_latest_orders": 1,
        "accepted_but_not_latest_rows": 1,
        "accepted_flagged_source_rows": 2989,
        "accepted_orders_with_flagged_source": 2989,
        "fact_timezone_assumed_rows": 2988,
        "quarantined_flagged_orders": 12,
        "quarantined_flagged_source_rows": 12,
        "raw_assumption_orders": 3001,
        "raw_assumption_rows": 3001,
        "selected_flagged_fact_orders": 2988,
        "selected_flagged_fact_rows": 2988,
    }
    assert summary["entity_disposition_bridge"]["total_entities"] == 117395
    assert [
        (row["entity_type"], row["distinct_entities"])
        for row in summary["entity_disposition_bridge"]["by_entity_type"]
    ] == [
        ("order", 100000),
        ("member_snapshot", 8961),
        ("member", 8000),
        ("product", 300),
        ("fx_rate", 134),
    ]
    quarantine = summary["quarantine_reconciliation"]
    assert quarantine["summary"] == {
        "collapsed_source_rule_links": 31,
        "entity_rule_links": 3821,
        "issue_hit_source_rule_links": 3852,
        "quarantine_physical_rows": 448,
        "quarantined_orders": 388,
    }
    assert quarantine["quarantined_multi_event_orders"] == 0


def test_exact_duplicate_latest_conflicts_unknown_keys_and_money(
    synthetic_phase2_warehouse: Path,
) -> None:
    connection = duckdb.connect(str(synthetic_phase2_warehouse), read_only=True)
    try:
        assert connection.execute(
            "SELECT duplicate_source_row_count FROM curated.fact_order WHERE order_id='ORD00000001'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM curated.fact_order "
            "WHERE order_id IN ('ORD00000002','ORD00000003')"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT order_status FROM curated.fact_order WHERE order_id='ORD00000004'"
        ).fetchone()[0] == "paid"
        assert connection.execute(
            "SELECT product_sk,missing_product,price_check_not_evaluable "
            "FROM curated.fact_order WHERE order_id='ORD00000005'"
        ).fetchone() == (0, True, True)
        assert connection.execute(
            "SELECT count(*) FROM curated.fact_order "
            "WHERE order_id IN ('ORD00000011','ORD00000012','ORD00000013','ORD00000014')"
        ).fetchone()[0] == 0
        currencies = connection.execute(
            "SELECT order_id,normalized_currency,rate_to_twd,gross_amount_twd "
            "FROM curated.fact_order WHERE order_id BETWEEN 'ORD00000008' AND 'ORD00000010' "
            "ORDER BY order_id"
        ).fetchall()
        assert [(row[0], row[1], str(row[2]), str(row[3])) for row in currencies] == [
            ("ORD00000008", "TWD", "1.00000000", "100.00"),
            ("ORD00000009", "USD", "2.00000000", "100.00"),
            ("ORD00000010", "JPY", "0.20000000", "100.00"),
        ]
        rounded = connection.execute(
            "SELECT gross_amount_twd_exact,gross_amount_twd FROM curated.fact_order "
            "WHERE order_id='ORD00000015'"
        ).fetchone()
        assert str(rounded[0]) == "100.005000000000"
        assert str(rounded[1]) == "100.01"
        assert connection.execute(
            "SELECT order_status,status_transition_warning FROM curated.fact_order "
            "WHERE order_id='ORD00000016'"
        ).fetchone() == ("paid", True)
        assert connection.execute(
            "SELECT quantity,gross_amount_twd FROM curated.fact_order "
            "WHERE order_id='ORD00000017'"
        ).fetchone() == (2, duckdb.execute("SELECT 100.00::DECIMAL(28,2)").fetchone()[0])
        synthetic_rules = dict(
            connection.execute(
                "SELECT rule_id,count(*) FROM quality.issue_hit GROUP BY rule_id ORDER BY rule_id"
            ).fetchall()
        )
        assert synthetic_rules["ORD-001"] == 2
        assert synthetic_rules["ORD-003"] == 2
        assert synthetic_rules["ORD-004"] == 6
        assert synthetic_rules["ORD-010"] == 1
        assert synthetic_rules["ORD-011"] == 1
        assert synthetic_rules["ORD-017"] == 1
        assert synthetic_rules["ORD-018"] == 1
        assert synthetic_rules["ORD-023"] == 1
        assert connection.execute(
            "SELECT round(1.005::DECIMAL(10,3),2)"
        ).fetchone()[0] == duckdb.execute("SELECT 1.01::DECIMAL(10,2)").fetchone()[0]
    finally:
        connection.close()


def test_timestamp_representations_use_canonical_instants_for_conflict_gate(
    synthetic_phase2_warehouse: Path,
) -> None:
    connection = duckdb.connect(str(synthetic_phase2_warehouse), read_only=True)
    try:
        invariant_counts = dict(
            connection.execute(
                "SELECT order_id,count(DISTINCT invariant_hash) "
                "FROM staging.order_event "
                "WHERE order_id BETWEEN 'ORD00000018' AND 'ORD00000020' "
                "GROUP BY order_id ORDER BY order_id"
            ).fetchall()
        )
        assert invariant_counts == {
            "ORD00000018": 1,
            "ORD00000019": 1,
            "ORD00000020": 2,
        }
        assert connection.execute(
            "SELECT count(*) FROM quality.entity_rule "
            "WHERE rule_id='ORD-004' AND business_key IN ('ORD00000018','ORD00000019')"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM quality.entity_rule "
            "WHERE rule_id='ORD-004' AND business_key='ORD00000020'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM curated.fact_order "
            "WHERE order_id IN ('ORD00000018','ORD00000019')"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM curated.fact_order WHERE order_id='ORD00000020'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_source_allowlist_excludes_incremental_files(
    phase2_warehouse: tuple[Path, Path],
) -> None:
    database, _ = phase2_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    try:
        files = {
            row[0]
            for row in connection.execute(
                "SELECT source_file FROM raw.order_event "
                "UNION SELECT source_file FROM raw.member_snapshot "
                "UNION SELECT source_file FROM raw.product "
                "UNION SELECT source_file FROM raw.fx_rate"
            ).fetchall()
        }
        assert files == {"orders_base.csv", "members.csv", "products.csv", "fx_rates.csv"}
        assert all("incremental" not in file_name for file_name in files)
    finally:
        connection.close()


def test_two_clean_base_builds_have_byte_identical_canonical_evidence(
    phase2_warehouse: tuple[Path, Path], tmp_path: Path
) -> None:
    _, first_evidence = phase2_warehouse
    second_database = tmp_path / "second.duckdb"
    second_evidence = tmp_path / "evidence"
    checksum = build_base_warehouse(second_database, evidence_dir=second_evidence)
    first_manifest = json.loads(
        (first_evidence / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert checksum == first_manifest["canonical_bundle_sha256"]
    for file_name in ("model_summary.json", "validation_summary.json", "evidence_manifest.json"):
        first_bytes = (first_evidence / file_name).read_bytes()
        second_bytes = (second_evidence / file_name).read_bytes()
        assert first_bytes == second_bytes
    combined = b"".join(path.read_bytes() for path in sorted(second_evidence.iterdir()))
    assert b"ingested_at" not in combined
    assert b"/Users/" not in combined
    assert b"execution_time" not in combined


def test_failed_build_does_not_leave_partial_database(tmp_path: Path) -> None:
    database = tmp_path / "partial.duckdb"
    empty_dataset = tmp_path / "empty-dataset"
    empty_dataset.mkdir()
    with pytest.raises(FileNotFoundError):
        build_base_warehouse(database, dataset_root=empty_dataset)
    assert not database.exists()
