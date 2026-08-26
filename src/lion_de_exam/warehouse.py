"""Thin orchestration for the SQL-authoritative Phase 2 base warehouse."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from lion_de_exam.reconciliation import DEFAULT_VALIDATION_SQL, write_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "LionDEExam" / "candidate_package" / "dataset"
SQL_FILES = (
    "schema.sql",
    "staging.sql",
    "quality_gates.sql",
    "dimensions.sql",
    "fact_order.sql",
)
SOURCE_FILES = {
    "orders_base_path": "orders_base.csv",
    "members_path": "members.csv",
    "products_path": "products.csv",
    "fx_rates_path": "fx_rates.csv",
}


def _sql_path_literal(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _render_sql(path: Path, dataset_root: Path) -> str:
    text = path.read_text(encoding="utf-8")
    for parameter, file_name in SOURCE_FILES.items():
        source = dataset_root / file_name
        if not source.is_file():
            raise FileNotFoundError(f"Missing required Phase 2 source: {source}")
        text = text.replace("{{" + parameter + "}}", _sql_path_literal(source))
    unresolved = [token for token in SOURCE_FILES if "{{" + token + "}}" in text]
    if unresolved:
        raise ValueError(f"Unresolved SQL path parameters: {unresolved}")
    return text


def build_base_warehouse(
    database: Path,
    dataset_root: Path = DEFAULT_DATASET_ROOT,
    evidence_dir: Path | None = None,
) -> str | None:
    """Build a new Phase 2 warehouse transactionally from the four allowlisted files."""
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite existing warehouse: {database}")
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database))
    committed = False
    try:
        connection.execute("SET TimeZone='UTC'")
        connection.execute("BEGIN TRANSACTION")
        for file_name in SQL_FILES:
            sql_path = PROJECT_ROOT / "sql" / file_name
            connection.execute(_render_sql(sql_path, dataset_root))
        connection.execute(DEFAULT_VALIDATION_SQL.read_text(encoding="utf-8"))
        failures = connection.execute(
            "SELECT check_id,violation_count FROM quality.validation_result "
            "WHERE violation_count<>0 ORDER BY check_id"
        ).fetchall()
        if failures:
            raise RuntimeError(f"Warehouse validation failed: {failures}")
        connection.execute("COMMIT")
        committed = True
        return write_evidence(connection, evidence_dir) if evidence_dir else None
    except Exception:
        if not committed:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
        if not committed and database.exists():
            database.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 2 base warehouse")
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    checksum = build_base_warehouse(args.output_db, args.dataset_root, args.evidence_dir)
    if checksum:
        print(f"canonical_evidence_sha256={checksum}")
    print(f"warehouse={args.output_db}")
    print("build=passed")


if __name__ == "__main__":
    main()
