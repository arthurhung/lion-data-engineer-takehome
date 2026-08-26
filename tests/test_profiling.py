from __future__ import annotations

import json
import re
from pathlib import Path

from lion_de_exam.profiling import (
    CANONICAL_FILENAMES,
    DEFAULT_DATASET_ROOT,
    DEFAULT_SQL_FILE,
    run_profile,
)
from lion_de_exam.source_contract import CONTRACTS, normalize_birth_date


def test_typed_contract_has_explicit_columns_and_no_float_authority() -> None:
    assert [contract.dataset for contract in CONTRACTS] == [
        "orders",
        "members",
        "products",
        "fx_rates",
    ]
    for contract in CONTRACTS:
        assert contract.business_key
        assert contract.columns
        assert len({column.name for column in contract.columns}) == len(contract.columns)
        assert all("FLOAT" not in column.duckdb_type for column in contract.columns)

    order_columns = {column.name: column for column in CONTRACTS[0].columns}
    created = order_columns["order_created_at"]
    assert created.accepted_raw_formats == (
        "ISO_8601_WITH_OFFSET",
        "YYYY/MM/DD HH:MM:SS",
    )
    assert created.canonical_typed_format == "TIMESTAMPTZ"
    assert created.normalization_quality_flag == "timezone_assumed=true"
    assert "Asia/Taipei" in str(created.normalization_assumption)
    currency = order_columns["currency"]
    assert currency.domain == ("JPY", "NTD", "TWD", "USD")
    assert "NTD" in str(currency.normalization_assumption)

    member_columns = {column.name: column for column in CONTRACTS[1].columns}
    birth_date = member_columns["birth_date"]
    assert birth_date.semantic_sentinel_values == ("1900-01-01",)
    assert birth_date.canonical_nullable is True
    assert birth_date.semantic_quality_flags == (
        "birth_date_sentinel",
        "birth_date_unknown",
    )
    assert "canonical NULL" in str(birth_date.semantic_normalization)


def test_birth_date_sentinel_parses_but_normalizes_to_null_and_retains_raw() -> None:
    normalized = normalize_birth_date("1900-01-01")

    assert normalized == {
        "raw_birth_date": "1900-01-01",
        "birth_date": None,
        "birth_date_sentinel": True,
        "birth_date_unknown": True,
    }


def test_two_clean_profiles_have_identical_canonical_evidence(tmp_path: Path) -> None:
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"

    checksum1 = run_profile(DEFAULT_DATASET_ROOT, DEFAULT_SQL_FILE, run1, run1)
    checksum2 = run_profile(DEFAULT_DATASET_ROOT, DEFAULT_SQL_FILE, run2, run2)

    assert checksum1 == checksum2
    for file_name in (*CANONICAL_FILENAMES, "evidence_manifest.json"):
        assert (run1 / file_name).read_bytes() == (run2 / file_name).read_bytes()
        committed = Path("docs/evidence/phase_01") / file_name
        assert (run1 / file_name).read_bytes() == committed.read_bytes()

    combined = "".join(
        (run1 / file_name).read_text(encoding="utf-8")
        for file_name in (*CANONICAL_FILENAMES, "evidence_manifest.json")
    )
    assert str(Path.cwd()) not in combined
    assert "/Users/" not in combined
    assert "execution_time" not in combined.replace('"execution_time"', "")
    assert "generated_at" not in combined


def test_profile_row_counts_and_decimal_strings(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    run_profile(DEFAULT_DATASET_ROOT, DEFAULT_SQL_FILE, evidence, evidence)
    profile = json.loads((evidence / "source_profile.json").read_text(encoding="utf-8"))
    rows = {
        item["source_file"]: item["data_row_count_excluding_header"] for item in profile["files"]
    }
    assert rows == {
        "orders_base.csv": 100040,
        "orders_incremental_day1.csv": 4615,
        "orders_incremental_day2.csv": 4700,
        "orders_incremental_day3.csv": 4615,
        "members.csv": 8991,
        "products.csv": 300,
        "fx_rates.csv": 134,
    }

    decimal_columns = [
        column
        for file_profile in profile["files"]
        for column in file_profile["columns"]
        if column["logical_type"] == "decimal"
    ]
    for column in decimal_columns:
        scale = int(column["duckdb_type"].split(",")[1].rstrip(")"))
        assert re.fullmatch(rf"-?[0-9]+\.[0-9]{{{scale}}}", column["typed_min"])
        assert re.fullmatch(rf"-?[0-9]+\.[0-9]{{{scale}}}", column["typed_max"])
        for value in column["typed_quantiles"].values():
            assert re.fullmatch(rf"-?[0-9]+\.[0-9]{{{scale}}}", value)


def test_quality_report_table_matches_machine_readable_issue_counts() -> None:
    evidence = json.loads(
        Path("docs/evidence/phase_01/issue_summary.json").read_text(encoding="utf-8")
    )
    report = Path("docs/part_a_quality_report.md").read_text(encoding="utf-8")
    table_rows = re.findall(
        r"^\| `([A-Z]+-[0-9]{3})` \| ([0-9,]+) \| ([0-9,]+) \|",
        report,
        flags=re.MULTILINE,
    )
    report_counts = {
        issue_id: (int(row_count.replace(",", "")), int(key_count.replace(",", "")))
        for issue_id, row_count, key_count in table_rows
    }
    evidence_counts = {
        item["issue_id"]: (
            item["affected_row_count"],
            item["affected_business_key_count"],
        )
        for item in evidence["issues"]
    }

    assert len(report_counts) == 47
    assert report_counts == evidence_counts
