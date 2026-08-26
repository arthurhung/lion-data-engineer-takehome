from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb


def test_actual_member_scd2_invariants_and_sentinel_results(
    phase2_warehouse: tuple[Path, Path],
) -> None:
    database, _ = phase2_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute(
            "SELECT count(*) FROM quality.validation_result WHERE violation_count<>0"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM staging.member_snapshot WHERE birth_date_sentinel"
        ).fetchone()[0] == 81
        assert connection.execute(
            "SELECT count(DISTINCT member_id) FROM staging.member_snapshot "
            "WHERE birth_date_sentinel"
        ).fetchone()[0] == 80
        assert connection.execute(
            "SELECT count(DISTINCT member_id) FROM staging.member_snapshot "
            "WHERE birth_date_unknown"
        ).fetchone()[0] == 61
        assert connection.execute(
            "SELECT count(DISTINCT member_id) FROM staging.member_snapshot "
            "WHERE birth_date_restatement"
        ).fetchone()[0] == 19
        assert connection.execute(
            "SELECT count(DISTINCT member_id) FROM staging.member_snapshot "
            "WHERE birth_date_identity_ambiguous"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member WHERE NOT is_unknown"
        ).fetchone()[0] == 8745
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member WHERE is_current AND NOT is_unknown"
        ).fetchone()[0] == 7972
    finally:
        connection.close()


def test_actual_member_scd2_reconciliation_bridge(
    phase2_warehouse: tuple[Path, Path],
) -> None:
    _, evidence = phase2_warehouse
    summary = json.loads((evidence / "model_summary.json").read_text(encoding="utf-8"))
    bridge = summary["member_scd2_bridge"]
    assert bridge["summary"] == {
        "accepted_lineage_rows": 8931,
        "conflict_members_restarted_later": 2,
        "conflict_members_without_reliable_version": 28,
        "current_members": 7972,
        "known_versions": 8745,
        "raw_snapshot_rows": 8991,
        "represented_members": 7972,
        "same_day_conflict_raw_rows": 60,
        "same_day_conflict_snapshot_entities": 30,
        "unchanged_snapshot_lineage_rows": 186,
        "unknown_member_facts": 337,
        "unknown_member_source_ids": 30,
    }
    assert bridge["unknown_fact_reason_breakdown"] == [
        {"fact_rows": 323, "reason": "no_reliable_version", "source_member_ids": 28},
        {
            "fact_rows": 14,
            "reason": "uncertainty_gap_before_restart",
            "source_member_ids": 2,
        },
    ]


def test_sentinel_restatement_identity_ambiguity_and_identical_snapshot_dedup(
    synthetic_phase2_warehouse: Path,
) -> None:
    connection = duckdb.connect(str(synthetic_phase2_warehouse), read_only=True)
    try:
        member1 = connection.execute(
            "SELECT birth_date,birth_date_sentinel,birth_date_unknown,birth_date_restatement,"
            "count(*) OVER () FROM curated.dim_member WHERE member_id='M000001'"
        ).fetchone()
        assert member1 == (date(1980, 1, 2), True, False, True, 1)
        assert connection.execute(
            "SELECT birth_date IS NULL,birth_date_unknown FROM curated.dim_member "
            "WHERE member_id='M000002'"
        ).fetchone() == (True, True)
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member WHERE member_id='M000003'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member WHERE member_id='M000004'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member_lineage l "
            "JOIN curated.dim_member d USING(member_sk) "
            "WHERE d.member_id='M000004'"
        ).fetchone()[0] == 2
    finally:
        connection.close()


def test_change_snapshots_uncertainty_gap_boundaries_and_null_safe_hash(
    synthetic_phase2_warehouse: Path,
) -> None:
    connection = duckdb.connect(str(synthetic_phase2_warehouse), read_only=True)
    try:
        periods = connection.execute(
            "SELECT valid_from,valid_to,is_current FROM curated.dim_member "
            "WHERE member_id='M000005' ORDER BY valid_from"
        ).fetchall()
        assert [(str(a), str(b), c) for a, b, c in periods] == [
            ("2026-04-30", "2026-05-31", False),
            ("2026-06-30", "9999-12-31", True),
        ]
        assert connection.execute(
            "SELECT member_sk=0,missing_member_asof FROM curated.fact_order "
            "WHERE order_id='ORD00000006'"
        ).fetchone() == (True, True)
        assert connection.execute(
            "SELECT member_sk<>0,missing_member_asof FROM curated.fact_order "
            "WHERE order_id='ORD00000007'"
        ).fetchone() == (True, False)
        assert connection.execute(
            "SELECT count(DISTINCT version_hash) FROM staging.member_snapshot "
            "WHERE member_id='M000006'"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member WHERE member_id='M000006'"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT sha256(to_json(struct_pack(schema_version:='member-state-v1',"
            "member_level:=coalesce(NULL,'<NULL>'),city:=coalesce(NULL,'<NULL>')))) <> "
            "sha256(to_json(struct_pack(schema_version:='member-state-v1',"
            "member_level:=coalesce('一般','<NULL>'),city:=coalesce(NULL,'<NULL>'))))"
        ).fetchone()[0]
    finally:
        connection.close()


def test_member_sk_is_deterministic_and_future_version_does_not_change_existing(
    synthetic_phase2_warehouse: Path,
) -> None:
    connection = duckdb.connect(str(synthetic_phase2_warehouse), read_only=True)
    try:
        existing = connection.execute(
            "SELECT member_sk FROM curated.dim_member "
            "WHERE member_id='M000006' AND valid_from=DATE '2026-04-30'"
        ).fetchone()[0]
        recomputed = connection.execute(
            "SELECT cast('0x'||substr(sha256('dim_member|v1|M000006|2026-04-30'),1,15) AS BIGINT)"
        ).fetchone()[0]
        future = connection.execute(
            "SELECT cast('0x'||substr(sha256('dim_member|v1|M000006|2026-07-31'),1,15) AS BIGINT)"
        ).fetchone()[0]
        assert existing == recomputed
        assert future != existing
        assert existing > 0 and future > 0
    finally:
        connection.close()
