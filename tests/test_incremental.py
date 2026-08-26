from __future__ import annotations

import csv
import hashlib
import shutil
from pathlib import Path

import duckdb
import pytest

from lion_de_exam.incremental import (
    BATCHES,
    current_state_checksum,
    initialize_phase3,
    inspect_csv,
    process_order_batch,
    refresh_member_projection,
    run_all,
)
from lion_de_exam.warehouse import DEFAULT_DATASET_ROOT

ORDER_HEADER = [
    "order_id","member_id","product_id","channel","order_status","quantity","currency",
    "amount","coupon_discount","order_created_at","departure_date","updated_at",
]


def _write(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _order(
    order_id: str,
    *,
    member: str = "M000001",
    product: str = "P00001",
    status: str = "paid",
    quantity: str = "1",
    currency: str = "TWD",
    amount: str = "100.0000",
    created: str = "2026-05-01T08:00:00+08:00",
    updated: str = "2026-05-01T09:00:00+08:00",
) -> list[object]:
    return [
        order_id,member,product,"web",status,quantity,currency,amount,"0.0000",created,
        "2026-07-10",updated,
    ]


@pytest.fixture()
def incremental_dataset(tmp_path: Path) -> Path:
    data = tmp_path / "dataset"
    data.mkdir()
    _write(
        data / "members.csv",
        ["member_id","member_name","member_level","city","birth_date","register_date","extract_date"],
        [
            ["M000001","Member 1","一般","台北","1980-01-01","2020-01-01","2026-04-30"],
            ["M000002","Member 2","一般","台北","1980-01-02","2020-01-01","2026-04-30"],
            ["M000003","Member 3","一般","台北","1980-01-03","2020-01-01","2026-04-30"],
            ["M000004","Member 4","一般","台北","1980-01-04","2020-01-01","2026-04-30"],
            ["M000005","Member 5","一般","台北","1980-01-05","2020-01-01","2026-04-30"],
        ],
    )
    _write(
        data / "products.csv",
        ["product_id","product_name","product_type","destination_country","destination_city","trip_days","base_price_twd","is_active"],
        [["P00001","Product","tour","TW","Taipei","1","100.0000","Y"]],
    )
    fx = []
    for day in ("2026-05-01","2026-07-01","2026-07-02","2026-07-03"):
        fx.extend([[day,"USD","2.00000000"],[day,"JPY","0.20000000"]])
    _write(data / "fx_rates.csv", ["rate_date","currency","rate_to_twd"], fx)
    equivalent_utc = _order(
        "ORD00000003",created="2026-05-01T00:00:00Z",updated="2026-05-01T09:00:00+08:00"
    )
    equivalent_offset = _order(
        "ORD00000003",created="2026-05-01T08:00:00+08:00",updated="2026-05-01T10:00:00+08:00"
    )
    late_base = _order("ORD00000002",updated="2026-07-02T09:00:00+08:00")
    base_rows = [_order("ORD00000001"),late_base,equivalent_utc,equivalent_offset]
    _write(data / "orders_base.csv", ORDER_HEADER, base_rows)
    day1_rows = [
        _order("ORD00000001",member="M000002",updated="2026-07-01T10:00:00+08:00"),
        _order("ORD00000002",updated="2026-07-01T10:00:00+08:00"),
        _order(
            "ORD00000004",created="2026-07-01T08:00:00+08:00",
            updated="2026-07-01T09:00:00+08:00",
        ),
        base_rows[0],
    ]
    _write(data / BATCHES[1].file_name, ORDER_HEADER, day1_rows)
    _write(
        data / BATCHES[2].file_name,
        ORDER_HEADER,
        [_order(
            "ORD00000005",quantity="2",created="2026-07-02T08:00:00+08:00",
            updated="2026-07-02T09:00:00+08:00",
        )],
    )
    _write(
        data / BATCHES[3].file_name,
        ORDER_HEADER,
        [_order(
            "ORD00000006",currency="USD",amount="50.0000",
            created="2026-07-03T08:00:00+08:00",updated="2026-07-03T09:00:00+08:00",
        )],
    )
    return data


def _counts(database: Path) -> tuple[int, int, int, int, int]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        return connection.execute(
            "SELECT (SELECT count(*) FROM raw.order_event),"
            "(SELECT count(*) FROM curated.fact_order),"
            "(SELECT count(*) FROM curated.dim_member),"
            "(SELECT count(*) FROM quality.quarantine_row),"
            "(SELECT count(*) FROM audit.batch_reconciliation)"
        ).fetchone()
    finally:
        connection.close()


def test_replay_order_lineage_late_conflict_and_decimal_semantics(
    incremental_dataset: Path, tmp_path: Path
) -> None:
    database = tmp_path / "phase3.duckdb"
    results = run_all(database, incremental_dataset)
    assert [item["status"] for item in results] == ["SUCCEEDED"] * 4
    before = current_state_checksum(database)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute(
            "SELECT count(*) FROM curated.fact_order WHERE order_id='ORD00000001'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM quality.entity_rule "
            "WHERE entity_type='order' AND business_key='ORD00000001' AND rule_id='ORD-004'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT updated_at FROM curated.fact_order WHERE order_id='ORD00000002'"
        ).fetchone()[0] == connection.execute(
            "SELECT TIMESTAMPTZ '2026-07-02T09:00:00+08:00'"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT count(*) FROM quality.issue_hit WHERE rule_id='INC-001'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*),count(DISTINCT canonical_event_hash),"
            "sum(is_lineage_representative::INTEGER) FROM staging.order_event_lineage "
            "WHERE canonical_event_hash=(SELECT canonical_event_hash FROM staging.order_event "
            "WHERE order_id='ORD00000001' AND source_file='orders_base.csv')"
        ).fetchone() == (2, 1, 1)
        assert connection.execute(
            "SELECT count(DISTINCT invariant_hash) FROM staging.order_event "
            "WHERE order_id='ORD00000003'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT quantity,gross_amount_twd FROM curated.fact_order WHERE order_id='ORD00000005'"
        ).fetchone() == (2, connection.execute("SELECT 100.00::DECIMAL(28,2)").fetchone()[0])
    finally:
        connection.close()

    replay = process_order_batch(
        database, BATCHES[1], incremental_dataset / BATCHES[1].file_name
    )
    assert replay["status"] == "SKIPPED_ALREADY_APPLIED"
    assert current_state_checksum(database) == before
    connection = duckdb.connect(str(database), read_only=True)
    try:
        reconciliation_count = connection.execute(
            "SELECT count(*) FROM audit.batch_reconciliation"
        ).fetchone()[0]
        assert reconciliation_count == 4
    finally:
        connection.close()

    with (incremental_dataset / "members.csv").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="same SHA-256"):
        run_all(database, incremental_dataset)


def test_strict_order_different_hash_and_failed_batch_rollback(
    incremental_dataset: Path, tmp_path: Path
) -> None:
    database = tmp_path / "phase3.duckdb"
    initialize_phase3(database, incremental_dataset)
    with pytest.raises(ValueError, match="strict next"):
        process_order_batch(database, BATCHES[2], incremental_dataset / BATCHES[2].file_name)
    process_order_batch(database, BATCHES[1], incremental_dataset / BATCHES[1].file_name)
    before = _counts(database)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        process_order_batch(
            database,
            BATCHES[2],
            incremental_dataset / BATCHES[2].file_name,
            fail_after_refresh=True,
        )
    assert _counts(database) == before

    altered_day2_dir = tmp_path / "altered-day2"
    altered_day2_dir.mkdir()
    altered_day2 = altered_day2_dir / BATCHES[2].file_name
    shutil.copy2(incremental_dataset / BATCHES[2].file_name, altered_day2)
    with altered_day2.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="previously attempted with different SHA-256"):
        process_order_batch(database, BATCHES[2], altered_day2)
    assert _counts(database) == before

    process_order_batch(database, BATCHES[2], incremental_dataset / BATCHES[2].file_name)
    altered_dir = tmp_path / "altered"
    altered_dir.mkdir()
    altered = altered_dir / BATCHES[1].file_name
    shutil.copy2(incremental_dataset / BATCHES[1].file_name, altered)
    with altered.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="different SHA-256"):
        process_order_batch(database, BATCHES[1], altered)


def test_stale_attempt_locks_file_identity(
    incremental_dataset: Path, tmp_path: Path
) -> None:
    database = tmp_path / "phase3.duckdb"
    initialize_phase3(database, incremental_dataset)
    process_order_batch(database, BATCHES[1], incremental_dataset / BATCHES[1].file_name)
    metadata = inspect_csv(incremental_dataset / BATCHES[2].file_name, tuple(ORDER_HEADER))
    connection = duckdb.connect(str(database))
    try:
        connection.execute(
            "INSERT INTO audit.batch_attempt(batch_order,source_file,file_sha256,status) "
            "VALUES (?,?,?,'RUNNING')",
            [BATCHES[2].order, BATCHES[2].file_name, metadata.file_sha256],
        )
    finally:
        connection.close()

    altered_dir = tmp_path / "stale-altered"
    altered_dir.mkdir()
    altered = altered_dir / BATCHES[2].file_name
    shutil.copy2(incremental_dataset / BATCHES[2].file_name, altered)
    with altered.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="previously attempted with different SHA-256"):
        process_order_batch(database, BATCHES[2], altered)

    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute(
            "SELECT status FROM audit.batch_attempt WHERE source_file=? "
            "ORDER BY attempt_id DESC LIMIT 1",
            [BATCHES[2].file_name],
        ).fetchone()[0] == "INTERRUPTED"
    finally:
        connection.close()
    result = process_order_batch(
        database, BATCHES[2], incremental_dataset / BATCHES[2].file_name
    )
    assert result["status"] == "SUCCEEDED"


def _insert_member(
    connection: duckdb.DuckDBPyConnection,
    member_id: str,
    name: str,
    level: str,
    city: str | None,
    extract_date: str,
    row_number: int,
) -> None:
    payload = f"{member_id}|{name}|{level}|{city}|{extract_date}"
    row_hash = hashlib.sha256(payload.encode()).hexdigest()
    uid = hashlib.sha256(f"members_incremental.csv|{row_number}|{row_hash}".encode()).hexdigest()
    birth_date = f"1980-01-{int(member_id[-1]):02d}"
    connection.execute(
        "INSERT INTO raw.member_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            member_id,name,level,city,birth_date,"2020-01-01",extract_date,
            "members_incremental.csv",row_number,1,row_hash,uid,
            connection.execute("SELECT current_timestamp").fetchone()[0],
        ],
    )


def test_synthetic_incremental_member_scd2(incremental_dataset: Path, tmp_path: Path) -> None:
    database = tmp_path / "phase3.duckdb"
    initialize_phase3(database, incremental_dataset)
    connection = duckdb.connect(str(database))
    try:
        connection.execute("BEGIN TRANSACTION")
        _insert_member(connection,"M000001","Member 1","銀卡","台北","2026-07-31",1)
        _insert_member(connection,"M000002","Renamed","一般","台北","2026-07-31",2)
        _insert_member(connection,"M000003","Member 3","一般","台北","2026-07-31",3)
        _insert_member(connection,"M000005","Member 5","銀卡","台北","2026-07-31",4)
        _insert_member(connection,"M000005","Member 5","金卡","台中","2026-07-31",5)
        _insert_member(connection,"M000005","Member 5","白金","高雄","2026-08-31",6)
        refresh_member_projection(connection)
        connection.execute("COMMIT")

        assert connection.execute(
            "SELECT valid_from,valid_to,is_current FROM curated.dim_member "
            "WHERE member_id='M000001' ORDER BY valid_from"
        ).fetchall() == [
            (connection.execute("SELECT DATE '2026-04-30'").fetchone()[0],
             connection.execute("SELECT DATE '2026-07-31'").fetchone()[0],False),
            (connection.execute("SELECT DATE '2026-07-31'").fetchone()[0],
             connection.execute("SELECT DATE '9999-12-31'").fetchone()[0],True),
        ]
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member WHERE member_id IN ('M000002','M000003')"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member_lineage l JOIN curated.dim_member d "
            "USING(member_sk) WHERE d.member_id IN ('M000002','M000003')"
        ).fetchone()[0] == 4
        assert connection.execute(
            "SELECT valid_from,valid_to FROM curated.dim_member WHERE member_id='M000005' "
            "ORDER BY valid_from"
        ).fetchall() == [
            (connection.execute("SELECT DATE '2026-04-30'").fetchone()[0],
             connection.execute("SELECT DATE '2026-07-31'").fetchone()[0]),
            (connection.execute("SELECT DATE '2026-08-31'").fetchone()[0],
             connection.execute("SELECT DATE '9999-12-31'").fetchone()[0]),
        ]
        before = connection.execute(
            "SELECT sha256(string_agg(member_id||valid_from::VARCHAR||valid_to::VARCHAR,"
            "'|' ORDER BY member_id,valid_from)) FROM curated.dim_member WHERE NOT is_unknown"
        ).fetchone()[0]
        refresh_member_projection(connection)
        after = connection.execute(
            "SELECT sha256(string_agg(member_id||valid_from::VARCHAR||valid_to::VARCHAR,"
            "'|' ORDER BY member_id,valid_from)) FROM curated.dim_member WHERE NOT is_unknown"
        ).fetchone()[0]
        assert before == after
        assert connection.execute(
            "SELECT count(*) FROM (SELECT member_id FROM curated.dim_member WHERE is_current "
            "AND NOT is_unknown GROUP BY member_id HAVING count(*)>1)"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM curated.dim_member a JOIN curated.dim_member b "
            "ON a.member_id=b.member_id AND a.member_sk<b.member_sk "
            "AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to "
            "WHERE NOT a.is_unknown AND NOT b.is_unknown"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT sha256(to_json(struct_pack(level:=coalesce(NULL,'<NULL>'),"
            "city:=coalesce('台北','<NULL>')))) <> sha256(to_json(struct_pack("
            "level:=coalesce('一般','<NULL>'),city:=coalesce('台北','<NULL>'))))"
        ).fetchone()[0]
    finally:
        connection.close()


def test_missing_fx_never_falls_back_to_one(incremental_dataset: Path, tmp_path: Path) -> None:
    database = tmp_path / "phase3.duckdb"
    initialize_phase3(database, incremental_dataset)
    missing_fx = _order(
        "ORD00000007",currency="USD",amount="50.0000",
        created="2026-06-30T08:00:00+08:00",updated="2026-07-01T09:00:00+08:00",
    )
    unsupported_fx = _order(
        "ORD00000008",currency="EUR",amount="50.0000",
        created="2026-07-01T08:00:00+08:00",updated="2026-07-01T09:00:00+08:00",
    )
    _write(
        incremental_dataset / BATCHES[1].file_name,
        ORDER_HEADER,
        [missing_fx, unsupported_fx],
    )
    process_order_batch(database, BATCHES[1], incremental_dataset / BATCHES[1].file_name)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        assert connection.execute(
            "SELECT rate_to_twd IS NULL FROM staging.order_event WHERE order_id='ORD00000007'"
        ).fetchone()[0]
        assert connection.execute(
            "SELECT count(*) FROM curated.fact_order WHERE order_id='ORD00000007'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM quality.entity_rule "
            "WHERE business_key IN ('ORD00000007','ORD00000008') AND rule_id='ORD-017'"
        ).fetchone()[0] == 2
    finally:
        connection.close()


@pytest.fixture(scope="session")
def actual_phase3_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    database = tmp_path_factory.mktemp("actual-phase3") / "phase3.duckdb"
    run_all(database)
    return database


def test_actual_phase3_contract_and_replay(actual_phase3_warehouse: Path) -> None:
    before = current_state_checksum(actual_phase3_warehouse)
    connection = duckdb.connect(str(actual_phase3_warehouse), read_only=True)
    try:
        assert connection.execute(
            "SELECT count(*) FROM quality.entity_rule "
            "WHERE entity_type='order' AND rule_id='ORD-004'"
        ).fetchone()[0] == 1788
        assert connection.execute(
            "SELECT count(DISTINCT i.business_key) FROM quality.issue_hit i "
            "WHERE i.entity_type='order' AND i.rule_id='INC-001'"
        ).fetchone()[0] == 37
        assert connection.execute(
            "SELECT d.is_curated_eligible,count(DISTINCT i.business_key) "
            "FROM quality.issue_hit i JOIN quality.entity_disposition d "
            "USING(entity_type,business_key) WHERE i.entity_type='order' "
            "AND i.rule_id='INC-001' GROUP BY d.is_curated_eligible "
            "ORDER BY d.is_curated_eligible"
        ).fetchall() == [(False, 12), (True, 25)]
        assert connection.execute(
            "SELECT sha256(coalesce(string_agg(member_id || ':' || valid_from::VARCHAR || "
            "':' || valid_to::VARCHAR || ':' || member_sk::VARCHAR || ':' || version_hash,"
            "'|' ORDER BY member_id,valid_from),'')) FROM curated.dim_member "
            "WHERE NOT is_unknown"
        ).fetchone()[0] == "d6d050056c26ccf74cf2ba64b3113f332995cc10190df657ed23f7729bbf5356"
    finally:
        connection.close()

    replay = process_order_batch(
        actual_phase3_warehouse,
        BATCHES[1],
        DEFAULT_DATASET_ROOT / BATCHES[1].file_name,
    )
    assert replay["status"] == "SKIPPED_ALREADY_APPLIED"
    assert current_state_checksum(actual_phase3_warehouse) == before
